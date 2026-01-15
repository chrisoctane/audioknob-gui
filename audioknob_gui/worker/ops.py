from __future__ import annotations

import glob
import os
import subprocess
import shlex
from dataclasses import dataclass
import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Any

from audioknob_gui.core.diffutil import unified_diff
from audioknob_gui.core.paths import get_registry_path
from audioknob_gui.core.qjackctl import (
    build_post_start_script,
    default_post_start_script_path,
    normalize_cpu_cores,
    read_config,
)
from audioknob_gui.core.runner import run
from audioknob_gui.registry import Knob, load_registry


# ============================================================================
# Distro detection for kernel cmdline handling
# ============================================================================

@dataclass(frozen=True)
class DistroInfo:
    """Detected distribution and boot system info."""
    distro_id: str  # e.g., "opensuse-tumbleweed", "fedora", "ubuntu"
    boot_system: str  # "grub2-bls", "grub2", "systemd-boot", "unknown"
    kernel_cmdline_file: str
    kernel_cmdline_update_cmd: list[str]


def read_os_release() -> dict[str, str]:
    os_release: dict[str, str] = {}
    try:
        content = Path("/etc/os-release").read_text(encoding="utf-8")
        for line in content.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                os_release[key] = value.strip().strip('"').strip("'")
    except Exception:
        pass
    return os_release


def resolve_cpupower_config_path(distro_id: str) -> str:
    deb_like = distro_id in ("debian", "ubuntu", "linuxmint", "pop")
    primary = "/etc/default/cpufrequtils" if deb_like else "/etc/sysconfig/cpupower"
    secondary = "/etc/sysconfig/cpupower" if deb_like else "/etc/default/cpufrequtils"
    if Path(primary).exists():
        return primary
    if Path(secondary).exists():
        return secondary
    return primary


def resolve_rtirq_config_path(distro_id: str) -> str:
    deb_like = distro_id in ("debian", "ubuntu", "linuxmint", "pop")
    primary = "/etc/default/rtirq" if deb_like else "/etc/sysconfig/rtirq"
    secondary = "/etc/sysconfig/rtirq" if deb_like else "/etc/default/rtirq"
    if Path(primary).exists():
        return primary
    if Path(secondary).exists():
        return secondary
    return primary


def _systemd_is_active(unit: str) -> bool:
    try:
        result = run(["systemctl", "is-active", unit])
    except Exception:
        return False
    return result.stdout.strip() == "active"


def detect_power_profile_backend() -> dict[str, str] | None:
    """Detect available power profile backend.

    Prefers tuned when active; otherwise uses powerprofilesctl when available.
    Returns dict with backend, cmd, and service keys, or None if unavailable.
    """
    from audioknob_gui.platform.packages import which_command

    ppd_cmd = which_command("powerprofilesctl")
    tuned_cmd = which_command("tuned-adm")

    tuned_active = bool(tuned_cmd) and _systemd_is_active("tuned.service")

    if tuned_active:
        return {
            "backend": "tuned",
            "cmd": tuned_cmd or "tuned-adm",
            "service": "tuned.service",
        }

    if ppd_cmd:
        return {
            "backend": "powerprofilesctl",
            "cmd": ppd_cmd,
            "service": "power-profiles-daemon.service",
        }

    if tuned_cmd:
        return {
            "backend": "tuned",
            "cmd": tuned_cmd,
            "service": "tuned.service",
        }

    return None


def read_power_profile(backend: str, cmd: str) -> str | None:
    """Read the current power profile name for the selected backend."""
    if backend == "powerprofilesctl":
        result = run([cmd, "get"])
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    if backend == "tuned":
        result = run([cmd, "active"])
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if "current active profile" in line.lower() and ":" in line:
                return line.split(":", 1)[1].strip() or None
        return None
    return None


def detect_distro() -> DistroInfo:
    """Detect distribution and boot system configuration."""
    from audioknob_gui.platform.packages import which_command
    
    # Parse /etc/os-release
    os_release = read_os_release()
    
    distro_id = os_release.get("ID", "unknown")
    version_id = os_release.get("VERSION_ID", "")
    
    def _cmd(cmd: str, *args: str) -> list[str]:
        path = which_command(cmd)
        if path:
            return [path, *args]
        return [cmd, *args]

    # Detect boot system and cmdline location
    if distro_id == "opensuse-tumbleweed" or (distro_id == "opensuse" and "tumbleweed" in os_release.get("PRETTY_NAME", "").lower()):
        # openSUSE Tumbleweed uses GRUB2-BLS with sdbootutil
        if Path("/etc/kernel/cmdline").exists() and which_command("sdbootutil"):
            return DistroInfo(
                distro_id="opensuse-tumbleweed",
                boot_system="grub2-bls",
                kernel_cmdline_file="/etc/kernel/cmdline",
                kernel_cmdline_update_cmd=_cmd("sdbootutil", "update-all-entries"),
            )
    
    if distro_id in ("opensuse-leap", "opensuse"):
        # openSUSE Leap uses traditional GRUB2
        return DistroInfo(
            distro_id="opensuse-leap",
            boot_system="grub2",
            kernel_cmdline_file="/etc/default/grub",
            kernel_cmdline_update_cmd=_cmd("grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"),
        )
    
    if distro_id == "fedora":
        return DistroInfo(
            distro_id="fedora",
            boot_system="grub2",
            kernel_cmdline_file="/etc/default/grub",
            kernel_cmdline_update_cmd=_cmd("grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"),
        )
    
    if distro_id in ("debian", "ubuntu", "linuxmint", "pop"):
        return DistroInfo(
            distro_id=distro_id,
            boot_system="grub2",
            kernel_cmdline_file="/etc/default/grub",
            kernel_cmdline_update_cmd=_cmd("update-grub"),
        )
    
    if distro_id == "arch":
        # Arch can use either GRUB2 or systemd-boot
        if Path("/boot/loader/loader.conf").exists():
            return DistroInfo(
                distro_id="arch",
                boot_system="systemd-boot",
                kernel_cmdline_file="/etc/kernel/cmdline",
                kernel_cmdline_update_cmd=_cmd("bootctl", "update"),
            )
        return DistroInfo(
            distro_id="arch",
            boot_system="grub2",
            kernel_cmdline_file="/etc/default/grub",
            kernel_cmdline_update_cmd=_cmd("grub-mkconfig", "-o", "/boot/grub/grub.cfg"),
        )
    
    # Fallback: try to detect boot system heuristically
    if Path("/etc/kernel/cmdline").exists():
        return DistroInfo(
            distro_id=distro_id,
            boot_system="bls",
            kernel_cmdline_file="/etc/kernel/cmdline",
            kernel_cmdline_update_cmd=["echo", "Manual bootloader update required"],
        )
    
    if Path("/etc/default/grub").exists():
        # Guess grub path
        if Path("/boot/grub2/grub.cfg").exists():
            return DistroInfo(
                distro_id=distro_id,
                boot_system="grub2",
                kernel_cmdline_file="/etc/default/grub",
                kernel_cmdline_update_cmd=_cmd("grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"),
            )
        if Path("/boot/grub/grub.cfg").exists():
            return DistroInfo(
                distro_id=distro_id,
                boot_system="grub2",
                kernel_cmdline_file="/etc/default/grub",
                kernel_cmdline_update_cmd=_cmd("grub-mkconfig", "-o", "/boot/grub/grub.cfg"),
            )
    
    return DistroInfo(
        distro_id=distro_id,
        boot_system="unknown",
        kernel_cmdline_file="",
        kernel_cmdline_update_cmd=[],
    )


def _expand_path(path: str) -> str:
    return str(Path(path).expanduser())


def build_knob_paths(
    *,
    paths: dict[str, str],
    distro: DistroInfo,
    knobs: list[Knob] | None = None,
) -> dict[str, dict[str, Any]]:
    if knobs is None:
        knobs = load_registry(get_registry_path())

    out: dict[str, dict[str, Any]] = {}

    for knob in knobs:
        targets: list[dict[str, Any]] = []
        kind = knob.impl.kind if knob.impl is not None else "none"
        params = knob.impl.params if knob.impl is not None else {}

        if kind in ("pam_limits_audio_group", "sysctl_conf", "udev_rule", "pipewire_conf", "qjackctl_server_prefix"):
            path = str(params.get("path", ""))
            targets.append({"type": "path", "value": _expand_path(path) if path else ""})
            if kind == "qjackctl_server_prefix":
                targets.append({"type": "path", "value": str(default_post_start_script_path())})
        elif kind == "rtirq_config":
            cfg_path = paths.get("rtirq_config", "")
            targets.append({"type": "path", "value": cfg_path})
            unit = str(params.get("unit", "rtirq.service"))
            targets.append({"type": "systemd_unit", "value": unit})
        elif kind == "irq_affinity":
            targets.append({"type": "proc_irq", "value": "/proc/irq"})
            state_path = str(params.get("persist_state_path", ""))
            if state_path:
                targets.append({"type": "path", "value": state_path})
            unit = str(params.get("persist_unit", ""))
            if unit:
                targets.append({"type": "systemd_unit", "value": unit})
            unit_path = str(params.get("persist_unit_path", ""))
            if unit_path:
                targets.append({"type": "path", "value": unit_path})
        elif kind == "power_profile":
            targets.append({"type": "command", "value": "powerprofilesctl"})
            targets.append({"type": "command", "value": "tuned-adm"})
            targets.append({"type": "systemd_unit", "value": "power-profiles-daemon.service"})
            targets.append({"type": "systemd_unit", "value": "tuned.service"})
        elif kind == "sysfs_glob_kv":
            glob_pat = str(params.get("glob", ""))
            if glob_pat:
                targets.append({"type": "sysfs_glob", "value": glob_pat})
        elif kind == "kernel_cmdline":
            cmdline_path = paths.get("kernel_cmdline_file", "")
            targets.append({"type": "kernel_cmdline_file", "value": cmdline_path})
            param = str(params.get("param", ""))
            if param:
                targets.append({"type": "kernel_cmdline_param", "value": param})
            if distro.kernel_cmdline_update_cmd:
                targets.append({"type": "kernel_cmdline_update_cmd", "value": distro.kernel_cmdline_update_cmd})
        elif kind == "systemd_unit_toggle":
            unit = str(params.get("unit", ""))
            targets.append({"type": "systemd_unit", "value": unit})
        elif kind == "user_service_mask":
            services = params.get("services")
            if isinstance(services, list):
                targets.append(
                    {"type": "user_services", "value": [str(s) for s in services if s]}
                )
            else:
                unit = str(params.get("unit", ""))
                targets.append({"type": "user_service", "value": unit})
        elif kind == "group_membership":
            groups = params.get("groups")
            if isinstance(groups, list):
                targets.append({"type": "groups", "value": [str(g) for g in groups if g]})
            elif knob.requires_groups:
                targets.append({"type": "groups", "value": list(knob.requires_groups)})
        elif kind == "baloo_disable":
            targets.append({"type": "command", "value": "balooctl"})
        elif kind == "read_only":
            what = str(params.get("what", ""))
            if what:
                targets.append({"type": "read_only", "value": what})

        if knob.id == "cpu_governor_performance_persistent":
            cfg_path = paths.get("cpupower_config", "")
            if cfg_path:
                targets.append({"type": "path", "value": cfg_path})
            targets.append({"type": "systemd_unit", "value": "cpupower.service"})

        out[knob.id] = {"kind": kind, "targets": targets}

    return out


def scan_system_profile(knobs: list[Knob] | None = None) -> dict[str, Any]:
    """Build a distro-aware path profile for knob operations."""
    distro = detect_distro()
    os_release = read_os_release()
    pretty_name = os_release.get("PRETTY_NAME", "")
    version_id = os_release.get("VERSION_ID", "")

    paths: dict[str, str] = {
        "kernel_cmdline_file": distro.kernel_cmdline_file,
        "cpupower_config": resolve_cpupower_config_path(distro.distro_id),
        "rtirq_config": resolve_rtirq_config_path(distro.distro_id),
        "pipewire_user_conf_dir": str(Path("~/.config/pipewire/pipewire.conf.d").expanduser()),
        "pipewire_system_conf_dir": "/etc/pipewire/pipewire.conf.d",
        "qjackctl_config": str(Path("~/.config/rncbc.org/QjackCtl.conf").expanduser()),
        "limits_dir": "/etc/security/limits.d",
        "sysctl_dir": "/etc/sysctl.d",
        "udev_rules_dir": "/etc/udev/rules.d",
    }

    commands: dict[str, list[str]] = {
        "kernel_cmdline_update": distro.kernel_cmdline_update_cmd,
    }

    try:
        from audioknob_gui.platform.packages import resolve_package_commands
        pkg_cmds = resolve_package_commands()
        commands.update(
            {
                "package_install": pkg_cmds.get("install", []),
                "package_remove": pkg_cmds.get("remove", []),
                "package_reinstall": pkg_cmds.get("reinstall", []),
                "package_query_owner": pkg_cmds.get("query_owner", []),
            }
        )
    except Exception:
        pass

    def _check_path(path: str, *, expect_dir: bool) -> bool:
        if not path:
            return False
        p = Path(path).expanduser()
        return p.is_dir() if expect_dir else p.exists()

    checks: dict[str, bool] = {
        "kernel_cmdline_file": _check_path(paths["kernel_cmdline_file"], expect_dir=False),
        "cpupower_config": _check_path(paths["cpupower_config"], expect_dir=False),
        "rtirq_config": _check_path(paths["rtirq_config"], expect_dir=False),
        "pipewire_user_conf_dir": _check_path(paths["pipewire_user_conf_dir"], expect_dir=True),
        "pipewire_system_conf_dir": _check_path(paths["pipewire_system_conf_dir"], expect_dir=True),
        "qjackctl_config": _check_path(paths["qjackctl_config"], expect_dir=False),
        "limits_dir": _check_path(paths["limits_dir"], expect_dir=True),
        "sysctl_dir": _check_path(paths["sysctl_dir"], expect_dir=True),
        "udev_rules_dir": _check_path(paths["udev_rules_dir"], expect_dir=True),
    }

    notes: list[str] = []
    if not paths["kernel_cmdline_file"]:
        notes.append("No kernel cmdline file detected; kernel cmdline knobs may be unavailable.")
    elif not checks["kernel_cmdline_file"]:
        notes.append(f"Kernel cmdline file not found: {paths['kernel_cmdline_file']}")
    if not checks["limits_dir"]:
        notes.append(f"Limits.d directory missing: {paths['limits_dir']}")
    if not checks["sysctl_dir"]:
        notes.append(f"sysctl.d directory missing: {paths['sysctl_dir']}")
    if not checks["udev_rules_dir"]:
        notes.append(f"udev rules directory missing: {paths['udev_rules_dir']}")

    knob_paths = build_knob_paths(paths=paths, distro=distro, knobs=knobs)

    return {
        "schema": 1,
        "scanned_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "distro_id": distro.distro_id,
        "version_id": version_id,
        "pretty_name": pretty_name,
        "boot_system": distro.boot_system,
        "paths": paths,
        "commands": commands,
        "checks": checks,
        "knob_paths": knob_paths,
        "notes": notes,
    }


@dataclass(frozen=True)
class FileChange:
    path: str
    action: str  # create|modify|delete
    diff: str


@dataclass(frozen=True)
class PreviewItem:
    knob_id: str
    title: str
    description: str
    requires_root: bool
    requires_reboot: bool
    risk_level: str
    action: str  # apply|restore
    file_changes: list[FileChange]
    would_run: list[list[str]]
    would_write: list[dict[str, Any]]
    notes: list[str]


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _parse_cpu_list(spec: str) -> set[int]:
    out: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, _, end = part.partition("-")
            try:
                s = int(start)
                e = int(end)
            except ValueError:
                continue
            if e < s:
                s, e = e, s
            out.update(range(s, e + 1))
        else:
            try:
                out.add(int(part))
            except ValueError:
                continue
    return out


def _find_pids_by_comm(name: str) -> list[int]:
    pids: list[int] = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if comm == name:
            pids.append(int(entry.name))
    return pids


def _read_proc_cpu_allowed_list(pid: int) -> str | None:
    try:
        text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except Exception:
        return None
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            _, _, value = line.partition(":")
            return value.strip()
    return None


def _list_task_ids(pid: int) -> list[int]:
    tids: list[int] = []
    task_dir = Path(f"/proc/{pid}/task")
    try:
        for entry in task_dir.iterdir():
            if entry.name.isdigit():
                tids.append(int(entry.name))
    except Exception:
        return []
    return tids


def _jackd_affinity_matches(expected_list: str) -> bool | None:
    expected = _parse_cpu_list(expected_list)
    if not expected:
        return None
    pids = _find_pids_by_comm("jackd")
    if not pids:
        return None
    saw = False
    for pid in pids:
        allowed = _read_proc_cpu_allowed_list(pid)
        if not allowed:
            continue
        allowed_set = _parse_cpu_list(allowed)
        if not allowed_set:
            continue
        saw = True
        if allowed_set == expected:
            return True
    if saw:
        return False
    return None


def _jackd_rt_summary() -> dict[str, Any] | None:
    pids = _find_pids_by_comm("jackd")
    if not pids:
        return None
    total_threads = 0
    rt_threads = 0
    rt_priorities: list[int] = []
    errors: list[str] = []
    for pid in pids:
        tids = _list_task_ids(pid)
        if not tids:
            tids = [pid]
        total_threads += len(tids)
        for tid in tids:
            try:
                policy = os.sched_getscheduler(tid)
            except Exception as e:
                errors.append(f"pid {pid} tid {tid}: {e}")
                continue
            if policy in (os.SCHED_FIFO, os.SCHED_RR):
                rt_threads += 1
                try:
                    prio = os.sched_getparam(tid).sched_priority
                except Exception:
                    prio = None
                if prio is not None:
                    rt_priorities.append(prio)
    return {
        "pids": pids,
        "total_threads": total_threads,
        "rt_threads": rt_threads,
        "rt_priorities": sorted(set(rt_priorities)),
        "errors": errors,
    }


def apply_jackd_affinity(cpu_list: str) -> dict[str, Any]:
    expected = _parse_cpu_list(cpu_list)
    if not expected:
        return {"status": "invalid_cpu_list", "expected": cpu_list}
    pids = _find_pids_by_comm("jackd")
    if not pids:
        return {"status": "not_running", "expected": cpu_list}
    errors: list[str] = []
    task_counts: dict[int, int] = {}
    for pid in pids:
        tids = _list_task_ids(pid)
        if not tids:
            tids = [pid]
        task_counts[pid] = len(tids)
        for tid in tids:
            try:
                os.sched_setaffinity(tid, expected)
            except Exception as e:
                errors.append(f"pid {pid} tid {tid}: {e}")
    runtime_ok = _jackd_affinity_matches(cpu_list)
    status = "applied"
    if runtime_ok is False or errors:
        status = "partial"
    return {
        "status": status,
        "expected": cpu_list,
        "pids": pids,
        "task_counts": task_counts,
        "runtime_ok": runtime_ok,
        "errors": errors,
    }


def _pam_limits_preview(params: dict[str, Any]) -> list[FileChange]:
    path = str(params["path"])
    wanted_lines = [str(x) for x in params.get("lines", [])]

    before = _read_text(path)
    before_lines = before.splitlines()
    after_lines = list(before_lines)

    for line in wanted_lines:
        if line not in after_lines:
            after_lines.append(line)

    after = "\n".join(after_lines).rstrip("\n") + "\n"

    action = "create" if (before == "" and not Path(path).exists()) else "modify"
    return [FileChange(path=path, action=action, diff=unified_diff(path, before, after))]


def _sysctl_conf_preview(params: dict[str, Any]) -> list[FileChange]:
    # Implemented as a simple sysctl.d drop-in file. We only ensure lines exist.
    path = str(params["path"])
    wanted_lines = [str(x) for x in params.get("lines", [])]

    before = _read_text(path)
    before_lines = before.splitlines()
    after_lines = list(before_lines)

    for line in wanted_lines:
        if line not in after_lines:
            after_lines.append(line)

    after = "\n".join(after_lines).rstrip("\n") + "\n"

    action = "create" if (before == "" and not Path(path).exists()) else "modify"
    return [FileChange(path=path, action=action, diff=unified_diff(path, before, after))]


def _systemd_unit_preview(params: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    unit = str(params["unit"])
    action = str(params.get("action", ""))
    if action == "disable_now":
        return [["systemctl", "disable", "--now", unit]], []
    elif action == "enable_now":
        return [["systemctl", "enable", "--now", unit]], []
    elif action == "enable":
        return [["systemctl", "enable", unit]], []
    elif action == "disable":
        return [["systemctl", "disable", unit]], []
    return [], [f"Unsupported systemd action: {action}"]


def _power_profile_preview(params: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    notes: list[str] = []
    cmds: list[list[str]] = []

    backend = detect_power_profile_backend()
    if not backend:
        notes.append("No power profile backend found (powerprofilesctl or tuned-adm).")
        return cmds, notes

    if backend["backend"] == "powerprofilesctl":
        profile = str(params.get("ppd_profile", "performance")).strip() or "performance"
        cmds.append([backend["cmd"], "set", profile])
        notes.append(f"Backend: power-profiles-daemon ({profile})")
    else:
        profile = str(params.get("tuned_profile", "latency-performance")).strip() or "latency-performance"
        cmds.append([backend["cmd"], "profile", profile])
        notes.append(f"Backend: tuned ({profile})")
    notes.append("Reset restores the previous profile.")
    return cmds, notes


def _rtirq_config_preview(params: dict[str, Any]) -> tuple[list[FileChange], list[list[str]]]:
    from audioknob_gui.core.rtirq import apply_rtirq_block, normalize_rtirq_list

    distro_id = read_os_release().get("ID", "")
    cfg_path = resolve_rtirq_config_path(distro_id)
    path = Path(cfg_path)

    name_list = normalize_rtirq_list(params.get("name_list", ["snd", "usb"]))
    high_list = normalize_rtirq_list(params.get("high_list", name_list))
    prio_high = int(params.get("prio_high", 90))
    prio_decr = int(params.get("prio_decr", 5))

    before = _read_text(str(path))
    after = apply_rtirq_block(
        before,
        name_list=name_list,
        high_list=high_list,
        prio_high=prio_high,
        prio_decr=prio_decr,
    )

    changes: list[FileChange] = []
    action = "modify" if path.exists() else "create"
    if before != after:
        changes.append(FileChange(path=str(path), action=action, diff=unified_diff(str(path), before, after)))

    unit = str(params.get("unit", "rtirq.service"))
    cmds = [["systemctl", "enable", "--now", unit]]
    return changes, cmds


def _irq_affinity_preview(params: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    from audioknob_gui.core.irq import collect_target_irqs, resolve_selected_devices

    device_keys = params.get("device_keys") or []
    cpu_cores = str(params.get("cpu_cores", "")).strip()
    state_path = str(params.get("persist_state_path", "")).strip()
    unit = str(params.get("persist_unit", "")).strip()
    notes: list[str] = []
    would_write: list[dict[str, Any]] = []
    try:
        active = run(["systemctl", "is-active", "irqbalance.service"]).stdout.strip()
        if active == "active":
            notes.append("irqbalance is active and can override IRQ pinning.")
    except Exception:
        pass

    if not device_keys:
        notes.append("No IRQ pinning devices selected. Configure devices before applying.")
        return would_write, notes
    if not cpu_cores:
        notes.append("No CPU cores configured for IRQ pinning.")
        return would_write, notes

    selected, missing = resolve_selected_devices(device_keys)
    if missing:
        notes.append(f"Missing devices: {', '.join(missing)}")
    if not selected:
        notes.append("No selected audio devices found.")
        return would_write, notes

    target_irqs = collect_target_irqs(selected)
    if not target_irqs:
        notes.append("No IRQs found for selected devices.")
        return would_write, notes

    for irq in target_irqs:
        would_write.append(
            {"path": f"/proc/irq/{irq}/smp_affinity_list", "value": cpu_cores}
        )

    for device in selected:
        warning = device.get("warning")
        if warning:
            notes.append(str(warning))

    if state_path:
        notes.append(f"Will persist IRQ pinning in {state_path}.")
    if unit:
        notes.append(f"Will enable {unit} to re-apply IRQ pinning at boot.")

    return would_write, notes


def _sysfs_glob_preview(params: dict[str, Any]) -> list[dict[str, Any]]:
    g = params["glob"]
    value = str(params["value"])
    matches = _expand_sysfs_globs(g)
    return [{"path": p, "value": value} for p in matches]


def _qjackctl_server_prefix_preview(params: dict[str, Any]) -> list[FileChange]:
    from audioknob_gui.core.qjackctl import (
        build_post_start_script,
        default_post_start_script_path,
        ensure_server_has_flags,
        ensure_server_prefix,
        normalize_cpu_cores,
        read_config,
        update_config,
    )
    import configparser
    import io

    path_str = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
    path = Path(path_str).expanduser()
    ensure_rt = bool(params.get("ensure_rt", True))
    ensure_priority = bool(params.get("ensure_priority", False))
    cpu_cores = params.get("cpu_cores")
    if cpu_cores is not None:
        cpu_cores = str(cpu_cores)
    cpu_cores_norm = normalize_cpu_cores(cpu_cores) if cpu_cores is not None else None

    post_startup_enabled = False
    post_startup_shell = ""
    post_script_path = default_post_start_script_path()
    if cpu_cores_norm:
        post_startup_enabled = True
        post_startup_shell = str(post_script_path)

    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    if path.exists():
        cp.read(path, encoding="utf-8")
    cfg = None
    try:
        cfg = read_config(path)
    except Exception:
        cfg = None
    before_cmd = (cfg.server_cmd if cfg is not None else None) or ""
    before_prefix = (cfg.server_prefix if cfg is not None else None) or ""
    # Compute what the after command would be (without modifying file)
    after_cmd = ensure_server_has_flags(
        before_cmd or "jackd",
        ensure_rt=False,
        ensure_priority=False,
        cpu_cores="",
    )
    after_prefix = ensure_server_prefix(before_prefix, cpu_cores="")
    target_preset = None
    if cfg is not None and cfg.def_preset:
        target_preset = cfg.def_preset

    before = _read_text(str(path))
    update_config(
        cp,
        preset=target_preset,
        new_server_cmd=after_cmd,
        server_prefix=after_prefix,
        realtime=True if ensure_rt else None,
        priority=90 if ensure_priority else None,
        mirror_unscoped=True,
        server_config_enabled=False,
        post_startup_enabled=post_startup_enabled,
        post_startup_shell=post_startup_shell,
    )

    out = io.StringIO()
    cp.write(out, space_around_delimiters=False)
    after = out.getvalue()

    changes: list[FileChange] = []
    action = "modify" if path.exists() else "create"
    if before != after:
        changes.append(FileChange(path=str(path), action=action, diff=unified_diff(str(path), before, after)))

    if cpu_cores_norm:
        script_body = build_post_start_script(cpu_cores_norm)
        script_before = _read_text(str(post_script_path))
        if script_before != script_body:
            script_action = "modify" if post_script_path.exists() else "create"
            changes.append(
                FileChange(
                    path=str(post_script_path),
                    action=script_action,
                    diff=unified_diff(str(post_script_path), script_before, script_body),
                )
            )
    else:
        if post_script_path.exists():
            script_before = _read_text(str(post_script_path))
            changes.append(
                FileChange(
                    path=str(post_script_path),
                    action="delete",
                    diff=unified_diff(str(post_script_path), script_before, ""),
                )
            )

    return changes


def _udev_rule_preview(params: dict[str, Any]) -> list[FileChange]:
    """Preview for udev rule creation."""
    path = str(params["path"])
    content = str(params["content"])
    
    before = _read_text(path)
    after = content.rstrip("\n") + "\n"
    
    action = "create" if not Path(path).exists() else "modify"
    return [FileChange(path=path, action=action, diff=unified_diff(path, before, after))]


def _kernel_cmdline_preview(params: dict[str, Any]) -> tuple[list[FileChange], list[str]]:
    """Preview for kernel cmdline modification.
    
    Returns (file_changes, notes) tuple.
    """
    param = str(params.get("param", ""))
    if not param:
        return [], ["No kernel parameter specified"]
    
    distro = detect_distro()
    notes: list[str] = []
    
    if distro.boot_system == "unknown":
        notes.append(f"Unknown boot system for {distro.distro_id}; cannot modify kernel cmdline")
        return [], notes
    
    cmdline_file = distro.kernel_cmdline_file
    if not cmdline_file:
        notes.append("No kernel cmdline file detected")
        return [], notes
    
    before = _read_text(cmdline_file)

    def _cmdline_tokens_for_file(text: str, boot_system: str) -> list[str]:
        """Return existing cmdline tokens for presence checks (avoid substring matches)."""
        if boot_system in ("grub2-bls", "bls", "systemd-boot"):
            return text.strip().split()

        if boot_system == "grub2":
            # Extract GRUB_CMDLINE_LINUX_DEFAULT="..."; best-effort parse.
            for line in text.splitlines():
                if not line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                    continue
                _, _, rhs = line.partition("=")
                rhs = rhs.strip()
                # Prefer quoted value if present
                if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                    rhs = rhs[1:-1]
                try:
                    return shlex.split(rhs)
                except Exception:
                    return rhs.split()
            return []

        return text.strip().split()

    def _param_present(param: str, tokens: list[str]) -> bool:
        if not param:
            return False
        if "=" in param:
            return any(t == param for t in tokens)
        # also treat foo=bar as satisfying "foo" presence
        return any(t == param or t.startswith(param + "=") for t in tokens)
    
    tokens = _cmdline_tokens_for_file(before, distro.boot_system)

    if distro.boot_system == "grub2-bls" or distro.boot_system == "bls":
        # BLS style: /etc/kernel/cmdline contains the full cmdline
        if _param_present(param, tokens):
            notes.append(f"Parameter '{param}' already present in {cmdline_file}")
            return [], notes
        
        # Add param to the end of the line (single line file)
        after = before.strip() + " " + param + "\n" if before.strip() else param + "\n"
        
        notes.append(f"Will run: {' '.join(distro.kernel_cmdline_update_cmd)}")
        notes.append("Requires reboot to take effect")
        
    elif distro.boot_system == "grub2":
        # GRUB2 style: /etc/default/grub has GRUB_CMDLINE_LINUX_DEFAULT="..."
        if _param_present(param, tokens):
            notes.append(f"Parameter '{param}' already present in {cmdline_file}")
            return [], notes
        
        # Find and modify GRUB_CMDLINE_LINUX_DEFAULT line
        after_lines = before.splitlines() if before else []
        found = False
        for i, line in enumerate(after_lines):
            if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                # Extract current value and add param
                # Format: GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
                if '="' in line and line.rstrip().endswith('"'):
                    # Add before the closing quote
                    after_lines[i] = line.rstrip()[:-1] + " " + param + '"'
                else:
                    # Fallback: append to line
                    after_lines[i] = line.rstrip() + " " + param
                found = True
                break
        
        if not found:
            # Add the line if missing
            after_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{param}"')
        
        after = "\n".join(after_lines)
        if after and not after.endswith("\n"):
            after += "\n"
        
        notes.append(f"Will run: {' '.join(distro.kernel_cmdline_update_cmd)}")
        notes.append("Requires reboot to take effect")
    
    elif distro.boot_system == "systemd-boot":
        # systemd-boot: similar to BLS
        if _param_present(param, tokens):
            notes.append(f"Parameter '{param}' already present in {cmdline_file}")
            return [], notes
        
        after = before.strip() + " " + param + "\n" if before.strip() else param + "\n"
        notes.append(f"Will run: {' '.join(distro.kernel_cmdline_update_cmd)}")
        notes.append("Requires reboot to take effect")
    
    else:
        notes.append(f"Unsupported boot system: {distro.boot_system}")
        return [], notes
    
    action = "modify" if Path(cmdline_file).exists() else "create"
    return [FileChange(path=cmdline_file, action=action, diff=unified_diff(cmdline_file, before, after))], notes


def _pipewire_conf_preview(params: dict[str, Any]) -> list[FileChange]:
    """Preview for PipeWire configuration."""
    path_str = str(params.get("path", "~/.config/pipewire/pipewire.conf.d/99-audioknob.conf"))
    path = Path(path_str).expanduser()
    
    # Build config content based on params
    lines = ["# audioknob-gui PipeWire configuration"]
    
    quantum = params.get("quantum")
    rate = params.get("rate")
    
    if quantum or rate:
        lines.append("context.properties = {")
        if quantum:
            lines.append(f"    default.clock.quantum = {quantum}")
            lines.append(f"    default.clock.min-quantum = {quantum}")
        if rate:
            lines.append(f"    default.clock.rate = {rate}")
        lines.append("}")
    
    content = "\n".join(lines) + "\n"
    before = _read_text(str(path))
    
    action = "create" if not path.exists() else "modify"
    return [FileChange(path=str(path), action=action, diff=unified_diff(str(path), before, content))]


def _user_service_mask_preview(params: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    """Preview for user service masking.
    
    Returns (would_run, notes) tuple.
    """
    services = params.get("services", [])
    if isinstance(services, str):
        services = [services]
    services = resolve_user_services(services)
    
    would_run: list[list[str]] = []
    notes: list[str] = []
    
    for svc in services:
        would_run.append(["systemctl", "--user", "mask", svc])
        would_run.append(["systemctl", "--user", "stop", svc])
    
    if services:
        notes.append("This will mask and stop the services for the current user")
        notes.append("Masking prevents services from starting, even on boot")
    
    return would_run, notes


def _list_user_units() -> set[str]:
    units: set[str] = set()
    user_paths = [
        Path("~/.config/systemd/user").expanduser(),
        Path("~/.local/share/systemd/user").expanduser(),
        Path("/etc/systemd/user"),
        Path("/usr/lib/systemd/user"),
        Path("/lib/systemd/user"),
    ]
    for base in user_paths:
        try:
            if not base.exists():
                continue
            for p in base.glob("*.service"):
                units.add(p.name)
        except Exception:
            continue

    try:
        result = run(["systemctl", "--user", "list-unit-files", "--no-legend", "--no-pager"])
    except Exception:
        result = None

    if result and result.returncode == 0:
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if parts:
                units.add(parts[0])

    try:
        live = run(["systemctl", "--user", "list-units", "--all", "--no-legend", "--no-pager"])
    except Exception:
        return units

    if live.returncode != 0:
        return units

    for line in live.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if parts:
            units.add(parts[0])
    return units


def resolve_user_services(services: list[str]) -> list[str]:
    units = _list_user_units()
    resolved: list[str] = []
    for svc in services:
        svc = str(svc).strip()
        if not svc:
            continue
        if any(ch in svc for ch in ("*", "?", "[")):
            matches = sorted(u for u in units if fnmatch.fnmatch(u, svc))
            resolved.extend(matches)
        elif svc in units:
            resolved.append(svc)
    return list(dict.fromkeys(resolved))


def user_unit_exists(unit: str) -> bool:
    """Return True if a user systemd unit file exists."""
    unit = unit.strip()
    if not unit:
        return False
    return unit in _list_user_units()


def _baloo_disable_preview(params: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    """Preview for Baloo (KDE file indexer) disable.
    
    Returns (would_run, notes) tuple.
    """
    would_run: list[list[str]] = []
    notes: list[str] = []
    
    from audioknob_gui.platform.packages import which_command
    cmd = which_command("balooctl")
    if cmd:
        would_run.append([cmd, "disable"])
        notes.append(f"Will disable Baloo file indexer using {Path(cmd).name}")
    else:
        notes.append("balooctl not found (balooctl/balooctl6) - KDE may not be installed")
    
    return would_run, notes


def preview(knob: Any, action: str) -> PreviewItem:
    file_changes: list[FileChange] = []
    would_run: list[list[str]] = []
    would_write: list[dict[str, Any]] = []
    notes: list[str] = []

    if knob.impl is None:
        notes.append("No implementation for this knob yet.")
        return PreviewItem(
            knob_id=knob.id,
            title=knob.title,
            description=knob.description,
            requires_root=bool(knob.requires_root),
            requires_reboot=bool(knob.requires_reboot),
            risk_level=str(knob.risk_level),
            action=action,
            file_changes=[],
            would_run=[],
            would_write=[],
            notes=notes,
        )

    kind = knob.impl.kind
    params = knob.impl.params

    if action == "apply":
        if kind == "pam_limits_audio_group":
            file_changes.extend(_pam_limits_preview(params))
        elif kind == "sysctl_conf":
            file_changes.extend(_sysctl_conf_preview(params))
        elif kind == "systemd_unit_toggle":
            cmds, more_notes = _systemd_unit_preview(params)
            would_run.extend(cmds)
            notes.extend(more_notes)
        elif kind == "rtirq_config":
            changes, cmds = _rtirq_config_preview(params)
            file_changes.extend(changes)
            would_run.extend(cmds)
            notes.append("Writes rtirq config and enables the rtirq service.")
        elif kind == "irq_affinity":
            writes, more_notes = _irq_affinity_preview(params)
            would_write.extend(writes)
            notes.extend(more_notes)
        elif kind == "sysfs_glob_kv":
            would_write.extend(_sysfs_glob_preview(params))
        elif kind == "qjackctl_server_prefix":
            file_changes.extend(_qjackctl_server_prefix_preview(params))
            notes.append("Quit QjackCtl before applying; it rewrites its config on exit.")
            try:
                path_str = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
                cfg = read_config(Path(path_str).expanduser())
                if cfg.server_config_enabled:
                    notes.append("QjackCtl ServerConfig is enabled; it will be disabled so GUI settings are used.")
            except Exception:
                pass
            cpu_cores = params.get("cpu_cores")
            if cpu_cores is not None:
                cpu_cores = normalize_cpu_cores(str(cpu_cores))
                if cpu_cores:
                    notes.append(f"If JACK is running, its CPU affinity will be updated to {cpu_cores}.")
        elif kind == "udev_rule":
            file_changes.extend(_udev_rule_preview(params))
            notes.append("Requires udev reload: udevadm control --reload-rules && udevadm trigger")
        elif kind == "kernel_cmdline":
            changes, more_notes = _kernel_cmdline_preview(params)
            file_changes.extend(changes)
            notes.extend(more_notes)
        elif kind == "power_profile":
            cmds, more_notes = _power_profile_preview(params)
            would_run.extend(cmds)
            notes.extend(more_notes)
        elif kind == "pipewire_conf":
            file_changes.extend(_pipewire_conf_preview(params))
            notes.append("Restart PipeWire to apply: systemctl --user restart pipewire")
        elif kind == "user_service_mask":
            cmds, more_notes = _user_service_mask_preview(params)
            would_run.extend(cmds)
            notes.extend(more_notes)
        elif kind == "baloo_disable":
            cmds, more_notes = _baloo_disable_preview(params)
            would_run.extend(cmds)
            notes.extend(more_notes)
        elif kind == "read_only":
            notes.append("Read-only knob; nothing to apply.")
        else:
            notes.append(f"Unsupported kind: {kind}")

    elif action == "restore":
        notes.append("Restore is transaction-based and uses txid (handled by worker restore command).")
    else:
        notes.append(f"Unknown action: {action}")

    return PreviewItem(
        knob_id=knob.id,
        title=knob.title,
        description=knob.description,
        requires_root=bool(knob.requires_root),
        requires_reboot=bool(knob.requires_reboot),
        risk_level=str(knob.risk_level),
        action=action,
        file_changes=file_changes,
        would_run=would_run,
        would_write=would_write,
        notes=notes,
    )


# Apply/restore primitives used by the worker.

def systemd_disable_now(unit: str) -> dict[str, Any]:
    pre_enabled = run(["systemctl", "is-enabled", unit]).stdout.strip()
    pre_active = run(["systemctl", "is-active", unit]).stdout.strip()

    r = run(["systemctl", "disable", "--now", unit])
    return {
        "kind": "systemd_unit_toggle",
        "unit": unit,
        "pre": {"enabled": pre_enabled, "active": pre_active},
        "result": {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr},
    }


def systemd_enable_now(unit: str, start: bool = True) -> dict[str, Any]:
    """Enable a systemd unit, optionally starting it immediately."""
    pre_enabled = run(["systemctl", "is-enabled", unit]).stdout.strip()
    pre_active = run(["systemctl", "is-active", unit]).stdout.strip()

    if start:
        r = run(["systemctl", "enable", "--now", unit])
    else:
        r = run(["systemctl", "enable", unit])
    return {
        "kind": "systemd_unit_toggle",
        "unit": unit,
        "pre": {"enabled": pre_enabled, "active": pre_active},
        "result": {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr},
    }


def systemd_restore(effect: dict[str, Any]) -> None:
    unit = str(effect["unit"])
    pre = effect.get("pre", {})
    pre_enabled = str(pre.get("enabled", ""))
    pre_active = str(pre.get("active", ""))

    if pre_enabled == "enabled":
        run(["systemctl", "enable", unit])
    elif pre_enabled == "disabled":
        run(["systemctl", "disable", unit])
    elif pre_enabled == "masked":
        run(["systemctl", "mask", unit])

    if pre_active == "active":
        run(["systemctl", "start", unit])
    elif pre_active == "inactive":
        run(["systemctl", "stop", unit])


def _expand_sysfs_globs(glob_spec: str | list[str]) -> list[str]:
    globs = [glob_spec] if isinstance(glob_spec, str) else list(glob_spec)
    matches: list[str] = []
    for g in globs:
        matches.extend(glob.glob(g))

    # Fallback for systems that only expose policy-based cpufreq paths.
    if not matches and any("cpu*/cpufreq/scaling_governor" in g for g in globs):
        matches.extend(glob.glob("/sys/devices/system/cpu/cpufreq/policy*/scaling_governor"))

    return sorted(set(matches))


def write_sysfs_values(glob_pat: str | list[str], value: str) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for p in _expand_sysfs_globs(glob_pat):
        path = Path(p)
        try:
            raw = path.read_text(encoding="utf-8").strip()
            # Some sysfs selectors (e.g. THP) present options like:
            #   "[always] madvise never"
            # Restore should write only the effective token, not the whole line.
            before = None
            if raw:
                toks = raw.split()
                bracketed = [t for t in toks if t.startswith("[") and t.endswith("]")]
                if bracketed:
                    before = bracketed[0].strip("[]")
                else:
                    before = raw
        except Exception:
            before = None
        path.write_text(value + "\n", encoding="utf-8")
        effects.append({"kind": "sysfs_write", "path": p, "before": before, "after": value})
    return effects


def restore_sysfs(effects: list[dict[str, Any]]) -> None:
    for e in effects:
        if e.get("kind") != "sysfs_write":
            continue
        before = e.get("before")
        if before is None:
            continue
        Path(str(e["path"])).write_text(str(before) + "\n", encoding="utf-8")


def restore_irq_affinity(effects: list[dict[str, Any]]) -> None:
    for e in effects:
        if e.get("kind") != "irq_affinity":
            continue
        irq = e.get("irq")
        before = e.get("before")
        if irq is None or before is None:
            continue
        path = Path(f"/proc/irq/{irq}/smp_affinity_list")
        if not path.exists():
            continue
        path.write_text(str(before).strip() + "\n", encoding="utf-8")


def user_service_unmask(services: list[str]) -> None:
    """Unmask user services that were masked."""
    for svc in services:
        run(["systemctl", "--user", "unmask", svc])


def user_service_restore(effect: dict[str, Any]) -> None:
    """Restore user service mask effects safely.

    Supports both legacy format:
      {"services": ["foo.service", ...]}
    and new format:
      {"services": [{"unit": "...", "pre_enabled": "...", "pre_active": "..."}, ...]}
    """
    services = effect.get("services", [])

    # Legacy: list[str]
    if isinstance(services, list) and all(isinstance(x, str) for x in services):
        user_service_unmask([str(x) for x in services])
        return

    if not isinstance(services, list):
        return

    for item in services:
        if not isinstance(item, dict):
            continue
        unit = str(item.get("unit", "")).strip()
        if not unit:
            continue

        pre_enabled = str(item.get("pre_enabled", "")).strip()
        pre_active = str(item.get("pre_active", "")).strip()

        # If it was already masked, don't unmask it.
        if pre_enabled != "masked":
            run(["systemctl", "--user", "unmask", unit])

        # Restore enablement state best-effort (avoid static/indirect etc).
        if pre_enabled == "enabled":
            run(["systemctl", "--user", "enable", unit])
        elif pre_enabled == "disabled":
            run(["systemctl", "--user", "disable", unit])
        elif pre_enabled == "masked":
            run(["systemctl", "--user", "mask", unit])

        # Restore running state best-effort.
        if pre_active == "active":
            run(["systemctl", "--user", "start", unit])
        elif pre_active == "inactive":
            run(["systemctl", "--user", "stop", unit])


def baloo_enable() -> None:
    """Re-enable Baloo file indexer."""
    from audioknob_gui.platform.packages import which_command
    cmd = which_command("balooctl")
    if cmd:
        try:
            # Best-effort: don't block the GUI reset path on balooctl.
            subprocess.Popen(
                [cmd, "enable"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            return


def check_knob_status(knob: Any) -> str:
    """Check if a knob's changes are currently applied.
    
    Returns one of:
    - "applied" - the knob's changes are in effect
    - "not_applied" - the knob's changes are not present
    - "partial" - some but not all changes are applied
    - "unknown" - can't determine status
    - "read_only" - this is a read-only/detection knob
    """
    if not knob.impl:
        return "unknown"
    
    kind = knob.impl.kind
    params = knob.impl.params
    
    if kind == "read_only":
        return "read_only"
    
    if kind == "pam_limits_audio_group":
        path = Path(str(params.get("path", "")))
        wanted_lines = [str(x) for x in params.get("lines", [])]
        if not path.exists():
            return "not_applied"
        content = path.read_text(encoding="utf-8")
        found = sum(1 for line in wanted_lines if line in content)
        if found == len(wanted_lines):
            return "applied"
        elif found > 0:
            return "partial"
        return "not_applied"
    
    if kind == "sysctl_conf":
        path = Path(str(params.get("path", "")))
        wanted_lines = [str(x) for x in params.get("lines", [])]
        if not path.exists():
            return "not_applied"
        content = path.read_text(encoding="utf-8")
        found = sum(1 for line in wanted_lines if line in content)
        if found == len(wanted_lines):
            return "applied"
        elif found > 0:
            return "partial"
        return "not_applied"

    if kind == "power_profile":
        backend = detect_power_profile_backend()
        if not backend:
            return "not_applicable"
        current = read_power_profile(backend["backend"], backend["cmd"])
        if current is None:
            return "unknown"
        if backend["backend"] == "powerprofilesctl":
            expected = str(params.get("ppd_profile", "performance")).strip() or "performance"
        else:
            expected = str(params.get("tuned_profile", "latency-performance")).strip() or "latency-performance"
        return "applied" if current == expected else "not_applied"

    if kind == "rtirq_config":
        from audioknob_gui.core.rtirq import normalize_rtirq_list, rtirq_block_present

        distro_id = read_os_release().get("ID", "")
        cfg_path = resolve_rtirq_config_path(distro_id)
        path = Path(cfg_path)

        name_list = normalize_rtirq_list(params.get("name_list", ["snd", "usb"]))
        high_list = normalize_rtirq_list(params.get("high_list", name_list))
        prio_high = int(params.get("prio_high", 90))
        prio_decr = int(params.get("prio_decr", 5))

        cfg_ok = False
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                cfg_ok = rtirq_block_present(
                    content,
                    name_list=name_list,
                    high_list=high_list,
                    prio_high=prio_high,
                    prio_decr=prio_decr,
                )
            except Exception:
                cfg_ok = False

        unit = str(params.get("unit", "rtirq.service"))
        service_ok = False
        service_partial = False
        try:
            enabled_result = run(["systemctl", "is-enabled", unit])
            enabled_msg = (enabled_result.stderr or enabled_result.stdout or "").strip()
            enabled = enabled_result.stdout.strip() or enabled_msg
            if "not-found" in enabled_msg.lower() or "not found" in enabled_msg.lower():
                return "not_applicable"
            active = run(["systemctl", "is-active", unit]).stdout.strip()
            if enabled in ("enabled", "static", "indirect"):
                service_ok = active == "active"
                service_partial = active not in ("", "active")
            elif enabled in ("disabled", "masked"):
                service_ok = False
            else:
                service_partial = True
        except Exception:
            service_partial = True

        if cfg_ok and service_ok:
            return "applied"
        if cfg_ok or service_ok or service_partial:
            return "partial"
        return "not_applied"

    if kind == "irq_affinity":
        from audioknob_gui.core.irq import (
            collect_target_irqs,
            list_irqs,
            parse_cpu_list,
            read_irq_affinity_list,
            resolve_selected_devices,
        )

        device_keys = params.get("device_keys") or []
        cpu_cores = str(params.get("cpu_cores", "")).strip()
        if not device_keys or not cpu_cores:
            return "not_applied"

        expected_set = parse_cpu_list(cpu_cores)
        if not expected_set:
            return "not_applied"

        selected, missing = resolve_selected_devices(device_keys)
        if not selected:
            return "not_applied"

        target_irqs = collect_target_irqs(selected)
        if not target_irqs:
            return "not_applied"

        matched = 0
        for irq in target_irqs:
            path = Path(f"/proc/irq/{irq}/smp_affinity_list")
            if not path.exists():
                continue
            try:
                current = path.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if parse_cpu_list(current) == expected_set:
                matched += 1

        sweep_ok = True
        housekeeping_raw = str(params.get("housekeeping_cores", "")).strip()
        if housekeeping_raw:
            housekeeping_set = parse_cpu_list(housekeeping_raw) - expected_set
            if housekeeping_set:
                for irq in list_irqs():
                    if irq in target_irqs:
                        continue
                    current = read_irq_affinity_list(irq)
                    if current is None:
                        continue
                    current_set = parse_cpu_list(current)
                    if current_set & expected_set:
                        sweep_ok = False
                        break

        state_path = str(params.get("persist_state_path", "")).strip()
        unit = str(params.get("persist_unit", "")).strip()
        config_ok = False
        service_ok = False
        service_partial = False
        if state_path:
            config_ok = Path(state_path).exists()
        if unit:
            try:
                enabled_result = run(["systemctl", "is-enabled", unit])
                enabled_msg = (enabled_result.stderr or enabled_result.stdout or "").strip()
                enabled = enabled_result.stdout.strip() or enabled_msg
                if "not-found" in enabled_msg.lower() or "not found" in enabled_msg.lower():
                    service_ok = False
                elif enabled in ("enabled", "static", "indirect"):
                    service_ok = True
                elif enabled in ("disabled", "masked"):
                    service_ok = False
                else:
                    service_partial = True
            except Exception:
                service_partial = True

        persistent_ok = (not state_path or config_ok) and (not unit or service_ok) and not service_partial
        if matched == len(target_irqs) and not missing and persistent_ok and sweep_ok:
            return "applied"
        if matched > 0 or missing or config_ok or service_ok or service_partial or not sweep_ok:
            return "partial"
        return "not_applied"
    
    if kind == "systemd_unit_toggle":
        unit = str(params.get("unit", ""))
        action = str(params.get("action", ""))
        if not unit:
            return "unknown"
        try:
            result = run(["systemctl", "is-enabled", unit])
            msg = (result.stderr or result.stdout or "").strip()
            msg_lower = msg.lower()
            if "not-found" in msg_lower or "not found" in msg_lower or "no such file" in msg_lower:
                return "not_applicable"
            is_enabled = result.stdout.strip() or msg
            if not is_enabled:
                return "unknown"
            is_enabled = is_enabled.strip()
            # systemctl is-enabled can return many values:
            # enabled, disabled, masked, static, indirect, generated, linked, etc.
            if action in ("disable_now", "disable"):
                # "disabled" or "masked" means the service won't start
                if is_enabled in ("disabled", "masked"):
                    return "applied"
                # "static" means no [Install] section, can't be enabled/disabled
                # "indirect" means enabled via another unit
                # "enabled" means explicitly enabled
                if is_enabled in ("enabled", "static", "indirect", "generated", "linked"):
                    return "not_applied"
                # If unit doesn't exist or unknown state
                return "unknown"
            elif action in ("enable_now", "enable"):
                if is_enabled in ("enabled", "static", "indirect"):
                    return "applied"
                if is_enabled in ("disabled", "masked"):
                    return "not_applied"
                return "unknown"
        except Exception:
            pass
        return "unknown"
    
    if kind == "sysfs_glob_kv":
        glob_pat = str(params.get("glob", ""))
        wanted = str(params.get("value", ""))
        matches = _expand_sysfs_globs(glob_pat)
        if not matches:
            return "not_applicable"
        applied_count = 0
        saw_selector = False
        for p in matches:
            try:
                content = Path(p).read_text(encoding="utf-8").strip()
                # Handle selector format like "always [madvise] never"
                # The bracketed token indicates current selection and can be anywhere
                current = None
                if "[" in content and "]" in content:
                    # Extract the bracketed token (e.g., "[madvise]" -> "madvise")
                    import re
                    match = re.search(r'\[([^\]]+)\]', content)
                    if match:
                        current = match.group(1)
                        saw_selector = True
                else:
                    # Plain value (no selector format)
                    current = content
                
                if current == wanted:
                    applied_count += 1
            except Exception:
                pass
        if applied_count == len(matches):
            base = "applied"
        elif applied_count > 0:
            base = "partial"
        else:
            base = "not_applied"

        # Special case: persistent CPU governor should also be persisted in cpupower config + service.
        if knob.id == "cpu_governor_performance_persistent":
            if base != "applied":
                return base

            os_release = read_os_release()
            distro_id = os_release.get("ID", "")
            cfg_path = resolve_cpupower_config_path(distro_id)
            cfg_ok = False
            try:
                text = Path(cfg_path).read_text(encoding="utf-8")
                # Accept GOV...="performance" or GOV...=performance
                import re
                cfg_ok = re.search(r'^\s*GOVERNOR\s*=\s*"?performance"?\s*$', text, flags=re.MULTILINE) is not None
            except Exception:
                cfg_ok = False

            svc_ok = False
            try:
                r = run(["systemctl", "is-enabled", "cpupower.service"])
                svc_ok = r.stdout.strip() in ("enabled", "static", "indirect")
            except Exception:
                svc_ok = False

            if cfg_ok and svc_ok:
                return "applied"
            return "partial"

        return base
    
    if kind == "qjackctl_server_prefix":
        path = Path(str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))).expanduser()
        if not path.exists():
            return "not_applied"
        try:
            cfg = read_config(path)
            cmd = cfg.server_cmd or ""
            rt_cfg = cfg.realtime
            prio_cfg = cfg.priority
            if not cmd:
                return "not_applied"
            tokens = cmd.split()
            ensure_rt = bool(params.get("ensure_rt", True))
            ensure_prio = bool(params.get("ensure_priority", False))
            cpu_cores = params.get("cpu_cores")
            if cpu_cores is not None:
                cpu_cores = normalize_cpu_cores(str(cpu_cores))

            rt_summary = _jackd_rt_summary()
            runtime_rt = None
            runtime_prio = None
            expected_prio = 90 if ensure_prio else None
            if rt_summary is not None:
                runtime_rt = rt_summary["rt_threads"] > 0
                if ensure_prio:
                    if rt_summary["rt_priorities"]:
                        runtime_prio = expected_prio in rt_summary["rt_priorities"]
                    else:
                        runtime_prio = False

            rt_ok = True
            if ensure_rt:
                if runtime_rt is not None:
                    rt_ok = runtime_rt
                else:
                    rt_ok = (
                        any(t in ("-R", "--realtime") or t.startswith("--realtime") for t in tokens)
                        or rt_cfg is True
                    )

            prio_ok = True
            if ensure_prio:
                if runtime_prio is not None:
                    prio_ok = runtime_prio
                else:
                    prio_ok = any(t.startswith("-P") for t in tokens) or prio_cfg == expected_prio

            pin_ok = True
            if cpu_cores is not None:
                config_pin_ok = True
                if cpu_cores == "":
                    config_pin_ok = not cfg.post_startup_enabled and not cfg.post_startup_shell
                else:
                    expected_script = build_post_start_script(cpu_cores)
                    expected_path = str(default_post_start_script_path())
                    config_pin_ok = cfg.post_startup_enabled and cfg.post_startup_shell == expected_path
                    if config_pin_ok:
                        try:
                            script_text = Path(expected_path).read_text(encoding="utf-8")
                            config_pin_ok = script_text == expected_script
                        except Exception:
                            config_pin_ok = False
                runtime_ok = None
                if cpu_cores:
                    runtime_ok = _jackd_affinity_matches(cpu_cores)
                pin_ok = config_pin_ok
                if runtime_ok is False:
                    pin_ok = False

            if rt_ok and prio_ok and pin_ok:
                if cfg.server_config_enabled:
                    return "partial"
                return "applied"
            if rt_ok or prio_ok or pin_ok:
                return "partial"
            return "not_applied"
        except Exception:
            return "unknown"
    
    if kind == "udev_rule":
        path = Path(str(params.get("path", "")))
        if not path.exists():
            return "not_applied"
        # Check if file has expected content
        content = params.get("content", "")
        try:
            current = path.read_text(encoding="utf-8")
            if content.strip() in current:
                return "applied"
        except Exception:
            pass
        return "not_applied"
    
    if kind == "kernel_cmdline":
        param = str(params.get("param", ""))
        if not param:
            return "unknown"
        
        def _param_in_tokens(p: str, tokens: list[str]) -> bool:
            """Check if param is present in token list."""
            for token in tokens:
                if token == p:
                    return True
                # Handle param=value form
                if "=" in p:
                    param_key = p.split("=")[0]
                    if token.startswith(param_key + "=") and token == p:
                        return True
            return False
        
        try:
            # Check current running kernel cmdline
            cmdline = Path("/proc/cmdline").read_text(encoding="utf-8")
            running_tokens = cmdline.split()
            in_running = _param_in_tokens(param, running_tokens)
            
            # Check boot config file (what will be active after reboot)
            distro = detect_distro()
            in_boot_config = False
            if distro.kernel_cmdline_file:
                try:
                    boot_content = Path(distro.kernel_cmdline_file).read_text(encoding="utf-8")
                    # For BLS/systemd-boot style (single line)
                    if distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                        boot_tokens = boot_content.strip().split()
                        in_boot_config = _param_in_tokens(param, boot_tokens)
                    # For GRUB2 style (GRUB_CMDLINE_LINUX_DEFAULT="...")
                    elif distro.boot_system == "grub2":
                        import shlex
                        for line in boot_content.splitlines():
                            if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                                _, _, rhs = line.partition("=")
                                rhs = rhs.strip().strip('"')
                                try:
                                    boot_tokens = shlex.split(rhs)
                                except Exception:
                                    boot_tokens = rhs.split()
                                in_boot_config = _param_in_tokens(param, boot_tokens)
                                break
                except Exception:
                    pass
            
            # Determine status based on both checks
            if in_running and in_boot_config:
                return "applied"
            if in_running and not in_boot_config:
                # Removed from boot config but still active until reboot
                return "pending_reboot"
            if in_boot_config and not in_running:
                # Added to boot config but not active until reboot
                return "pending_reboot"
            return "not_applied"
        except Exception:
            return "unknown"
    
    if kind == "pipewire_conf":
        path_str = str(params.get("path", "~/.config/pipewire/pipewire.conf.d/99-audioknob.conf"))
        path = Path(path_str).expanduser()
        if not path.exists():
            return "not_applied"
        # File exists, check for our settings
        try:
            content = path.read_text(encoding="utf-8")
            quantum = params.get("quantum")
            rate = params.get("rate")
            found = 0
            expected = 0
            if quantum:
                expected += 1
                if f"default.clock.quantum = {quantum}" in content:
                    found += 1
            if rate:
                expected += 1
                if f"default.clock.rate = {rate}" in content:
                    found += 1
            if expected == 0:
                return "unknown"
            if found == expected:
                return "applied"
            elif found > 0:
                return "partial"
            return "not_applied"
        except Exception:
            return "unknown"
    
    if kind == "user_service_mask":
        services = params.get("services", [])
        if isinstance(services, str):
            services = [services]
        if not services:
            return "unknown"

        existing = resolve_user_services(services)
        if not existing:
            return "not_applicable"

        masked_count = 0
        for svc in existing:
            try:
                result = run(["systemctl", "--user", "is-enabled", svc])
                if result.stdout.strip() == "masked":
                    masked_count += 1
            except Exception:
                pass
        
        if masked_count == len(existing):
            return "applied"
        elif masked_count > 0:
            return "partial"
        return "not_applied"
    
    if kind == "baloo_disable":
        # Check if Baloo is disabled
        from audioknob_gui.platform.packages import which_command
        cmd = which_command("balooctl")
        if not cmd:
            return "unknown"
        try:
            result = run([cmd, "status"], timeout=5)
            # balooctl6 may write status to stderr; include both.
            out = (result.stdout + "\n" + result.stderr).lower()
            if "disabled" in out or "not running" in out or "stopped" in out:
                return "applied"
            if "enabled" in out or "running" in out:
                return "not_applied"
            if result.returncode != 0:
                return "unknown"
            return "not_applied"
        except Exception:
            return "unknown"
    
    if kind == "group_membership":
        # Check if user is in the required audio groups
        import grp
        import os
        import pwd
        
        groups_to_check = params.get("groups", ["audio", "realtime"])
        if isinstance(groups_to_check, str):
            groups_to_check = [groups_to_check]
        
        try:
            user_gids = set(os.getgroups())
            user_name = pwd.getpwuid(os.getuid()).pw_name
            in_count = 0
            configured_count = 0
            exist_count = 0
            
            for group_name in groups_to_check:
                try:
                    gr = grp.getgrnam(group_name)
                    exist_count += 1
                    if gr.gr_gid in user_gids:
                        in_count += 1
                    # Check configured membership even if session doesn't have it yet.
                    if user_name in gr.gr_mem or gr.gr_gid == os.getgid():
                        configured_count += 1
                except KeyError:
                    # Group doesn't exist on this system - skip it
                    pass
            
            if exist_count == 0:
                # No required groups exist on this system
                return "unknown"
            
            if in_count == exist_count:
                return "applied"
            if configured_count == exist_count:
                return "pending_reboot"
            if in_count > 0 or configured_count > 0:
                return "partial"
            return "not_applied"
        except Exception:
            return "unknown"
    
    return "unknown"

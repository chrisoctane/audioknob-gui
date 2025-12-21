from __future__ import annotations

import glob
import subprocess
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from audioknob_gui.core.diffutil import unified_diff
from audioknob_gui.core.qjackctl import ensure_server_flags, read_config
from audioknob_gui.core.runner import run


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


def detect_distro() -> DistroInfo:
    """Detect distribution and boot system configuration."""
    from audioknob_gui.platform.packages import which_command
    
    # Parse /etc/os-release
    os_release = {}
    try:
        content = Path("/etc/os-release").read_text()
        for line in content.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                os_release[key] = value.strip('"\'')
    except Exception:
        pass
    
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


def _sysfs_glob_preview(params: dict[str, Any]) -> list[dict[str, Any]]:
    g = params["glob"]
    value = str(params["value"])
    matches = _expand_sysfs_globs(g)
    return [{"path": p, "value": value} for p in matches]


def _qjackctl_server_prefix_preview(params: dict[str, Any]) -> list[FileChange]:
    from audioknob_gui.core.qjackctl import ensure_server_has_flags, ensure_server_prefix

    path_str = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
    path = Path(path_str).expanduser()
    ensure_rt = bool(params.get("ensure_rt", True))
    ensure_priority = bool(params.get("ensure_priority", False))
    cpu_cores = params.get("cpu_cores")
    if cpu_cores is not None:
        cpu_cores = str(cpu_cores)

    try:
        cfg = read_config(path)
        before_cmd = cfg.server_cmd or ""
        before_prefix = cfg.server_prefix or ""
        preset = cfg.def_preset or "default"
    except Exception:
        before_cmd = ""
        before_prefix = ""
        preset = "default"

    # Compute what the after command would be (without modifying file)
    after_cmd = ensure_server_has_flags(
        before_cmd or "jackd",
        ensure_rt=ensure_rt,
        ensure_priority=ensure_priority,
        cpu_cores="" if cpu_cores is not None else None,
    )
    after_prefix = ensure_server_prefix(before_prefix, cpu_cores=cpu_cores)

    before = _read_text(str(path))
    # Generate a realistic diff by finding and replacing the Server line
    after_lines = before.splitlines() if before else []
    server_key = f"{preset}\\Server=" if preset else "Server="
    prefix_key = f"{preset}\\ServerPrefix=" if preset else "ServerPrefix="
    found = False
    prefix_found = False
    for i, line in enumerate(after_lines):
        if line.startswith(server_key):
            after_lines[i] = f"{server_key}{after_cmd}"
            found = True
        if line.startswith(prefix_key):
            after_lines[i] = f"{prefix_key}{after_prefix}"
            prefix_found = True
    if not found and preset:
        # Add the line if missing
        if "[Settings]" not in after_lines:
            after_lines.append("[Settings]")
        after_lines.append(f"{server_key}{after_cmd}")
    if not prefix_found and preset:
        if "[Settings]" not in after_lines:
            after_lines.append("[Settings]")
        after_lines.append(f"{prefix_key}{after_prefix}")

    after = "\n".join(after_lines)
    if after and not after.endswith("\n"):
        after += "\n"

    action = "modify" if path.exists() else "create"
    return [FileChange(path=str(path), action=action, diff=unified_diff(str(path), before, after))]


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
    
    would_run: list[list[str]] = []
    notes: list[str] = []
    
    for svc in services:
        would_run.append(["systemctl", "--user", "mask", svc])
        would_run.append(["systemctl", "--user", "stop", svc])
    
    if services:
        notes.append("This will mask and stop the services for the current user")
        notes.append("Masking prevents services from starting, even on boot")
    
    return would_run, notes


def user_unit_exists(unit: str) -> bool:
    """Return True if a user systemd unit file exists."""
    try:
        result = run(["systemctl", "--user", "list-unit-files", unit])
    except Exception:
        return False

    if result.returncode != 0:
        return False

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("UNIT FILE"):
            continue
        parts = line.split()
        if parts and parts[0] == unit:
            return True
    return False


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
        elif kind == "sysfs_glob_kv":
            would_write.extend(_sysfs_glob_preview(params))
        elif kind == "qjackctl_server_prefix":
            file_changes.extend(_qjackctl_server_prefix_preview(params))
        elif kind == "udev_rule":
            file_changes.extend(_udev_rule_preview(params))
            notes.append("Requires udev reload: udevadm control --reload-rules && udevadm trigger")
        elif kind == "kernel_cmdline":
            changes, more_notes = _kernel_cmdline_preview(params)
            file_changes.extend(changes)
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
            run([cmd, "enable"], timeout=30)
        except subprocess.TimeoutExpired:
            # Allow slow or hung balooctl without failing reset.
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

            def _read_os_release_id() -> str:
                try:
                    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
                        if line.startswith("ID="):
                            return line.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception:
                    pass
                return ""

            distro_id = _read_os_release_id()
            cfg_path = "/etc/default/cpufrequtils" if distro_id in ("debian", "ubuntu", "linuxmint", "pop") else "/etc/sysconfig/cpupower"
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
            if not cfg.server_cmd:
                return "not_applied"
            cmd = cfg.server_cmd or ""
            prefix = cfg.server_prefix or ""
            tokens = cmd.split()
            prefix_tokens = prefix.split()
            ensure_rt = bool(params.get("ensure_rt", True))
            ensure_prio = bool(params.get("ensure_priority", False))
            cpu_cores = params.get("cpu_cores")
            if cpu_cores is not None:
                cpu_cores = str(cpu_cores)

            rt_ok = True
            if ensure_rt:
                rt_ok = any(t in ("-R", "--realtime") or t.startswith("--realtime") for t in tokens)

            prio_ok = True
            if ensure_prio:
                prio_ok = any(t.startswith("-P") for t in tokens)

            pin_ok = True
            if cpu_cores is not None:
                if cpu_cores == "":
                    pin_ok = "taskset" not in tokens and "taskset" not in prefix_tokens
                else:
                    pin_ok = False
                    for parts in (prefix_tokens, tokens):
                        for i, tok in enumerate(parts):
                            if tok == "taskset" and i + 2 < len(parts) and parts[i + 1] == "-c":
                                pin_ok = parts[i + 2] == cpu_cores
                                break
                        if pin_ok:
                            break

            if rt_ok and prio_ok and pin_ok:
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
            if in_running:
                return "applied"
            elif in_boot_config:
                # In boot config but not running = pending reboot
                return "pending_reboot"
            else:
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

        existing = [svc for svc in services if user_unit_exists(svc)]
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
        
        groups_to_check = params.get("groups", ["audio", "realtime"])
        if isinstance(groups_to_check, str):
            groups_to_check = [groups_to_check]
        
        try:
            user_gids = set(os.getgroups())
            in_count = 0
            exist_count = 0
            
            for group_name in groups_to_check:
                try:
                    gr = grp.getgrnam(group_name)
                    exist_count += 1
                    if gr.gr_gid in user_gids:
                        in_count += 1
                except KeyError:
                    # Group doesn't exist on this system - skip it
                    pass
            
            if exist_count == 0:
                # No required groups exist on this system
                return "unknown"
            
            if in_count == exist_count:
                return "applied"
            elif in_count > 0:
                return "partial"
            return "not_applied"
        except Exception:
            return "unknown"
    
    return "unknown"

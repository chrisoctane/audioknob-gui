from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from audioknob_gui.core.paths import default_paths
from audioknob_gui.core.audit import log_audit_event
from audioknob_gui.core.transaction import (
    RESET_BACKUP,
    RESET_DELETE,
    RESET_PACKAGE,
    backup_file,
    list_transactions,
    new_tx,
    reset_file_to_default,
    restore_file,
    write_manifest,
)
from audioknob_gui.platform.detect import dump_detect
from audioknob_gui.registry import load_registry
from audioknob_gui.worker.ops import (
    check_knob_status,
    preview,
    restore_sysfs,
    systemd_restore,
    user_unit_exists,
)


def _setup_worker_logging() -> logging.Logger:
    is_root = os.geteuid() == 0
    paths = default_paths()
    base = Path(paths.var_lib_dir) if is_root else Path(paths.user_state_dir)
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "worker.log"

    logger = logging.getLogger("audioknob.worker")
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    logger.info("start euid=%s argv=%s", os.geteuid(), " ".join(sys.argv))
    return logger


def _log_audit_event(action: str, payload: dict[str, Any]) -> None:
    logger = logging.getLogger("audioknob.worker")
    log_audit_event(logger, action, payload)


def _require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("This command must run as root (use pkexec).")


def _registry_default_path() -> str:
    from audioknob_gui.core.paths import get_registry_path
    return get_registry_path()


def _load_gui_state() -> dict:
    """Best-effort load of GUI state.json (user-scope)."""
    paths = default_paths()
    p = Path(paths.user_state_dir) / "state.json"
    try:
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _qjackctl_cpu_cores_override(state: dict) -> str | None:
    """Return comma-separated cpu list for taskset, or None if unset."""
    raw = state.get("qjackctl_cpu_cores")
    if raw is None:
        return None
    if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
        if not raw:
            # Explicitly configured as "no pinning"
            return ""
        return ",".join(str(int(x)) for x in raw)
    return None


def _pipewire_quantum_override(state: dict) -> int | None:
    """Return selected PipeWire quantum (buffer size), or None if unset/invalid."""
    raw = state.get("pipewire_quantum")
    if raw is None:
        return None
    try:
        v = int(raw)
    except Exception:
        return None
    if v in (32, 64, 128, 256, 512, 1024):
        return v
    return None


def _pipewire_sample_rate_override(state: dict) -> int | None:
    """Return selected PipeWire sample rate, or None if unset/invalid."""
    raw = state.get("pipewire_sample_rate")
    if raw is None:
        return None
    try:
        v = int(raw)
    except Exception:
        return None
    if v in (44100, 48000, 88200, 96000, 192000):
        return v
    return None


def cmd_detect(_: argparse.Namespace) -> int:
    print(json.dumps(dump_detect(), indent=2, sort_keys=True))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    state = _load_gui_state()
    qjackctl_override = _qjackctl_cpu_cores_override(state)
    pipewire_quantum = _pipewire_quantum_override(state)
    pipewire_sample_rate = _pipewire_sample_rate_override(state)

    items = []
    for kid in args.knob:
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")

        # Apply per-user overrides from GUI state (non-root knobs)
        if (
            qjackctl_override is not None
            and k.impl is not None
            and k.impl.kind == "qjackctl_server_prefix"
        ):
            new_params = dict(k.impl.params)
            new_params["cpu_cores"] = qjackctl_override
            k = replace(k, impl=replace(k.impl, params=new_params))

        if (
            pipewire_quantum is not None
            and k.id == "pipewire_quantum"
            and k.impl is not None
            and k.impl.kind == "pipewire_conf"
        ):
            new_params = dict(k.impl.params)
            new_params["quantum"] = pipewire_quantum
            k = replace(k, impl=replace(k.impl, params=new_params))

        if (
            pipewire_sample_rate is not None
            and k.id == "pipewire_sample_rate"
            and k.impl is not None
            and k.impl.kind == "pipewire_conf"
        ):
            new_params = dict(k.impl.params)
            new_params["rate"] = pipewire_sample_rate
            k = replace(k, impl=replace(k.impl, params=new_params))

        items.append(preview(k, action=args.action))

    payload = {
        "schema": 1,
        "items": [
            {
                "knob_id": i.knob_id,
                "title": i.title,
                "description": i.description,
                "requires_root": i.requires_root,
                "requires_reboot": i.requires_reboot,
                "risk_level": i.risk_level,
                "action": i.action,
                "file_changes": [
                    {"path": fc.path, "action": fc.action, "diff": fc.diff}
                    for fc in i.file_changes
                ],
                "would_run": i.would_run,
                "would_write": i.would_write,
                "notes": i.notes,
            }
            for i in items
        ],
    }

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_apply_user(args: argparse.Namespace) -> int:
    """Apply non-root knobs (user-scope transactions)."""
    logger = logging.getLogger("audioknob.worker")
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    paths = default_paths()
    tx = new_tx(paths.user_state_dir)

    state = _load_gui_state()
    qjackctl_override = _qjackctl_cpu_cores_override(state)
    pipewire_quantum = _pipewire_quantum_override(state)
    pipewire_sample_rate = _pipewire_sample_rate_override(state)

    backups: list[dict] = []
    effects: list[dict] = []
    applied: list[str] = []

    for kid in args.knob:
        logger.info("apply-user knob=%s", kid)
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")
        if k.requires_root:
            raise SystemExit(f"Knob {kid} requires root; use 'apply' command with pkexec")
        if not k.capabilities.apply:
            continue
        if not k.impl:
            continue

        kind = k.impl.kind
        params = k.impl.params

        if kind == "qjackctl_server_prefix":
            path_str = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
            path = Path(path_str).expanduser()
            backups.append(backup_file(tx, str(path)))

            from audioknob_gui.core.qjackctl import ensure_server_flags

            ensure_rt = bool(params.get("ensure_rt", True))
            ensure_priority = bool(params.get("ensure_priority", False))
            cpu_cores = qjackctl_override if qjackctl_override is not None else params.get("cpu_cores")
            if cpu_cores is not None:
                cpu_cores = str(cpu_cores)

            before, after = ensure_server_flags(
                path, ensure_rt=ensure_rt, ensure_priority=ensure_priority, cpu_cores=cpu_cores
            )

        elif kind == "pipewire_conf":
            import subprocess

            path_str = str(params.get("path", "~/.config/pipewire/pipewire.conf.d/99-audioknob.conf"))
            path = Path(path_str).expanduser()
            backups.append(backup_file(tx, str(path)))
            
            # Build config content
            lines = ["# audioknob-gui PipeWire configuration"]
            quantum = pipewire_quantum if (kid == "pipewire_quantum" and pipewire_quantum is not None) else params.get("quantum")
            rate = pipewire_sample_rate if (kid == "pipewire_sample_rate" and pipewire_sample_rate is not None) else params.get("rate")
            
            if quantum or rate:
                lines.append("context.properties = {")
                if quantum:
                    lines.append(f"    default.clock.quantum = {quantum}")
                    lines.append(f"    default.clock.min-quantum = {quantum}")
                if rate:
                    lines.append(f"    default.clock.rate = {rate}")
                lines.append("}")
            
            content = "\n".join(lines) + "\n"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            # Apply immediately: restart PipeWire user services (best-effort).
            # Avoid failing the whole knob if restart is unsupported on the system.
            try:
                r = subprocess.run(
                    ["systemctl", "--user", "restart", "pipewire.service", "pipewire-pulse.service"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                effects.append(
                    {
                        "kind": "pipewire_restart",
                        "result": {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr},
                    }
                )
            except Exception as e:
                effects.append({"kind": "pipewire_restart", "error": str(e)})

        elif kind == "user_service_mask":
            import subprocess
            
            services = params.get("services", [])
            if isinstance(services, str):
                services = [services]

            existing = [svc for svc in services if user_unit_exists(svc)]
            if not existing:
                raise SystemExit("No matching user services found to mask")

            masked_services: list[dict] = []
            for svc in existing:
                # Capture pre-state so restore doesn't unmask services that were already masked.
                pre_enabled = subprocess.run(
                    ["systemctl", "--user", "is-enabled", svc],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                pre_active = subprocess.run(
                    ["systemctl", "--user", "is-active", svc],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

                # Stop and mask the service
                subprocess.run(["systemctl", "--user", "stop", svc], check=False, capture_output=True)
                result = subprocess.run(["systemctl", "--user", "mask", svc], check=False, capture_output=True)
                if result.returncode == 0:
                    masked_services.append({"unit": svc, "pre_enabled": pre_enabled, "pre_active": pre_active})
            
            if masked_services:
                effects.append({
                    "kind": "user_service_mask",
                    "services": masked_services,
                })

        elif kind == "baloo_disable":
            import shutil
            import subprocess
            
            from audioknob_gui.platform.packages import which_command
            cmd = which_command("balooctl")
            if cmd:
                try:
                    result = subprocess.run([cmd, "disable"], check=False, capture_output=True, text=True, timeout=10)
                except subprocess.TimeoutExpired:
                    raise SystemExit("balooctl disable timed out")
                if result.returncode != 0:
                    err = result.stderr.strip() or result.stdout.strip() or "balooctl disable failed"
                    raise SystemExit(err)
                # Verify state if possible (balooctl6 can write to stderr)
                try:
                    status = subprocess.run([cmd, "status"], check=False, capture_output=True, text=True, timeout=5)
                    out = (status.stdout + "\n" + status.stderr).lower()
                    if "running" in out and "disabled" not in out and "not running" not in out and "stopped" not in out:
                        raise SystemExit("balooctl reports running after disable")
                except subprocess.TimeoutExpired:
                    pass
                effects.append({
                    "kind": "baloo_disable",
                    "result": {"returncode": result.returncode},
                })
            else:
                raise SystemExit("balooctl not found (balooctl/balooctl6) - KDE may not be installed")

        else:
            raise SystemExit(f"Unsupported non-root knob kind: {kind}")

        applied.append(kid)

    manifest = {
        "schema": 1,
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": effects,
    }
    write_manifest(tx, manifest)
    _log_audit_event(
        "apply-user",
        {
            "txid": tx.txid,
            "applied": applied,
            "backups": backups,
            "effects": effects,
            "manifest": str(tx.root / "manifest.json"),
        },
    )

    logger.info("apply-user done txid=%s applied=%s", tx.txid, ",".join(applied))
    print(json.dumps({"schema": 1, "txid": tx.txid, "applied": applied}, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    logger = logging.getLogger("audioknob.worker")
    _require_root()

    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    paths = default_paths()
    tx = new_tx(paths.var_lib_dir)

    effects: list[dict] = []
    backups: list[dict] = []
    applied: list[str] = []
    warnings: list[str] = []
    followups: list[dict] = []

    for kid in args.knob:
        logger.info("apply knob=%s", kid)
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")
        if not k.capabilities.apply:
            continue
        if not k.impl:
            continue

        kind = k.impl.kind
        params = k.impl.params

        if kind == "pam_limits_audio_group":
            path = str(params["path"])
            backups.append(backup_file(tx, path))

            want_lines = [str(x) for x in params.get("lines", [])]
            before = ""
            try:
                before = Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""
            before_lines = before.splitlines()
            after_lines = list(before_lines)
            for line in want_lines:
                if line not in after_lines:
                    after_lines.append(line)
            after = "\n".join(after_lines).rstrip("\n") + "\n"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(after, encoding="utf-8")

        elif kind == "sysctl_conf":
            path = str(params["path"])
            backups.append(backup_file(tx, path))

            want_lines = [str(x) for x in params.get("lines", [])]
            before = ""
            try:
                before = Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""
            before_lines = before.splitlines()
            after_lines = list(before_lines)
            for line in want_lines:
                if line not in after_lines:
                    after_lines.append(line)
            after = "\n".join(after_lines).rstrip("\n") + "\n"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(after, encoding="utf-8")

        elif kind == "systemd_unit_toggle":
            from audioknob_gui.worker.ops import systemd_disable_now, systemd_enable_now

            unit = str(params["unit"])
            action = str(params.get("action", ""))
            if action == "disable_now":
                effects.append(systemd_disable_now(unit))
            elif action == "enable_now":
                effects.append(systemd_enable_now(unit))
            elif action == "enable":
                effects.append(systemd_enable_now(unit, start=False))
            elif action == "disable":
                effects.append(systemd_disable_now(unit))
            else:
                raise SystemExit(f"Unsupported systemd action: {action}")

        elif kind == "sysfs_glob_kv":
            from audioknob_gui.worker.ops import write_sysfs_values

            glob_pat = params["glob"]
            sysfs_effects = write_sysfs_values(glob_pat, str(params["value"]))
            if not sysfs_effects:
                raise SystemExit(f"No sysfs entries found for: {glob_pat}")
            effects.extend(sysfs_effects)

            # Special case: persistent CPU governor requires additional config to survive reboot.
            if kid == "cpu_governor_performance_persistent":
                from audioknob_gui.worker.ops import (
                    read_os_release,
                    resolve_cpupower_config_path,
                    systemd_enable_now,
                )

                distro_id = read_os_release().get("ID", "")
                cfg_path = resolve_cpupower_config_path(distro_id)
                key = "GOVERNOR"

                backups.append(backup_file(tx, cfg_path))

                before = ""
                try:
                    before = Path(cfg_path).read_text(encoding="utf-8")
                except FileNotFoundError:
                    before = ""

                lines = before.splitlines()
                out_lines: list[str] = []
                replaced = False
                for line in lines:
                    if line.strip().startswith(key + "="):
                        out_lines.append(f'{key}="performance"')
                        replaced = True
                    else:
                        out_lines.append(line)
                if not replaced:
                    if out_lines and out_lines[-1].strip() != "":
                        out_lines.append("")
                    out_lines.append('# Added by audioknob-gui (persistent CPU governor)')
                    out_lines.append(f'{key}="performance"')

                after = "\n".join(out_lines).rstrip("\n") + "\n"
                Path(cfg_path).parent.mkdir(parents=True, exist_ok=True)
                Path(cfg_path).write_text(after, encoding="utf-8")

                # Best-effort: ensure cpupower.service is enabled so setting persists.
                effects.append(systemd_enable_now("cpupower.service"))

        elif kind == "udev_rule":
            path = str(params["path"])
            content = str(params["content"])
            backups.append(backup_file(tx, path))
            
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content.rstrip("\n") + "\n", encoding="utf-8")
            
            # Reload udev rules
            import subprocess
            subprocess.run(["udevadm", "control", "--reload-rules"], check=False)
            subprocess.run(["udevadm", "trigger"], check=False)

        elif kind == "kernel_cmdline":
            from audioknob_gui.worker.ops import detect_distro
            
            param = str(params.get("param", ""))
            if not param:
                raise SystemExit("No kernel parameter specified")
            
            distro = detect_distro()
            if distro.boot_system == "unknown" or not distro.kernel_cmdline_file:
                raise SystemExit(f"Unknown boot system for {distro.distro_id}; cannot modify kernel cmdline")
            
            cmdline_file = distro.kernel_cmdline_file
            backups.append(backup_file(tx, cmdline_file))
            
            before = ""
            try:
                before = Path(cmdline_file).read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""

            def _tokens_for_existing(before_text: str, boot_system: str) -> list[str]:
                if boot_system in ("grub2-bls", "bls", "systemd-boot"):
                    return before_text.strip().split()
                if boot_system == "grub2":
                    for line in before_text.splitlines():
                        if not line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                            continue
                        _, _, rhs = line.partition("=")
                        rhs = rhs.strip()
                        if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                            rhs = rhs[1:-1]
                        try:
                            return shlex.split(rhs)
                        except Exception:
                            return rhs.split()
                    return []
                return before_text.strip().split()

            def _param_present(param_str: str, tokens: list[str]) -> bool:
                if not param_str:
                    return False
                if "=" in param_str:
                    return any(t == param_str for t in tokens)
                return any(t == param_str or t.startswith(param_str + "=") for t in tokens)

            tokens = _tokens_for_existing(before, distro.boot_system)
            if _param_present(param, tokens):
                # Already present, skip
                pass
            elif distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                # BLS style: single line file
                after = before.strip() + " " + param + "\n" if before.strip() else param + "\n"
                Path(cmdline_file).parent.mkdir(parents=True, exist_ok=True)
                Path(cmdline_file).write_text(after, encoding="utf-8")
            elif distro.boot_system == "grub2":
                # GRUB2 style: modify GRUB_CMDLINE_LINUX_DEFAULT
                before_lines = before.splitlines() if before else []
                after_lines = list(before_lines)
                found = False
                for i, line in enumerate(after_lines):
                    if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                        if '="' in line and line.rstrip().endswith('"'):
                            after_lines[i] = line.rstrip()[:-1] + " " + param + '"'
                        else:
                            after_lines[i] = line.rstrip() + " " + param
                        found = True
                        break
                if not found:
                    after_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{param}"')
                after = "\n".join(after_lines)
                if after and not after.endswith("\n"):
                    after += "\n"
                Path(cmdline_file).write_text(after, encoding="utf-8")
            
            # Run bootloader update command
            if distro.kernel_cmdline_update_cmd:
                import subprocess
                result = subprocess.run(distro.kernel_cmdline_update_cmd, capture_output=True, text=True)
                effects.append({
                    "kind": "kernel_cmdline",
                    "param": param,
                    "file": cmdline_file,
                    "update_cmd": distro.kernel_cmdline_update_cmd,
                    "result": {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
                })
                if result.returncode != 0:
                    cmd_str = " ".join(distro.kernel_cmdline_update_cmd)
                    detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                    warnings.append(
                        "Bootloader update failed for kernel cmdline.\n"
                        f"Command: {cmd_str}\n"
                        f"Error: {detail}\n"
                        "Run the command manually and reboot."
                    )
                    followups.append({
                        "label": f"Run: {cmd_str}",
                        "cmd": distro.kernel_cmdline_update_cmd,
                    })
            elif distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                warnings.append(
                    "Kernel cmdline updated but no bootloader update command is configured.\n"
                    "Run sdbootutil update-all-entries and reboot."
                )
                followups.append({
                    "label": "Run: sdbootutil update-all-entries",
                    "cmd": ["sdbootutil", "update-all-entries"],
                })
            elif distro.boot_system == "grub2":
                warnings.append(
                    "Kernel cmdline updated but no bootloader update command is configured.\n"
                    "Run grub2-mkconfig -o /boot/grub2/grub.cfg (or your distro's update-grub) and reboot."
                )
                followups.append({
                    "label": "Run: grub2-mkconfig -o /boot/grub2/grub.cfg",
                    "cmd": ["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"],
                })

        elif kind == "read_only":
            pass
        else:
            raise SystemExit(f"Unsupported knob kind: {kind}")

        applied.append(kid)

    manifest = {
        "schema": 1,
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": effects,
    }
    write_manifest(tx, manifest)
    audit_payload = {
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": effects,
        "manifest": str(tx.root / "manifest.json"),
    }
    if warnings:
        audit_payload["warnings"] = warnings
    if followups:
        audit_payload["followups"] = followups
    _log_audit_event("apply", audit_payload)

    logger.info("apply done txid=%s applied=%s", tx.txid, ",".join(applied))
    result = {"schema": 1, "txid": tx.txid, "applied": applied}
    if warnings:
        result["warnings"] = warnings
    if followups:
        result["followups"] = followups
    print(json.dumps(result, indent=2))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Restore a transaction (root or user-scope)."""
    paths = default_paths()

    # Try root transactions first, then user
    tx_root = Path(paths.var_lib_dir) / "transactions" / args.txid
    manifest_path = tx_root / "manifest.json"
    is_root = manifest_path.exists()

    if not is_root:
        tx_root = Path(paths.user_state_dir) / "transactions" / args.txid
        manifest_path = tx_root / "manifest.json"
        if not manifest_path.exists():
            raise SystemExit(f"Transaction not found: {args.txid}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Restore files (works for both root and user)
    for meta in manifest.get("backups", []):
        restore_file(type("Tx", (), {"root": tx_root})(), meta)

    # Restore effects
    effects = manifest.get("effects", [])
    
    if is_root:
        _require_root()
        sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
        systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]

        restore_sysfs(sysfs)
        for e in systemd:
            systemd_restore(e)
    
    # User-scope effects
    from audioknob_gui.worker.ops import user_service_restore, baloo_enable
    
    for e in effects:
        if e.get("kind") == "user_service_mask":
            user_service_restore(e)
        elif e.get("kind") == "baloo_disable":
            baloo_enable()

    _log_audit_event(
        "restore",
        {
            "txid": args.txid,
            "was_root": is_root,
            "backups": manifest.get("backups", []),
            "effects": effects,
            "manifest": str(manifest_path),
        },
    )
    print(json.dumps({"schema": 1, "restored": args.txid, "was_root": is_root}, indent=2))
    return 0


def cmd_history(_: argparse.Namespace) -> int:
    paths = default_paths()
    tx_dir = Path(paths.var_lib_dir) / "transactions"
    items: list[dict] = []

    if tx_dir.exists():
        for p in sorted(tx_dir.iterdir()):
            if not p.is_dir():
                continue
            mp = p / "manifest.json"
            if mp.exists():
                try:
                    m = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:
                    m = {"schema": 0}
                items.append({"txid": p.name, "manifest": m})
            else:
                items.append({"txid": p.name, "manifest": None})

    print(json.dumps({"schema": 1, "items": items}, indent=2))
    return 0


def cmd_reset_defaults(args: argparse.Namespace) -> int:
    """Reset all audioknob-gui changes to system defaults.
    
    This uses the reset_strategy stored in each backup:
    - Files we created: delete them
    - Package-owned files: restore from package manager
    - User files: restore from our backup
    
    Use --scope to filter:
    - 'user': only user-scope transactions (no root needed); silently skips root txs
    - 'root': only root-scope transactions (needs pkexec); errors if not root
    - 'all': both (default); silently skips root txs if not root (for GUI two-phase use)
    
    The GUI uses two-phase reset: first --scope user, then pkexec --scope root.
    """
    paths = default_paths()
    results: list[dict] = []
    errors: list[str] = []
    scope_filter = getattr(args, "scope", "all")
    
    # Gather transactions based on scope filter
    all_txs = []
    
    if scope_filter in ("root", "all"):
        root_txs = list_transactions(paths.var_lib_dir)
        for tx_info in root_txs:
            tx_info["scope"] = "root"
            all_txs.append(tx_info)
    
    if scope_filter in ("user", "all"):
        user_txs = list_transactions(paths.user_state_dir)
        for tx_info in user_txs:
            tx_info["scope"] = "user"
            all_txs.append(tx_info)
    
    # If running the user phase, also compute whether there is pending root work
    # (for GUI two-phase resets) even when there are no user transactions.
    needs_root_reset = False
    if scope_filter == "user":
        root_txs = list_transactions(paths.var_lib_dir)
        for tx_info in root_txs:
            # Pending files: file still exists
            for meta in tx_info.get("backups", []):
                file_path = meta.get("path", "")
                if file_path and Path(file_path).exists():
                    needs_root_reset = True
                    break
            if needs_root_reset:
                break
            # Pending effects: restorable effects
            for effect in tx_info.get("effects", []):
                kind = effect.get("kind", "")
                if kind in ("sysfs_write", "systemd_unit_toggle"):
                    needs_root_reset = True
                    break
            if needs_root_reset:
                break

    if not all_txs:
        payload = {
            "schema": 1,
            "message": "No transactions found - nothing to reset",
            "reset_count": 0,
            "results": [],
            "errors": [],
            "scope": scope_filter,
            "needs_root_reset": needs_root_reset,
        }
        _log_audit_event(
            "reset-defaults",
            {
                "scope": scope_filter,
                "reset_count": 0,
                "results": [],
                "errors": [],
                "needs_root_reset": needs_root_reset,
            },
        )
        print(json.dumps(payload, indent=2))
        return 0
    
    # Track which files we've already reset (avoid duplicate resets)
    reset_paths: set[str] = set()
    needs_bootloader_update = False
    
    # Process all transactions (newest first - they're already sorted)
    for tx_info in all_txs:
        txid = tx_info["txid"]
        scope = tx_info["scope"]
        backups = tx_info.get("backups", [])
        
        # Check if this is a root transaction and we need root
        if scope == "root" and os.geteuid() != 0:
            # Can't reset root transactions without root privileges
            # Only report as error if scope_filter is "all" (mixed mode)
            # If scope_filter is "root", this is a real error
            if scope_filter == "root":
                errors.append(f"Transaction {txid} needs root; run with pkexec")
            # If scope_filter is "all", we silently skip (GUI will call root separately)
            continue
        
        # Create a Transaction object for backup restore
        from audioknob_gui.core.transaction import Transaction
        tx_root = Path(tx_info["root"])
        tx = Transaction(txid=txid, root=tx_root)
        
        for meta in backups:
            file_path = meta.get("path", "")
            if not file_path or file_path in reset_paths:
                continue
            
            strategy = meta.get("reset_strategy", RESET_BACKUP)
            
            # Check if we need root for package restore
            if strategy == RESET_PACKAGE and os.geteuid() != 0:
                errors.append(f"Need root to restore {file_path} from package")
                continue
            
            success, message = reset_file_to_default(meta, tx)
            results.append({
                "path": file_path,
                "strategy": strategy,
                "success": success,
                "message": message,
            })
            
            if success:
                reset_paths.add(file_path)
            else:
                errors.append(message)
        
        # Handle effects (sysfs, systemd, user services, etc.)
        effects = tx_info.get("effects", [])
        if any(e.get("kind") == "kernel_cmdline" for e in effects):
            needs_bootloader_update = True
        
        if scope == "root" and effects and os.geteuid() == 0:
            sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
            systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]

            try:
                restore_sysfs(sysfs)
                for e in systemd:
                    systemd_restore(e)
                if sysfs or systemd:
                    results.append({
                        "path": "(root effects)",
                        "strategy": "effects",
                        "success": True,
                        "message": f"Restored {len(sysfs)} sysfs + {len(systemd)} systemd effects",
                    })
            except Exception as ex:
                errors.append(f"Failed to restore root effects: {ex}")
        
        # User-scope effects (services, baloo)
        if scope == "user" and effects:
            from audioknob_gui.worker.ops import user_service_restore, baloo_enable
            
            user_effects_restored = 0
            for e in effects:
                try:
                    if e.get("kind") == "user_service_mask":
                        user_service_restore(e)
                        user_effects_restored += 1
                    elif e.get("kind") == "baloo_disable":
                        baloo_enable()
                        user_effects_restored += 1
                except Exception as ex:
                    errors.append(f"Failed to restore user effect: {ex}")
            
            if user_effects_restored:
                results.append({
                    "path": "(user effects)",
                    "strategy": "effects",
                    "success": True,
                    "message": f"Restored {user_effects_restored} user effect(s)",
                })
    
    # Check if there are pending root changes (for informing GUI)
    # Use list-pending semantics: only count files that still exist + restorable effects
    if scope_filter == "user" and not needs_root_reset:
        root_txs = list_transactions(paths.var_lib_dir)
        for tx_info in root_txs:
            # Check for pending files
            for meta in tx_info.get("backups", []):
                file_path = meta.get("path", "")
                if file_path and Path(file_path).exists():
                    needs_root_reset = True
                    break
            if needs_root_reset:
                break
            # Check for restorable effects (sysfs, systemd - not pipewire_restart)
            for effect in tx_info.get("effects", []):
                kind = effect.get("kind", "")
                if kind in ("sysfs_write", "systemd_unit_toggle"):
                    needs_root_reset = True
                    break
            if needs_root_reset:
                break
    
    # If kernel cmdline was reset, update the bootloader so changes stick after reboot.
    if scope_filter in ("root", "all") and os.geteuid() == 0:
        try:
            from audioknob_gui.worker.ops import detect_distro
            distro = detect_distro()
            if distro.kernel_cmdline_file and distro.kernel_cmdline_file in reset_paths:
                needs_bootloader_update = True
            if needs_bootloader_update:
                if distro.kernel_cmdline_update_cmd:
                    result = subprocess.run(
                        distro.kernel_cmdline_update_cmd,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        cmd_str = " ".join(distro.kernel_cmdline_update_cmd)
                        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                        errors.append(
                            "Bootloader update failed after reset.\n"
                            f"Command: {cmd_str}\n"
                            f"Error: {detail}\n"
                            "Run the command manually and reboot."
                        )
                    else:
                        results.append({
                            "path": "(bootloader update)",
                            "strategy": "kernel_cmdline",
                            "success": True,
                            "message": f"Ran: {' '.join(distro.kernel_cmdline_update_cmd)}",
                        })
                elif distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                    errors.append(
                        "Kernel cmdline reset but no bootloader update command is configured.\n"
                        "Run sdbootutil update-all-entries and reboot."
                    )
                elif distro.boot_system == "grub2":
                    errors.append(
                        "Kernel cmdline reset but no bootloader update command is configured.\n"
                        "Run grub2-mkconfig -o /boot/grub2/grub.cfg (or your distro's update-grub) and reboot."
                    )
        except Exception as ex:
            errors.append(f"Bootloader update check failed: {ex}")

    _log_audit_event(
        "reset-defaults",
        {
            "scope": scope_filter,
            "reset_count": len(reset_paths),
            "results": results,
            "errors": errors,
            "needs_root_reset": needs_root_reset,
        },
    )
    print(json.dumps({
        "schema": 1,
        "message": f"Reset {len(reset_paths)} files to system defaults",
        "reset_count": len(reset_paths),
        "results": results,
        "errors": errors,
        "scope": scope_filter,
        "needs_root_reset": needs_root_reset,
    }, indent=2))
    
    return 1 if errors else 0


def cmd_list_changes(_: argparse.Namespace) -> int:
    """List all files/effects modified by audioknob-gui across all transactions."""
    paths = default_paths()

    root_txs = list_transactions(paths.var_lib_dir)
    user_txs = list_transactions(paths.user_state_dir)

    all_files: dict[str, dict] = {}
    all_effects: list[dict] = []
    has_root_effects = False
    has_user_effects = False

    for tx_info in root_txs + user_txs:
        scope = "root" if tx_info in root_txs else "user"
        
        # Collect file backups
        for meta in tx_info.get("backups", []):
            file_path = meta.get("path", "")
            if file_path and file_path not in all_files:
                all_files[file_path] = {
                    "path": file_path,
                    "scope": scope,
                    "txid": tx_info["txid"],
                    "reset_strategy": meta.get("reset_strategy", RESET_BACKUP),
                    "package": meta.get("package"),
                    "we_created": meta.get("we_created", False),
                }
        
        # Collect effects (sysfs, systemd, user services, etc.)
        for effect in tx_info.get("effects", []):
            effect_copy = dict(effect)
            effect_copy["scope"] = scope
            effect_copy["txid"] = tx_info["txid"]
            all_effects.append(effect_copy)
            
            if scope == "root":
                has_root_effects = True
            else:
                has_user_effects = True

    print(json.dumps({
        "schema": 1,
        "files": list(all_files.values()),
        "count": len(all_files),
        "effects": all_effects,
        "effects_count": len(all_effects),
        "has_root_effects": has_root_effects,
        "has_user_effects": has_user_effects,
    }, indent=2))
    return 0


def cmd_list_pending(_: argparse.Namespace) -> int:
    """List files/effects that are still pending reset (files exist, not yet restored).
    
    Unlike list-changes (historical audit), this only shows what CURRENTLY needs resetting.
    Use this for GUI preview of "Reset All".
    """
    paths = default_paths()

    root_txs = list_transactions(paths.var_lib_dir)
    user_txs = list_transactions(paths.user_state_dir)

    pending_files: dict[str, dict] = {}
    pending_effects: list[dict] = []
    has_root_files = False
    has_user_files = False
    has_root_effects = False
    has_user_effects = False

    for tx_info in root_txs + user_txs:
        scope = "root" if tx_info in root_txs else "user"
        
        # Collect file backups - but only if file still exists (or we created it and it's there)
        for meta in tx_info.get("backups", []):
            file_path = meta.get("path", "")
            if not file_path or file_path in pending_files:
                continue
            
            # Check if file still exists (meaning we still need to reset it)
            from pathlib import Path
            p = Path(file_path).expanduser()
            we_created = meta.get("we_created", False)
            
            if we_created:
                # We created this file - only pending if it still exists
                if not p.exists():
                    continue
            else:
                # We modified existing file - check if our backup exists
                # (if backup exists, we can restore; if file is gone, nothing to do)
                tx_root = Path(tx_info["root"])
                backup_key = meta.get("backup_key", "")
                backup_path = tx_root / "backups" / backup_key if backup_key else None
                if backup_path and not backup_path.exists():
                    continue
                if not p.exists():
                    continue
            
            pending_files[file_path] = {
                "path": file_path,
                "scope": scope,
                "txid": tx_info["txid"],
                "reset_strategy": meta.get("reset_strategy", RESET_BACKUP),
                "package": meta.get("package"),
                "we_created": we_created,
            }
            
            if scope == "root":
                has_root_files = True
            else:
                has_user_files = True
        
        # For effects, deduplicate by kind+path. Transactions are newest-first.
        # We keep the OLDEST entry (original "before" state) to restore to true baseline.
        # So we DON'T skip duplicates here; we let later (older) entries overwrite.
        for effect in tx_info.get("effects", []):
            kind = effect.get("kind", "")
            # Skip pipewire_restart - those are just notifications, not reversible
            if kind == "pipewire_restart":
                continue
            
            # For sysfs_write, deduplicate by path - we only need to restore once
            effect_path = effect.get("path", "")
            effect_key = f"{kind}:{effect_path}"
            
            # Find if we already have this effect (from a newer transaction)
            # We want the OLDEST entry (original before state), so replace if found
            existing_idx = next(
                (i for i, e in enumerate(pending_effects)
                 if e.get("kind") == kind and e.get("path") == effect_path),
                None
            )
            
            effect_copy = dict(effect)
            effect_copy["scope"] = scope
            effect_copy["txid"] = tx_info["txid"]
            
            if existing_idx is not None:
                # Replace with older (current) entry to get original before state
                pending_effects[existing_idx] = effect_copy
            else:
                pending_effects.append(effect_copy)
            
            if scope == "root":
                has_root_effects = True
            else:
                has_user_effects = True

    print(json.dumps({
        "schema": 1,
        "files": list(pending_files.values()),
        "count": len(pending_files),
        "effects": pending_effects,
        "effects_count": len(pending_effects),
        "has_root_files": has_root_files,
        "has_user_files": has_user_files,
        "has_root_effects": has_root_effects,
        "has_user_effects": has_user_effects,
    }, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Check current status of all knobs."""
    reg = load_registry(args.registry)

    # Apply per-user overrides so status reflects GUI-configured values.
    state = _load_gui_state()
    qjackctl_override = _qjackctl_cpu_cores_override(state)
    pipewire_quantum = _pipewire_quantum_override(state)
    pipewire_sample_rate = _pipewire_sample_rate_override(state)
    
    statuses = []
    for k in reg:
        if (
            qjackctl_override is not None
            and k.impl is not None
            and k.impl.kind == "qjackctl_server_prefix"
        ):
            new_params = dict(k.impl.params)
            new_params["cpu_cores"] = qjackctl_override
            k = replace(k, impl=replace(k.impl, params=new_params))
        if (
            pipewire_quantum is not None
            and k.id == "pipewire_quantum"
            and k.impl is not None
            and k.impl.kind == "pipewire_conf"
        ):
            new_params = dict(k.impl.params)
            new_params["quantum"] = pipewire_quantum
            k = replace(k, impl=replace(k.impl, params=new_params))
        if (
            pipewire_sample_rate is not None
            and k.id == "pipewire_sample_rate"
            and k.impl is not None
            and k.impl.kind == "pipewire_conf"
        ):
            new_params = dict(k.impl.params)
            new_params["rate"] = pipewire_sample_rate
            k = replace(k, impl=replace(k.impl, params=new_params))
        status = check_knob_status(k)
        statuses.append({
            "knob_id": k.id,
            "title": k.title,
            "status": status,
            "requires_root": k.requires_root,
        })
    
    print(json.dumps({
        "schema": 1,
        "statuses": statuses,
    }, indent=2))
    return 0


def _find_transaction_for_knob(knob_id: str) -> tuple[str | None, dict | None, str | None]:
    """Find the oldest transaction that applied a specific knob.
    
    Returns (txid, manifest, scope) or (None, None, None) if not found.
    """
    paths = default_paths()
    
    # Check root transactions first (oldest first), so restore-knob can restore
    # the original "before" state even if the knob was applied multiple times.
    root_txs = list_transactions(paths.var_lib_dir)
    for tx_info in reversed(root_txs):
        if knob_id in tx_info.get("applied", []):
            manifest_path = Path(tx_info["root"]) / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                return tx_info["txid"], manifest, "root"
    
    # Check user transactions (oldest first) for non-root knobs.
    user_txs = list_transactions(paths.user_state_dir)
    for tx_info in reversed(user_txs):
        if knob_id in tx_info.get("applied", []):
            manifest_path = Path(tx_info["root"]) / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                return tx_info["txid"], manifest, "user"
    
    return None, None, None


def _restore_knob_once(knob_id: str) -> dict:
    txid, manifest, scope = _find_transaction_for_knob(knob_id)
    if not txid or not manifest:
        return {
            "schema": 1,
            "success": False,
            "knob_id": knob_id,
            "error": f"No transaction found for knob: {knob_id}",
        }

    # Check if we need root for this operation
    if scope == "root" and os.geteuid() != 0:
        return {
            "schema": 1,
            "success": False,
            "knob_id": knob_id,
            "error": f"Knob {knob_id} was applied as root; run with pkexec to restore",
        }

    paths = default_paths()
    tx_root = Path(paths.var_lib_dir if scope == "root" else paths.user_state_dir) / "transactions" / txid

    # Create a Transaction object for backup restore
    from audioknob_gui.core.transaction import Transaction
    tx = Transaction(txid=txid, root=tx_root)

    # Restore only the backups from this knob's transaction
    restored = []
    errors = []
    for meta in manifest.get("backups", []):
        success, message = reset_file_to_default(meta, tx)
        if success:
            restored.append(meta["path"])
        else:
            errors.append(message)

    # Also restore effects if present
    effects = manifest.get("effects", [])

    if scope == "root" and os.geteuid() == 0:
        sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
        systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]

        try:
            restore_sysfs(sysfs)
            for e in systemd:
                systemd_restore(e)
            if sysfs or systemd:
                restored.append(f"(effects: {len(sysfs)} sysfs, {len(systemd)} systemd)")
        except Exception as ex:
            errors.append(f"Failed to restore effects: {ex}")

    # User-scope effects
    from audioknob_gui.worker.ops import user_service_restore, baloo_enable

    user_effects_restored = 0
    for e in effects:
        try:
            if e.get("kind") == "user_service_mask":
                user_service_restore(e)
                user_effects_restored += 1
            elif e.get("kind") == "baloo_disable":
                baloo_enable()
                user_effects_restored += 1
        except Exception as ex:
            errors.append(f"Failed to restore user effect: {ex}")

    if user_effects_restored:
        restored.append(f"(user effects: {user_effects_restored})")

    # If kernel cmdline was restored, update the bootloader so changes stick after reboot.
    if scope == "root" and os.geteuid() == 0:
        try:
            from audioknob_gui.worker.ops import detect_distro
            distro = detect_distro()
            needs_bootloader_update = any(e.get("kind") == "kernel_cmdline" for e in effects)
            if distro.kernel_cmdline_file and distro.kernel_cmdline_file in restored:
                needs_bootloader_update = True
            if needs_bootloader_update:
                if distro.kernel_cmdline_update_cmd:
                    result = subprocess.run(
                        distro.kernel_cmdline_update_cmd,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        cmd_str = " ".join(distro.kernel_cmdline_update_cmd)
                        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                        errors.append(
                            "Bootloader update failed after reset.\n"
                            f"Command: {cmd_str}\n"
                            f"Error: {detail}\n"
                            "Run the command manually and reboot."
                        )
                    else:
                        restored.append(f"(bootloader update: {' '.join(distro.kernel_cmdline_update_cmd)})")
                elif distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                    errors.append(
                        "Kernel cmdline reset but no bootloader update command is configured.\n"
                        "Run sdbootutil update-all-entries and reboot."
                    )
                elif distro.boot_system == "grub2":
                    errors.append(
                        "Kernel cmdline reset but no bootloader update command is configured.\n"
                        "Run grub2-mkconfig -o /boot/grub2/grub.cfg (or your distro's update-grub) and reboot."
                    )
        except Exception as ex:
            errors.append(f"Bootloader update check failed: {ex}")

    return {
        "schema": 1,
        "success": len(errors) == 0,
        "knob_id": knob_id,
        "txid": txid,
        "scope": scope,
        "restored": restored,
        "errors": errors,
    }


def cmd_restore_knob(args: argparse.Namespace) -> int:
    """Restore a specific knob to its original state."""
    result = _restore_knob_once(args.knob_id)
    _log_audit_event("restore-knob", result)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


def cmd_restore_many(args: argparse.Namespace) -> int:
    """Restore multiple knobs to their original state."""
    results = []
    restored: list[str] = []
    errors: list[str] = []

    for knob_id in args.knob:
        result = _restore_knob_once(knob_id)
        results.append(result)
        if result.get("success"):
            restored.append(knob_id)
            continue
        if result.get("errors"):
            for err in result["errors"]:
                errors.append(f"{knob_id}: {err}")
        elif result.get("error"):
            errors.append(f"{knob_id}: {result['error']}")
        else:
            errors.append(f"{knob_id}: restore failed")

    success = len(errors) == 0
    payload = {
        "schema": 1,
        "success": success,
        "restored": restored,
        "results": results,
        "errors": errors,
    }
    _log_audit_event("restore-many", payload)
    print(json.dumps(payload, indent=2))
    return 0 if success else 1


def _force_reset_systemd(unit: str, action: str) -> tuple[bool, str]:
    from audioknob_gui.worker.ops import systemd_disable_now, systemd_enable_now

    if action in ("disable_now", "disable"):
        systemd_enable_now(unit, start=True)
        return True, f"Enabled {unit}"
    if action in ("enable_now", "enable"):
        systemd_disable_now(unit)
        return True, f"Disabled {unit}"
    return False, f"Unsupported systemd action: {action}"


def _force_reset_kernel_cmdline(param: str) -> tuple[bool, str]:
    from audioknob_gui.worker.ops import detect_distro

    distro = detect_distro()
    if distro.boot_system == "unknown" or not distro.kernel_cmdline_file:
        return False, "No kernel cmdline file detected"

    path = Path(distro.kernel_cmdline_file)
    try:
        before = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Failed to read {path}: {e}"

    def _remove_param(tokens: list[str]) -> list[str]:
        if not param:
            return tokens
        if "=" in param:
            return [t for t in tokens if t != param]
        return [t for t in tokens if t != param and not t.startswith(param + "=")]

    after = before
    if distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
        tokens = before.strip().split()
        new_tokens = _remove_param(tokens)
        after = " ".join(new_tokens).strip() + ("\n" if before.endswith("\n") or new_tokens else "")
    elif distro.boot_system == "grub2":
        lines = before.splitlines()
        out_lines: list[str] = []
        updated = False
        for line in lines:
            if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                _, _, rhs = line.partition("=")
                rhs = rhs.strip()
                if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                    inner = rhs[1:-1]
                else:
                    inner = rhs
                try:
                    tokens = shlex.split(inner)
                except Exception:
                    tokens = inner.split()
                new_tokens = _remove_param(tokens)
                new_rhs = " ".join(new_tokens)
                out_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{new_rhs}"')
                updated = True
            else:
                out_lines.append(line)
        if not updated:
            return False, "GRUB_CMDLINE_LINUX_DEFAULT not found"
        after = "\n".join(out_lines)
        if after and not after.endswith("\n"):
            after += "\n"
    else:
        return False, f"Unsupported boot system: {distro.boot_system}"

    try:
        path.write_text(after, encoding="utf-8")
    except Exception as e:
        return False, f"Failed to write {path}: {e}"

    if distro.kernel_cmdline_update_cmd:
        try:
            subprocess.run(distro.kernel_cmdline_update_cmd, check=False, capture_output=True, text=True)
        except Exception:
            pass

    return True, f"Removed {param} from {path}"


def cmd_force_reset_knob(args: argparse.Namespace) -> int:
    knob_id = args.knob_id
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}
    k = by_id.get(knob_id)
    if k is None:
        payload = {"schema": 1, "success": False, "error": f"Unknown knob id: {knob_id}", "knob_id": knob_id}
        _log_audit_event("force-reset-knob", payload)
        print(json.dumps(payload, indent=2))
        return 1

    if k.requires_root and os.geteuid() != 0:
        payload = {
            "schema": 1,
            "success": False,
            "error": f"Knob {knob_id} requires root; run with pkexec",
            "knob_id": knob_id,
        }
        _log_audit_event("force-reset-knob", payload)
        print(json.dumps(payload, indent=2))
        return 1

    if not k.impl:
        payload = {"schema": 1, "success": False, "error": "Knob not implemented", "knob_id": knob_id}
        _log_audit_event("force-reset-knob", payload)
        print(json.dumps(payload, indent=2))
        return 1

    kind = k.impl.kind
    params = k.impl.params
    success = False
    message = ""

    if kind == "systemd_unit_toggle":
        unit = str(params.get("unit", ""))
        action = str(params.get("action", ""))
        success, message = _force_reset_systemd(unit, action)
    elif kind == "kernel_cmdline":
        param = str(params.get("param", ""))
        success, message = _force_reset_kernel_cmdline(param)
    else:
        message = f"Force reset not supported for kind: {kind}"

    payload = {
        "schema": 1,
        "success": success,
        "knob_id": knob_id,
        "message": message,
    }
    _log_audit_event("force-reset-knob", payload)
    print(json.dumps(payload, indent=2))
    return 0 if success else 1


def main(argv: list[str] | None = None) -> int:
    logger = _setup_worker_logging()
    p = argparse.ArgumentParser(prog="audioknob-worker")
    p.add_argument("--registry", default=_registry_default_path())

    sub = p.add_subparsers(dest="cmd", required=True)

    sd = sub.add_parser("detect", help="Detect audio stack and devices (read-only)")
    sd.set_defaults(func=cmd_detect)

    sp = sub.add_parser("preview", help="Preview planned changes")
    sp.add_argument("--action", choices=["apply", "restore"], default="apply")
    sp.add_argument("knob", nargs="+")
    sp.set_defaults(func=cmd_preview)

    sa = sub.add_parser("apply", help="Apply root knobs (creates a transaction, requires root)")
    sa.add_argument("knob", nargs="+")
    sa.set_defaults(func=cmd_apply)

    sau = sub.add_parser("apply-user", help="Apply non-root knobs (creates user-scope transaction)")
    sau.add_argument("knob", nargs="+")
    sau.set_defaults(func=cmd_apply_user)

    sr = sub.add_parser("restore", help="Restore a transaction")
    sr.add_argument("txid")
    sr.set_defaults(func=cmd_restore)

    sh = sub.add_parser("history", help="List transactions")
    sh.set_defaults(func=cmd_history)

    srd = sub.add_parser("reset-defaults", help="Reset ALL changes to system defaults")
    srd.add_argument(
        "--scope",
        choices=["user", "root", "all"],
        default="all",
        help="Which scope to reset: 'user' (no root needed), 'root' (needs pkexec), or 'all' (default)",
    )
    srd.set_defaults(func=cmd_reset_defaults)

    slc = sub.add_parser("list-changes", help="List all files modified by audioknob-gui (historical audit)")
    slc.set_defaults(func=cmd_list_changes)

    slp = sub.add_parser("list-pending", help="List files/effects still pending reset (for GUI preview)")
    slp.set_defaults(func=cmd_list_pending)

    sst = sub.add_parser("status", help="Check current status of all knobs")
    sst.set_defaults(func=cmd_status)

    srk = sub.add_parser("restore-knob", help="Restore a specific knob to its original state")
    srk.add_argument("knob_id", help="ID of the knob to restore")
    srk.set_defaults(func=cmd_restore_knob)

    srm = sub.add_parser("restore-many", help="Restore multiple knobs to their original state")
    srm.add_argument("knob", nargs="+", help="IDs of knobs to restore")
    srm.set_defaults(func=cmd_restore_many)

    sfr = sub.add_parser("force-reset-knob", help="Force reset a knob without a transaction")
    sfr.add_argument("knob_id", help="ID of the knob to force reset")
    sfr.set_defaults(func=cmd_force_reset_knob)

    args = p.parse_args(argv)
    try:
        rc = int(args.func(args))
        logger.info("exit rc=%s", rc)
        return rc
    except SystemExit as e:
        logger.error("exit error=%s", e)
        raise
    except Exception:
        logger.exception("unhandled error")
        raise


if __name__ == "__main__":
    raise SystemExit(main())

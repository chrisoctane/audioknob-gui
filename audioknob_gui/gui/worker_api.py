from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _registry_path() -> str:
    from audioknob_gui.core.paths import get_registry_path
    return get_registry_path()


def _pkexec_available() -> bool:
    from shutil import which

    return which("pkexec") is not None


_PKEXEC_CANCELLED = "__PKEXEC_CANCELLED__"


def _is_pkexec_cancel(msg: str) -> bool:
    if not msg:
        return False
    lower = msg.lower()
    if "authentication cancelled" in lower or "authentication canceled" in lower:
        return True
    if "authorization cancelled" in lower or "authorization canceled" in lower:
        return True
    if "not authorized" in lower and "incident has been reported" in lower:
        return True
    return False


def _is_no_transaction_error(msg: str) -> bool:
    return "no transaction found" in (msg or "").lower()


def _is_force_reset_error(msg: str) -> bool:
    lower = (msg or "").lower()
    return "force reset" in lower and ("reset did not" in lower or "did not remove" in lower)


def _worker_log_path(*, is_root: bool) -> str:
    from audioknob_gui.core.paths import default_paths

    paths = default_paths()
    base = Path(paths.var_lib_dir) if is_root else Path(paths.user_state_dir)
    return str(base / "logs" / "worker.log")


def _root_worker_path_candidates() -> list[str]:
    # The polkit policy installs a fixed-path wrapper here by contract.
    return ["/usr/libexec/audioknob-gui-worker"]


def _normalize_repo_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(Path(raw).expanduser().resolve())
    except Exception:
        return str(Path(raw).expanduser())


def _configured_root_worker_repo() -> str:
    dev_conf = Path("/etc/audioknob-gui/dev.conf")
    if not dev_conf.exists():
        return ""
    try:
        lines = dev_conf.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    if not lines:
        return ""
    return _normalize_repo_path(lines[0])


def _ensure_dev_root_worker_alignment() -> None:
    gui_repo = _normalize_repo_path(os.environ.get("AUDIOKNOB_DEV_REPO", ""))
    if not gui_repo:
        return

    worker_repo = _configured_root_worker_repo()
    if worker_repo == gui_repo:
        return

    worker_label = worker_repo or "not configured"
    raise RuntimeError(
        "Repo GUI is running in dev mode, but the privileged worker is not pointed at the same checkout.\n\n"
        f"GUI repo: {gui_repo}\n"
        f"Root worker repo: {worker_label}\n\n"
        "Run this once (system change):\n"
        f"  cd {gui_repo}\n"
        "  sudo ./packaging/install-polkit.sh\n\n"
        "Or install the updated package system-wide before applying root/system knobs."
    )


def _pick_root_worker_path() -> str:
    for p in _root_worker_path_candidates():
        if os.path.isabs(p) and os.path.exists(p) and os.access(p, os.X_OK):
            _ensure_dev_root_worker_alignment()
            return p
    raise RuntimeError(
        "Privileged worker is not installed.\n\n"
        "Install steps (system change):\n"
        "  cd /home/chris/audioknob-gui\n"
        "  sudo ./packaging/install-polkit.sh\n\n"
        "Then ensure the package is installed into system python so root can import it."
    )


def _basename(path_or_cmd: str) -> str:
    return os.path.basename(path_or_cmd.strip())


def _validate_pkexec_command(cmd: list[str]) -> None:
    if not cmd:
        raise RuntimeError("Refused to run empty privileged command")

    tokens = [str(x).strip() for x in cmd]
    first = _basename(tokens[0])
    rest = tokens[1:]
    if not first:
        raise RuntimeError("Refused to run malformed privileged command")

    # Knob/system operations must go through the fixed worker wrapper.
    # Direct pkexec is only allowed for explicit GUI maintenance actions.
    if first == "usermod":
        if len(rest) == 3 and rest[0] == "-aG" and rest[1] and rest[2]:
            return
        if len(rest) == 3 and rest[0] == "-G" and rest[2]:
            return
        raise RuntimeError("Refused privileged usermod command outside group maintenance")

    if first == "gpasswd":
        if len(rest) == 3 and rest[0] == "-d" and rest[1] and rest[2]:
            return
        raise RuntimeError("Refused privileged gpasswd command outside group maintenance")

    if first == "zypper":
        if len(rest) >= 3 and rest[0] == "--non-interactive" and rest[1] == "install":
            return
        if rest == ["--gpg-auto-import-keys", "refresh"]:
            return
        if len(rest) >= 2 and rest[0] == "ar":
            return
        raise RuntimeError("Refused privileged zypper command outside install/repo maintenance")

    if first == "dnf":
        if len(rest) >= 3 and rest[0] == "install" and rest[1] == "-y":
            return
        raise RuntimeError("Refused privileged dnf command outside package install")

    if first == "apt-get":
        if len(rest) >= 3 and rest[0] == "install" and rest[1] == "-y":
            return
        raise RuntimeError("Refused privileged apt-get command outside package install")

    if first == "pacman":
        if len(rest) >= 3 and rest[0] == "-S" and rest[1] == "--noconfirm":
            return
        raise RuntimeError("Refused privileged pacman command outside package install")

    if first == "sdbootutil":
        if rest == ["update-all-entries"]:
            return
        raise RuntimeError("Refused privileged sdbootutil command outside update-all-entries")

    if first == "bootctl":
        if rest == ["update"]:
            return
        raise RuntimeError("Refused privileged bootctl command outside update")

    if first == "update-grub":
        if not rest:
            return
        raise RuntimeError("Refused privileged update-grub command with unexpected arguments")

    if first in ("grub2-mkconfig", "grub-mkconfig"):
        if len(rest) == 2 and rest[0] == "-o" and rest[1].startswith("/boot/"):
            return
        raise RuntimeError("Refused privileged grub-mkconfig command outside /boot/* output targets")

    if first == "systemctl":
        if rest == ["reboot"]:
            return
        raise RuntimeError("Refused privileged systemctl command outside reboot")

    if first == "truncate":
        expected_log = _worker_log_path(is_root=True)
        if len(rest) == 3 and rest[0] in ("-s", "--size") and rest[1] == "0" and rest[2] == expected_log:
            return
        raise RuntimeError("Refused privileged truncate command outside zero-size log clear")

    raise RuntimeError(
        "Refused privileged command outside allowlist. "
        "Use /usr/libexec/audioknob-gui-worker for knob/system operations."
    )


def _run_worker_apply_user(knob_ids: list[str]) -> dict:
    """Apply non-root knobs (no pkexec needed)."""
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "--registry",
        _registry_path(),
        "apply-user",
        *knob_ids,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=False)
        msg = p.stderr.strip() or "worker apply-user failed"
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_apply_pkexec(knob_ids: list[str]) -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = [
        "pkexec",
        worker,
        "--registry",
        _registry_path(),
        "apply",
        *knob_ids,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=True)
        msg = p.stderr.strip() or p.stdout.strip() or "worker apply failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_restore_many_user(knob_ids: list[str]) -> dict:
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "restore-many",
        *knob_ids,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.stdout.strip():
        try:
            data = json.loads(p.stdout)
            if p.returncode != 0:
                return data
            return data
        except Exception:
            pass
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=False)
        msg = p.stderr.strip() or p.stdout.strip() or "worker restore failed"
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_restore_many_pkexec(knob_ids: list[str]) -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = [
        "pkexec",
        worker,
        "restore-many",
        *knob_ids,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.stdout.strip():
        try:
            data = json.loads(p.stdout)
            if p.returncode != 0:
                return data
            return data
        except Exception:
            pass
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=True)
        msg = p.stderr.strip() or p.stdout.strip() or "worker restore failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_restore_pkexec(txid: str) -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = [
        "pkexec",
        worker,
        "restore",
        txid,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=True)
        msg = p.stderr.strip() or p.stdout.strip() or "worker restore failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_restore_user(txid: str) -> dict:
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "restore",
        txid,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=False)
        msg = p.stderr.strip() or p.stdout.strip() or "worker restore failed"
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_history_user() -> dict:
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "history",
        "--scope",
        "user",
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=False)
        msg = p.stderr.strip() or p.stdout.strip() or "worker history failed"
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_history_pkexec() -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = [
        "pkexec",
        worker,
        "history",
        "--scope",
        "root",
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=True)
        msg = p.stderr.strip() or p.stdout.strip() or "worker history failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_force_reset_pkexec(knob_id: str) -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = [
        "pkexec",
        worker,
        "--registry",
        _registry_path(),
        "force-reset-knob",
        knob_id,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=True)
        msg = p.stderr.strip() or p.stdout.strip() or "worker force reset failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_force_reset_user(knob_id: str) -> dict:
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "--registry",
        _registry_path(),
        "force-reset-knob",
        knob_id,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        msg = p.stderr.strip() or p.stdout.strip() or "worker force reset failed"
        raise RuntimeError(msg)
    return json.loads(p.stdout)


def _run_worker_scx_runtime_pkexec(action: str) -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = [
        "pkexec",
        worker,
        "--registry",
        _registry_path(),
        "scx-runtime",
        action,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=True)
        msg = p.stderr.strip() or p.stdout.strip() or "worker scx-runtime failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    return json.loads(p.stdout)


def _run_worker_restore_knob_pkexec(knob_id: str) -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = ["pkexec", worker, "restore-knob", knob_id]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0 and not p.stdout.strip():
        log_path = _worker_log_path(is_root=True)
        msg = p.stderr.strip() or p.stdout.strip() or "worker restore-knob failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    if not p.stdout.strip():
        msg = p.stderr.strip() or "worker restore-knob failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(msg)
    try:
        return json.loads(p.stdout)
    except Exception:
        msg = p.stderr.strip() or p.stdout.strip() or "worker restore-knob parse failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(msg)


def _run_worker_restore_knob_user(knob_id: str) -> dict:
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "restore-knob",
        knob_id,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0 and not p.stdout.strip():
        msg = p.stderr.strip() or p.stdout.strip() or "worker restore-knob failed"
        raise RuntimeError(msg)
    if not p.stdout.strip():
        raise RuntimeError(p.stderr.strip() or "worker restore-knob failed")
    try:
        return json.loads(p.stdout)
    except Exception:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "worker restore-knob parse failed")


def _run_worker_status_user() -> dict:
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "--registry",
        _registry_path(),
        "status",
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0 or not p.stdout.strip():
        msg = p.stderr.strip() or p.stdout.strip() or "worker status failed"
        raise RuntimeError(msg)
    try:
        return json.loads(p.stdout)
    except Exception:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "worker status parse failed")


def _run_worker_status_pkexec() -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = ["pkexec", worker, "--registry", _registry_path(), "status"]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0 or not p.stdout.strip():
        msg = p.stderr.strip() or p.stdout.strip() or "worker status failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(msg)
    try:
        return json.loads(p.stdout)
    except Exception:
        msg = p.stderr.strip() or p.stdout.strip() or "worker status parse failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(msg)


def _run_worker_reset_defaults_user(*, timeout: int = 120) -> dict:
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "reset-defaults",
        "--scope",
        "user",
    ]
    p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if p.stdout.strip():
        try:
            return json.loads(p.stdout)
        except Exception:
            pass
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=False)
        msg = p.stderr.strip() or p.stdout.strip() or "worker reset-defaults failed"
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    raise RuntimeError(p.stderr.strip() or "worker reset-defaults failed")


def _run_worker_reset_defaults_pkexec(*, timeout: int = 300) -> dict:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")

    worker = _pick_root_worker_path()
    argv = [
        "pkexec",
        worker,
        "reset-defaults",
        "--scope",
        "root",
    ]
    p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if p.stdout.strip():
        try:
            return json.loads(p.stdout)
        except Exception:
            pass
    msg = p.stderr.strip() or p.stdout.strip() or "worker reset-defaults failed"
    if _is_pkexec_cancel(msg):
        raise RuntimeError(_PKEXEC_CANCELLED)
    if p.returncode != 0:
        log_path = _worker_log_path(is_root=True)
        raise RuntimeError(f"{msg}\n\nLog: {log_path}")
    raise RuntimeError(msg)


def _run_pkexec_command_capture(
    cmd: list[str], *, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")
    _validate_pkexec_command(cmd)
    argv = ["pkexec", *cmd]
    p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    msg = p.stderr.strip() or p.stdout.strip() or ""
    if _is_pkexec_cancel(msg):
        raise RuntimeError(_PKEXEC_CANCELLED)
    return p


def _run_pkexec_command(cmd: list[str]) -> None:
    p = _run_pkexec_command_capture(cmd)
    if p.returncode != 0:
        msg = p.stderr.strip() or p.stdout.strip() or "command failed"
        raise RuntimeError(msg)

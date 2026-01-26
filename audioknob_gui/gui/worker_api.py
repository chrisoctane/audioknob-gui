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
    # The polkit policy installs a fixed-path wrapper here by default.
    return [
        "/usr/libexec/audioknob-gui-worker",
        "/usr/local/libexec/audioknob-gui-worker",
        # Fallback: if packaged as a normal CLI in PATH.
        "/usr/local/bin/audioknob-worker",
        "/usr/bin/audioknob-worker",
    ]


def _pick_root_worker_path() -> str:
    from shutil import which

    for p in _root_worker_path_candidates():
        if os.path.isabs(p) and os.path.exists(p) and os.access(p, os.X_OK):
            return p
    # Try PATH for audioknob-worker as a last resort.
    w = which("audioknob-worker")
    if w:
        return w
    raise RuntimeError(
        "Privileged worker is not installed.\n\n"
        "Install steps (system change):\n"
        "  cd /home/chris/audioknob-gui\n"
        "  sudo ./packaging/install-polkit.sh\n\n"
        "Then ensure the package is installed into system python so root can import it."
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


def _run_pkexec_command(cmd: list[str]) -> None:
    if not _pkexec_available():
        raise RuntimeError("pkexec not found")
    argv = ["pkexec", *cmd]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        msg = p.stderr.strip() or p.stdout.strip() or "command failed"
        if _is_pkexec_cancel(msg):
            raise RuntimeError(_PKEXEC_CANCELLED)
        raise RuntimeError(msg)

from __future__ import annotations

import html as html_lib
import json
import logging
import os
import re
import subprocess
import sys
import shutil
import glob
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


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


def _state_path() -> Path:
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        d = Path(xdg_state) / "audioknob-gui"
    else:
        d = Path.home() / ".local" / "state" / "audioknob-gui"
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.json"


def _read_git_rev(repo_root: Path) -> str:
    git_dir = repo_root / ".git"
    if git_dir.is_file():
        try:
            line = git_dir.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
        if line.startswith("gitdir:"):
            git_dir = (repo_root / line.split(":", 1)[1].strip()).resolve()
        else:
            return ""
    if not git_dir.is_dir():
        return ""
    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        ref_path = git_dir / ref
        try:
            return ref_path.read_text(encoding="utf-8").strip()[:8]
        except Exception:
            return ""
    return head[:8]


def _git_rev() -> str:
    env_rev = os.environ.get("AUDIOKNOB_GIT_REV", "").strip()
    if env_rev:
        return env_rev[:8]
    repo_env = os.environ.get("AUDIOKNOB_DEV_REPO", "").strip()
    if repo_env:
        rev = _read_git_rev(Path(repo_env))
        if rev:
            return rev
    return _read_git_rev(Path(__file__).resolve().parents[2])


def _app_title() -> str:
    try:
        from audioknob_gui import __version__ as app_version
    except Exception:
        app_version = "unknown"
    rev = _git_rev()
    if rev:
        return f"audioknob-gui v{app_version} (git {rev})"
    return f"audioknob-gui v{app_version}"


_GUI_LOGGER: logging.Logger | None = None


def _get_gui_logger() -> logging.Logger:
    global _GUI_LOGGER
    if _GUI_LOGGER is not None:
        return _GUI_LOGGER

    log_dir = _state_path().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "gui.log"

    logger = logging.getLogger("audioknob.gui")
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    _GUI_LOGGER = logger
    return logger


_AUDIT_LOGGER: logging.Logger | None = None


def _get_audit_logger() -> logging.Logger:
    global _AUDIT_LOGGER
    if _AUDIT_LOGGER is not None:
        return _AUDIT_LOGGER

    log_path = Path(_worker_log_path(is_root=False))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("audioknob.audit")
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    _AUDIT_LOGGER = logger
    return logger


def _log_gui_audit(action: str, payload: dict[str, Any]) -> None:
    from audioknob_gui.core.audit import log_audit_event

    log_audit_event(_get_audit_logger(), action, payload)


def load_state() -> dict:
    p = _state_path()
    default = {
        "schema": 1,
        "last_txid": None,
        "last_user_txid": None,
        "last_root_txid": None,
        "font_size": 11,
        "queued_knobs": [],
        "queued_actions": {},
        # Per-knob UI state
        "qjackctl_cpu_cores": None,  # list[int] or None
        "kernel_isolcpus_cores": None,  # list[int] or None
        "kernel_nohz_full_cores": None,  # list[int] or None
        "kernel_rcu_nocbs_cores": None,  # list[int] or None
        "kernel_irqaffinity_cores": None,  # list[int] or None
        "irq_housekeeping_auto": True,  # bool
        "irq_pinning_devices": [],  # list[str]
        "irq_pinning_cpu_cores": None,  # list[int] or None
        "audio_core_plan_count": 4,  # int
        "audio_core_plan_expanded": True,  # bool
        "view_tab": "all",  # str
        "advanced_mode_enabled": False,  # bool
        "pipewire_quantum": None,  # int (32..1024) or None
        "pipewire_sample_rate": None,  # int (44100/48000/88200/96000/192000) or None
        "power_profile_backend": "auto",  # auto | powerprofilesctl | tuned
        "jitter_test_last": None,  # dict payload from last run or None
        "system_profile": None,  # dict from startup scan or None
        "baseline_statuses": {},  # knob_id -> status string (first-run baseline)
        "baseline_checks": {},  # knob_id -> list[str] lines (first-run snapshot)
        "baseline_captured_at": None,  # ISO timestamp
        "baseline_txid_user": None,  # last_user_txid at capture time
        "baseline_txid_root": None,  # last_root_txid at capture time
        "baseline_source": "initial",  # initial | capture | import
    }
    if not p.exists():
        return default
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # Migrate old state format
        if "last_txid" in data and "last_user_txid" not in data:
            data["last_root_txid"] = data.get("last_txid")
            data["last_user_txid"] = None
        if "font_size" not in data:
            data["font_size"] = 11
        if "qjackctl_cpu_cores" not in data:
            data["qjackctl_cpu_cores"] = None
        if "kernel_isolcpus_cores" not in data:
            data["kernel_isolcpus_cores"] = None
        if "kernel_nohz_full_cores" not in data:
            data["kernel_nohz_full_cores"] = None
        if "kernel_rcu_nocbs_cores" not in data:
            data["kernel_rcu_nocbs_cores"] = None
        if "kernel_irqaffinity_cores" not in data:
            data["kernel_irqaffinity_cores"] = None
        if "irq_housekeeping_auto" not in data:
            manual = data.get("kernel_irqaffinity_cores")
            has_manual = isinstance(manual, list) and any(isinstance(x, int) for x in manual)
            data["irq_housekeeping_auto"] = not has_manual
        if "irq_pinning_devices" not in data:
            data["irq_pinning_devices"] = []
        if "irq_pinning_cpu_cores" not in data:
            data["irq_pinning_cpu_cores"] = None
        if "audio_core_plan_count" not in data:
            data["audio_core_plan_count"] = 4
        if "audio_core_plan_expanded" not in data:
            data["audio_core_plan_expanded"] = True
        if "view_tab" not in data:
            data["view_tab"] = "all"
        if "advanced_mode_enabled" not in data:
            data["advanced_mode_enabled"] = bool(data.get("audio_session_enabled", False))
        data.pop("audio_session_enabled", None)
        data.pop("audio_session_knobs", None)
        if "pipewire_quantum" not in data:
            data["pipewire_quantum"] = None
        if "pipewire_sample_rate" not in data:
            data["pipewire_sample_rate"] = None
        if "power_profile_backend" not in data:
            data["power_profile_backend"] = "auto"
        if "jitter_test_last" not in data:
            data["jitter_test_last"] = None
        if "system_profile" not in data:
            data["system_profile"] = None
        if "baseline_statuses" not in data:
            data["baseline_statuses"] = {}
        if "baseline_checks" not in data:
            data["baseline_checks"] = {}
        if "baseline_captured_at" not in data:
            data["baseline_captured_at"] = None
        if "baseline_txid_user" not in data:
            data["baseline_txid_user"] = None
        if "baseline_txid_root" not in data:
            data["baseline_txid_root"] = None
        if "baseline_source" not in data:
            data["baseline_source"] = "initial"
        if "enable_reboot_knobs" not in data:
            data["enable_reboot_knobs"] = False
        if "queued_knobs" not in data:
            data["queued_knobs"] = []
        if "queued_actions" not in data:
            if isinstance(data.get("queued_knobs"), list):
                data["queued_actions"] = {
                    k: "apply" for k in data["queued_knobs"] if isinstance(k, str)
                }
            else:
                data["queued_actions"] = {}
        if not isinstance(data.get("queued_knobs"), list):
            data["queued_knobs"] = []
        else:
            data["queued_knobs"] = [x for x in data["queued_knobs"] if isinstance(x, str)]
        if not isinstance(data.get("queued_actions"), dict):
            data["queued_actions"] = {}
        else:
            cleaned = {}
            for k, v in data["queued_actions"].items():
                if isinstance(k, str) and v in ("apply", "reset"):
                    cleaned[k] = v
            data["queued_actions"] = cleaned
        if data.get("jitter_test_last") is not None and not isinstance(data.get("jitter_test_last"), dict):
            data["jitter_test_last"] = None
        if data.get("irq_pinning_devices") is not None and not isinstance(data.get("irq_pinning_devices"), list):
            data["irq_pinning_devices"] = []
        else:
            data["irq_pinning_devices"] = [
                str(x) for x in data.get("irq_pinning_devices", []) if isinstance(x, (str, int))
            ]
        if data.get("irq_pinning_cpu_cores") is not None and not isinstance(data.get("irq_pinning_cpu_cores"), list):
            data["irq_pinning_cpu_cores"] = None
        else:
            cores = data.get("irq_pinning_cpu_cores")
            if isinstance(cores, list) and all(isinstance(x, int) for x in cores):
                data["irq_pinning_cpu_cores"] = cores
            else:
                data["irq_pinning_cpu_cores"] = None
        if data.get("audio_core_plan_count") is not None and not isinstance(data.get("audio_core_plan_count"), int):
            data["audio_core_plan_count"] = 4
        if data.get("view_tab") not in ("all", "cores"):
            data["view_tab"] = "all"
        for key in (
            "kernel_isolcpus_cores",
            "kernel_nohz_full_cores",
            "kernel_rcu_nocbs_cores",
            "kernel_irqaffinity_cores",
        ):
            if data.get(key) is not None and not isinstance(data.get(key), list):
                data[key] = None
            else:
                cores = data.get(key)
                if isinstance(cores, list) and all(isinstance(x, int) for x in cores):
                    data[key] = cores
                else:
                    data[key] = None
        if data.get("advanced_mode_enabled") is not None and not isinstance(data.get("advanced_mode_enabled"), bool):
            data["advanced_mode_enabled"] = False
        if data.get("irq_housekeeping_auto") is not None and not isinstance(data.get("irq_housekeeping_auto"), bool):
            data["irq_housekeeping_auto"] = True
        if data.get("system_profile") is not None and not isinstance(data.get("system_profile"), dict):
            data["system_profile"] = None
        if data.get("baseline_statuses") is not None and not isinstance(data.get("baseline_statuses"), dict):
            data["baseline_statuses"] = {}
        if data.get("baseline_checks") is not None and not isinstance(data.get("baseline_checks"), dict):
            data["baseline_checks"] = {}
        if data.get("baseline_txid_user") is not None and not isinstance(data.get("baseline_txid_user"), str):
            data["baseline_txid_user"] = None
        if data.get("baseline_txid_root") is not None and not isinstance(data.get("baseline_txid_root"), str):
            data["baseline_txid_root"] = None
        if data.get("baseline_source") is not None and not isinstance(data.get("baseline_source"), str):
            data["baseline_source"] = "initial"
        if data.get("baseline_source") not in ("initial", "capture", "import"):
            data["baseline_source"] = "initial"
        # Sanitize known UI config values (can be corrupted by older bugs / manual edits).
        try:
            q = data.get("pipewire_quantum")
            qv = int(q) if q is not None else None
            if qv not in (32, 64, 128, 256, 512, 1024):
                data["pipewire_quantum"] = None
        except Exception:
            data["pipewire_quantum"] = None
        try:
            r = data.get("pipewire_sample_rate")
            rv = int(r) if r is not None else None
            if rv not in (44100, 48000, 88200, 96000, 192000):
                data["pipewire_sample_rate"] = None
        except Exception:
            data["pipewire_sample_rate"] = None
        backend = str(data.get("power_profile_backend") or "").strip().lower()
        if backend not in ("auto", "powerprofilesctl", "tuned"):
            data["power_profile_backend"] = "auto"
        return data
    except Exception:
        return default


def save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    try:
        from PySide6.QtCore import Qt, QThread, Signal, QEvent
        from PySide6.QtWidgets import (
            QApplication,
            QAbstractItemView,
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QScrollArea,
            QSizePolicy,
            QSlider,
            QSpinBox,
            QTableWidget,
            QTableWidgetItem,
            QTabBar,
            QTextEdit,
            QToolButton,
            QVBoxLayout,
            QWidget,
        )
        from PySide6.QtGui import QColor, QCursor
        from shiboken6 import isValid
    except Exception as e:  # pragma: no cover
        print(
            "PySide6 is required to run audioknob-gui.\n"
            "Install it into your venv, e.g.:\n"
            "  python -m venv .venv && . .venv/bin/activate\n"
            "  python -m pip install -U pip\n"
            "  python -m pip install -e .\n\n"
            f"Import error: {e}",
            file=sys.stderr,
        )
        return 2

    from audioknob_gui.gui.tests_dialog import jitter_test_summary
    from audioknob_gui.registry import load_registry

    class KnobTaskWorker(QThread):
        finished = Signal(str, str, bool, object, str)

        def __init__(self, knob_id: str, action: str, fn, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._knob_id = knob_id
            self._action = action
            self._fn = fn

        def run(self) -> None:
            try:
                success, payload, message = self._fn()
            except Exception as e:
                success, payload, message = False, None, str(e)
            self.finished.emit(self._knob_id, self._action, bool(success), payload, message or "")

    class QueueTaskWorker(QThread):
        finished = Signal(bool, object, str)

        def __init__(self, fn, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._fn = fn

        def run(self) -> None:
            try:
                success, payload, message = self._fn()
            except Exception as e:
                success, payload, message = False, None, str(e)
            self.finished.emit(bool(success), payload, message or "")

    class ConfirmDialog(QDialog):
        def __init__(self, planned_ids: list[str], parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Confirm queued changes")
            self.resize(520, 150)
            self.ok = False

            root = QVBoxLayout(self)
            root.addWidget(QLabel("<b>Apply these queued changes?</b>"))
            root.addWidget(QLabel("Items: " + ", ".join(planned_ids)))
            root.addWidget(QLabel("<i>You'll be prompted for your password if root access is needed.</i>"))

            btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            btns.accepted.connect(self._on_ok)
            btns.rejected.connect(self.reject)
            root.addWidget(btns)

        def _on_ok(self) -> None:
            self.ok = True
            self.accept()

    class CpuCoreDialog(QDialog):
        def __init__(
            self,
            *,
            cpu_count: int,
            selected: set[int],
            allow_auto: bool = False,
            auto_enabled: bool = False,
            auto_label: str | None = None,
            auto_hint: str | None = None,
            title: str | None = None,
            lines: list[str] | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle(title or "Configure CPU cores for JACK")
            self.resize(520, 320)

            self._cpu_count = max(1, int(cpu_count))
            self._checks: list[QCheckBox] = []
            self._auto_cb: QCheckBox | None = None
            self._auto_hint: QLabel | None = None

            root = QVBoxLayout(self)
            if lines is None:
                lines = [
                    "Select CPU cores to pin JACK to (taskset -c).",
                    "Tip: cores 0-1 are often busiest (IRQs/system tasks).",
                ]
            for line in lines:
                root.addWidget(QLabel(line))

            if allow_auto:
                label = auto_label or "Auto"
                hint = auto_hint or "Auto uses all cores except selected audio cores."
                self._auto_cb = QCheckBox(label)
                self._auto_cb.setChecked(bool(auto_enabled))
                root.addWidget(self._auto_cb)
                self._auto_hint = QLabel(hint)
                self._auto_hint.setWordWrap(True)
                root.addWidget(self._auto_hint)

            grid_wrap = QWidget()
            grid = QGridLayout(grid_wrap)

            cols = 4
            for core in range(self._cpu_count):
                cb = QCheckBox(f"Core {core}")
                cb.setChecked(core in selected)
                self._checks.append(cb)
                grid.addWidget(cb, core // cols, core % cols)

            root.addWidget(grid_wrap)

            btn_row = QHBoxLayout()
            btn_all = QPushButton("Select all")
            btn_none = QPushButton("Clear all")
            btn_row.addWidget(btn_all)
            btn_row.addWidget(btn_none)
            btn_row.addStretch(1)
            root.addLayout(btn_row)

            def _set_all(v: bool) -> None:
                for cb in self._checks:
                    cb.setChecked(v)

            btn_all.clicked.connect(lambda: _set_all(True))
            btn_none.clicked.connect(lambda: _set_all(False))

            if self._auto_cb is not None:
                def _apply_auto(enabled: bool) -> None:
                    for cb in self._checks:
                        cb.setEnabled(not enabled)
                    btn_all.setEnabled(not enabled)
                    btn_none.setEnabled(not enabled)

                self._auto_cb.toggled.connect(_apply_auto)
                _apply_auto(self._auto_cb.isChecked())

            btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            btns.accepted.connect(self.accept)
            btns.rejected.connect(self.reject)
            root.addWidget(btns)

        def selected_cores(self) -> list[int]:
            out: list[int] = []
            for i, cb in enumerate(self._checks):
                if cb.isChecked():
                    out.append(i)
            return out

        def auto_enabled(self) -> bool:
            if self._auto_cb is None:
                return False
            return self._auto_cb.isChecked()

    class IrqPinningDialog(QDialog):
        def __init__(
            self,
            *,
            cpu_count: int,
            selected_cores: set[int],
            devices: list[dict[str, object]],
            selected_devices: set[str],
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle("Configure IRQ pinning")
            self.resize(620, 520)

            self._cpu_count = max(1, int(cpu_count))
            self._core_checks: list[QCheckBox] = []
            self._device_checks: dict[str, QCheckBox] = {}

            root = QVBoxLayout(self)
            root.addWidget(QLabel("Select audio devices to pin their IRQs."))
            root.addWidget(QLabel("USB devices pin the host controller IRQs (shared)."))
            try:
                from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups

                groups = read_thread_sibling_groups()
                if any(len(g) > 1 for g in groups):
                    logical = len(read_cpu_present() or [])
                    physical = len(groups)
                    root.addWidget(
                        QLabel(
                            f"SMT detected: {physical} physical / {logical} logical. "
                            "Select both siblings for best isolation."
                        )
                    )
            except Exception:
                pass

            device_box = QGroupBox("Devices")
            device_layout = QVBoxLayout(device_box)
            device_scroll = QScrollArea()
            device_scroll.setWidgetResizable(True)
            device_container = QWidget()
            device_container_layout = QVBoxLayout(device_container)

            for device in devices:
                key = str(device.get("key"))
                label = str(device.get("label") or key)
                bus = str(device.get("bus") or "unknown")
                irqs = device.get("irqs") or []
                warning = device.get("warning")
                controller = device.get("controller_pci_id")
                driver = device.get("controller_driver")
                extra: list[str] = []
                if controller:
                    ctrl = f"controller {controller}"
                    if driver:
                        ctrl += f" ({driver})"
                    extra.append(ctrl)
                if irqs:
                    extra.append("IRQs: " + ",".join(str(x) for x in irqs))
                if warning:
                    extra.append(f"WARNING: {warning}")

                text = f"{label} [{bus}]"
                if extra:
                    text += " - " + "; ".join(extra)

                cb = QCheckBox(text)
                cb.setChecked(key in selected_devices)
                if not irqs:
                    cb.setEnabled(False)
                    cb.setToolTip("No IRQs detected for this device.")
                self._device_checks[key] = cb
                device_container_layout.addWidget(cb)

            device_container_layout.addStretch(1)
            device_scroll.setWidget(device_container)
            device_layout.addWidget(device_scroll)
            root.addWidget(device_box)

            core_box = QGroupBox("CPU cores")
            core_layout = QVBoxLayout(core_box)
            core_layout.addWidget(QLabel("Select CPU cores to pin IRQs to."))

            grid_wrap = QWidget()
            grid = QGridLayout(grid_wrap)

            cols = 4
            for core in range(self._cpu_count):
                cb = QCheckBox(f"Core {core}")
                cb.setChecked(core in selected_cores)
                self._core_checks.append(cb)
                grid.addWidget(cb, core // cols, core % cols)

            core_layout.addWidget(grid_wrap)

            btn_row = QHBoxLayout()
            btn_all = QPushButton("Select all")
            btn_none = QPushButton("Clear all")
            btn_row.addWidget(btn_all)
            btn_row.addWidget(btn_none)
            btn_row.addStretch(1)
            core_layout.addLayout(btn_row)

            def _set_all(v: bool) -> None:
                for cb in self._core_checks:
                    cb.setChecked(v)

            btn_all.clicked.connect(lambda: _set_all(True))
            btn_none.clicked.connect(lambda: _set_all(False))
            root.addWidget(core_box)

            btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            btns.accepted.connect(self.accept)
            btns.rejected.connect(self.reject)
            root.addWidget(btns)

        def selected_core_list(self) -> list[int]:
            out: list[int] = []
            for i, cb in enumerate(self._core_checks):
                if cb.isChecked():
                    out.append(i)
            return out

        def selected_device_keys(self) -> list[str]:
            out: list[str] = []
            for key, cb in self._device_checks.items():
                if cb.isChecked():
                    out.append(key)
            return out

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            from PySide6.QtCore import QTimer
            self.setWindowTitle(_app_title())
            self.resize(980, 640)

            self._task_threads: list[QThread] = []
            self.state = load_state()
            self.registry = load_registry(_registry_path())
            self._dependency_index = self._build_dependency_index()
            _get_gui_logger().info("gui started")
            self._ensure_system_profile()
            self._baseline_ready = self._baseline_available()
            self._baseline_busy = False
            self._ensure_baseline_state()
            self._queued_actions = self._sanitize_queue_actions(self.state.get("queued_actions"))
            if self._queued_actions != self.state.get("queued_actions"):
                self.state["queued_actions"] = dict(self._queued_actions)
                save_state(self.state)
            self._queue_busy = False
            self._queue_needs_reboot = False
            self._queue_inflight: list[tuple[str, str]] = []
            
            # Apply saved font size
            self._apply_font_size(self.state.get("font_size", 11))

            # Apply modern stylesheet
            self._apply_stylesheet()

            w = QWidget()
            self.setCentralWidget(w)
            root = QVBoxLayout(w)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)

            # Header
            top = QHBoxLayout()
            self.header_layout = top
            self.font_label = QLabel("Font:")
            top.addWidget(self.font_label)
            self.font_spinner = QSpinBox()
            self.font_spinner.setRange(8, 24)
            self.font_spinner.setValue(self.state.get("font_size", 11))
            self.font_spinner.setToolTip("Adjust font size")
            self.font_spinner.valueChanged.connect(self._on_font_change)
            top.addWidget(self.font_spinner)
            top.addStretch(1)

            # Global reboot-required banner (shown when any knob is pending reboot).
            self.reboot_banner = QLabel("")
            self.reboot_banner.setStyleSheet("color: #f57c00; font-weight: bold;")
            self.reboot_banner.setWordWrap(True)
            self.reboot_banner.setVisible(False)

            self.reboot_toggle = QCheckBox("Enable reboot-required changes")
            self.reboot_toggle.setChecked(bool(self.state.get("enable_reboot_knobs", False)))
            self.reboot_toggle.setToolTip("Unlock knobs that require a reboot/log-out to take effect")
            self.reboot_toggle.toggled.connect(self._on_reboot_toggle)
            top.addWidget(self.reboot_toggle)

            self.advanced_toggle = QCheckBox("Enable advanced knobs")
            self.advanced_toggle.setChecked(bool(self.state.get("advanced_mode_enabled", False)))
            self.advanced_toggle.setToolTip("Unlock advanced knobs that can impact system performance")
            self.advanced_toggle.toggled.connect(self._on_advanced_mode_toggle)
            top.addWidget(self.advanced_toggle)

            self.queue_label = QLabel("")
            self.queue_label.setToolTip("Queued changes waiting to apply")
            self.queue_label.setVisible(False)
            top.addWidget(self.queue_label)

            self.btn_apply_queue = QPushButton("Apply")
            self.btn_apply_queue.setToolTip("Apply queued changes")
            self.btn_apply_queue.clicked.connect(
                lambda _checked=False: self._on_apply_queue(reboot_after=False)
            )
            self.btn_apply_queue.setVisible(False)
            top.addWidget(self.btn_apply_queue)

            self.btn_apply_queue_reboot = QPushButton("Apply & Reboot")
            self.btn_apply_queue_reboot.setToolTip("Apply queued changes and reboot after")
            self.btn_apply_queue_reboot.clicked.connect(
                lambda _checked=False: self._on_apply_queue(reboot_after=True)
            )
            self.btn_apply_queue_reboot.setVisible(False)
            top.addWidget(self.btn_apply_queue_reboot)

            self.reboot_button = QPushButton("Reboot")
            self.reboot_button.setToolTip("Restart the system to apply pending changes")
            self.reboot_button.clicked.connect(self._on_reboot_now)
            self.reboot_button.setVisible(False)
            top.addWidget(self.reboot_button)

            self.btn_recheck = QPushButton("Re-check State")
            self.btn_recheck.setToolTip("Re-scan current system state")
            self.btn_recheck.clicked.connect(self._on_recheck_state)
            top.addWidget(self.btn_recheck)

            self.btn_logs = QPushButton("Logs")
            self.btn_logs.setToolTip("Open logs for copy/paste")
            self.btn_logs.clicked.connect(self._on_show_logs)
            top.addWidget(self.btn_logs)

            self.btn_tx_history = QPushButton("Tx History")
            self.btn_tx_history.setToolTip("View transactions (txid) and restore")
            self.btn_tx_history.clicked.connect(self._on_show_tx_history)
            top.addWidget(self.btn_tx_history)

            self.btn_reset = QPushButton("Reset All")
            self.btn_reset.setToolTip("Reset all changes to system defaults")
            self.btn_reset.setEnabled(self._baseline_ready)
            top.addWidget(self.btn_reset)
            root.addLayout(top)
            root.addWidget(self.reboot_banner)

            advanced_note = QLabel(
                "Advanced settings can reduce performance in intensive workloads. "
                "Enable advanced knobs to make changes; reboot may be required."
            )
            advanced_note.setWordWrap(True)
            root.addWidget(advanced_note)

            self._view_mode = str(self.state.get("view_tab", "all"))
            self.view_tabs = QTabBar()
            self.view_tabs.addTab("Main")
            self.view_tabs.addTab("Advanced")
            if self._view_mode == "cores":
                self.view_tabs.setCurrentIndex(1)
            else:
                self.view_tabs.setCurrentIndex(0)
            self.view_tabs.currentChanged.connect(self._on_view_tab_changed)
            root.addWidget(self.view_tabs)

            self.cores_panel = self._build_cores_panel()
            root.addWidget(self.cores_panel)
            self._update_cores_panel_visibility()

            self.table = QTableWidget(0, 10)
            self.table.setHorizontalHeaderLabels(
                ["Info", "Knob", "Action", "Config", "Requirements", "Status", "Check", "Category", "Risk", "CLI"]
            )
            self.table.horizontalHeader().setStretchLastSection(False)
            self.table.setSortingEnabled(False)
            self.table.setAlternatingRowColors(True)
            self.table.setWordWrap(False)
            self.table.setTextElideMode(Qt.ElideRight)
            self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setMouseTracking(True)
            self.table.verticalHeader().setVisible(False)
            header = self.table.horizontalHeader()
            header.setMinimumSectionSize(60)
            info_header = self.table.horizontalHeaderItem(0)
            if info_header is not None:
                info_header.setToolTip("Show details")
            req_header = self.table.horizontalHeaderItem(4)
            if req_header is not None:
                req_header.setToolTip(self._requirements_key_tooltip())
            # Make every column user-resizable (Interactive). We also set reasonable defaults.
            # NOTE: ResizeToContents does NOT reliably account for cell widgets (buttons/combos),
            # which causes text clipping like "Apply" -> "Annlv".
            for c in range(self.table.columnCount()):
                header.setSectionResizeMode(c, QHeaderView.Interactive)
            self._sort_column: int | None = None
            self._sort_descending = False
            header.setSortIndicatorShown(True)
            header.sectionClicked.connect(self._on_header_sort)
            header.sectionResized.connect(self._on_section_resized)
            self._min_column_widths: dict[int, int] = {}
            self._apply_default_column_widths()
            root.addWidget(self.table)

            self._knob_statuses: dict[str, str] = {}
            self._busy_knobs: set[str] = set()
            self._install_busy = False
            self._logs_busy = False
            self._reboot_busy = False
            self._status_busy = False
            self._user_groups: set[str] = set()
            self._refresh_user_groups()
            self._refresh_statuses()
            self._populate()
            QTimer.singleShot(0, self._apply_window_constraints)

            self.btn_reset.clicked.connect(self.on_reset_defaults)
            self.table.cellEntered.connect(self._on_row_hover)
            self.table.viewport().installEventFilter(self)
            self.table.horizontalHeader().installEventFilter(self)
            self.table.installEventFilter(self)
            self.installEventFilter(self)

        def _advanced_knob_ids(self) -> set[str]:
            return set(
                [
                    "irqbalance_disable",
                    "rtirq_enable",
                    "irq_pinning",
                    "cpu_governor_performance_persistent",
                    "power_profile_performance",
                    "kernel_threadirqs",
                    "kernel_rt_throttling_off",
                    "kernel_cstate_limit",
                    "kernel_intel_idle_cstate_limit",
                    "kernel_audit_off",
                    "kernel_mitigations_off",
                    "kernel_isolcpus",
                    "kernel_nohz_full",
                    "kernel_rcu_nocbs",
                    "kernel_irqaffinity",
                ]
            )

        def _core_knob_ids(self) -> set[str]:
            return {
                "qjackctl_server_prefix_rt",
                "irq_pinning",
                "kernel_rt_throttling_off",
                "kernel_cstate_limit",
                "kernel_intel_idle_cstate_limit",
                "kernel_isolcpus",
                "kernel_nohz_full",
                "kernel_rcu_nocbs",
                "kernel_irqaffinity",
            }

        def _on_view_tab_changed(self, index: int) -> None:
            mode = "cores" if index == 1 else "all"
            if mode == self._view_mode:
                return
            self._view_mode = mode
            self.state["view_tab"] = mode
            save_state(self.state)
            self._update_cores_panel_visibility()
            self._populate()

        def _update_cores_panel_visibility(self) -> None:
            if hasattr(self, "cores_panel") and self.cores_panel is not None:
                self.cores_panel.setVisible(self._view_mode == "cores")
            self._sync_core_plan_controls()

        def _build_cores_panel(self) -> QWidget:
            from audioknob_gui.platform.detect import get_cpu_count

            cpu_count = get_cpu_count()
            panel = QWidget()
            root = QVBoxLayout(panel)
            root.setContentsMargins(0, 0, 0, 0)

            expanded = bool(self.state.get("audio_core_plan_expanded", True))
            header_row = QHBoxLayout()
            self.core_plan_toggle = QToolButton()
            self.core_plan_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.core_plan_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
            self.core_plan_toggle.setText("Audio Core Plan")
            self.core_plan_toggle.setCheckable(True)
            self.core_plan_toggle.setChecked(expanded)
            self.core_plan_toggle.setAutoRaise(True)
            self.core_plan_toggle.toggled.connect(self._on_core_plan_toggle)
            header_row.addWidget(self.core_plan_toggle)
            header_row.addStretch(1)
            root.addLayout(header_row)

            self.core_plan_body = QWidget()
            body = QVBoxLayout(self.core_plan_body)

            hint = QLabel("Auto-set chooses audio cores and updates per-knob core selections. Apply knobs to take effect.")
            hint.setWordWrap(True)
            body.addWidget(hint)

            row = QHBoxLayout()
            row.addWidget(QLabel("Audio cores"))
            self.core_plan_count = QSpinBox()
            self.core_plan_count.setRange(1, max(1, int(cpu_count)))
            self.core_plan_count.setValue(int(self.state.get("audio_core_plan_count", 4)))
            self.core_plan_count.valueChanged.connect(self._on_core_plan_count_changed)
            row.addWidget(self.core_plan_count)
            self.btn_core_plan_auto = QPushButton("Auto-set")
            self.btn_core_plan_auto.clicked.connect(self._on_core_plan_auto)
            row.addWidget(self.btn_core_plan_auto)
            row.addStretch(1)
            body.addLayout(row)

            self.core_plan_auto_housekeeping = QCheckBox("Auto housekeeping (invert audio cores)")
            self.core_plan_auto_housekeeping.setChecked(bool(self.state.get("irq_housekeeping_auto", True)))
            self.core_plan_auto_housekeeping.setToolTip(
                "Use IRQ Pinning audio cores to invert the housekeeping set for irqaffinity."
            )
            self.core_plan_auto_housekeeping.toggled.connect(self._on_housekeeping_auto_toggled)
            body.addWidget(self.core_plan_auto_housekeeping)

            self.core_plan_summary = QLabel("")
            self.core_plan_summary.setWordWrap(True)
            body.addWidget(self.core_plan_summary)

            btn_row = QHBoxLayout()
            self.btn_irq_overview = QPushButton("IRQ Overview")
            self.btn_irq_overview.clicked.connect(self._show_irq_overview)
            btn_row.addWidget(self.btn_irq_overview)
            btn_row.addStretch(1)
            body.addLayout(btn_row)

            baseline_row = QHBoxLayout()
            self.btn_baseline_capture = QPushButton("Capture Baseline...")
            self.btn_baseline_capture.setToolTip("Capture current system as baseline and save to a file")
            self.btn_baseline_capture.clicked.connect(self._on_capture_baseline)
            baseline_row.addWidget(self.btn_baseline_capture)
            self.btn_baseline_import = QPushButton("Import Baseline...")
            self.btn_baseline_import.setToolTip("Import a baseline snapshot file (no system changes)")
            self.btn_baseline_import.clicked.connect(self._on_import_baseline)
            baseline_row.addWidget(self.btn_baseline_import)
            baseline_row.addStretch(1)
            body.addLayout(baseline_row)

            self.core_plan_body.setVisible(expanded)
            root.addWidget(self.core_plan_body)

            return panel

        def _on_core_plan_toggle(self, expanded: bool) -> None:
            self.state["audio_core_plan_expanded"] = bool(expanded)
            save_state(self.state)
            if hasattr(self, "core_plan_body"):
                self.core_plan_body.setVisible(expanded)
            if hasattr(self, "core_plan_toggle"):
                self.core_plan_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

        def _on_core_plan_count_changed(self, value: int) -> None:
            self.state["audio_core_plan_count"] = int(value)
            save_state(self.state)
            self._sync_core_plan_controls()

        def _on_housekeeping_auto_toggled(self, enabled: bool) -> None:
            self.state["irq_housekeeping_auto"] = bool(enabled)
            save_state(self.state)
            self._sync_core_plan_controls()
            status = self._knob_statuses.get("kernel_irqaffinity")
            if status in ("applied", "pending_reboot"):
                _get_gui_logger().info("irq housekeeping mode updated; reapplying")
                self._on_apply_knob("kernel_irqaffinity")
                return
            QMessageBox.information(
                self,
                "Saved",
                "Saved IRQ housekeeping mode. Apply IRQ Housekeeping (irqaffinity) to take effect.",
            )

        def _suggest_audio_cores(self, count: int) -> list[int]:
            from audioknob_gui.core.irq import (
                is_irq_affinity_writable,
                list_irqs,
                parse_cpu_list,
                read_cpu_present,
                read_irq_effective_affinity_list,
                read_thread_sibling_groups,
            )

            desired = max(1, int(count))
            cores = sorted(read_cpu_present())
            if not cores:
                return []
            scores = {c: 0 for c in cores}
            for irq in list_irqs():
                if is_irq_affinity_writable(irq):
                    continue
                raw = read_irq_effective_affinity_list(irq)
                if not raw:
                    continue
                for core in parse_cpu_list(raw):
                    if core in scores:
                        scores[core] += 1

            groups = read_thread_sibling_groups() or [[c] for c in cores]
            avoid = {0, 1}
            groups_no01 = [g for g in groups if avoid.isdisjoint(g)]
            filtered = False
            if sum(len(g) for g in groups_no01) >= desired:
                groups = groups_no01
                filtered = True

            entries: list[tuple[int, int, list[int]]] = []
            for group in groups:
                group_score = sum(scores.get(c, 0) for c in group)
                entries.append((group_score, min(group), group))
            entries.sort(key=lambda item: (item[0], item[1]))

            selected: set[int] = set()
            for _, _, group in entries:
                selected.update(group)
                if len(selected) >= desired:
                    break

            if len(selected) < desired and filtered:
                entries = []
                for group in read_thread_sibling_groups() or [[c] for c in cores]:
                    group_score = sum(scores.get(c, 0) for c in group)
                    entries.append((group_score, min(group), group))
                entries.sort(key=lambda item: (item[0], item[1]))
                selected.clear()
                for _, _, group in entries:
                    selected.update(group)
                    if len(selected) >= desired:
                        break

            return sorted(selected)

        def _on_core_plan_auto(self) -> None:
            count = int(self.core_plan_count.value())
            audio_cores = self._suggest_audio_cores(count)
            if not audio_cores:
                QMessageBox.warning(self, "Auto-set", "No audio cores could be selected.")
                return
            audio_cores = sorted(set(audio_cores))
            selected_count = len(audio_cores)
            self.state["irq_pinning_cpu_cores"] = audio_cores
            self.state["qjackctl_cpu_cores"] = audio_cores
            self.state["kernel_isolcpus_cores"] = audio_cores
            self.state["kernel_nohz_full_cores"] = audio_cores
            self.state["kernel_rcu_nocbs_cores"] = audio_cores
            self.state["irq_housekeeping_auto"] = True
            save_state(self.state)

            affected = [
                "irq_pinning",
                "qjackctl_server_prefix_rt",
                "kernel_isolcpus",
                "kernel_nohz_full",
                "kernel_rcu_nocbs",
                "kernel_irqaffinity",
            ]
            by_id = {k.id: k for k in self.registry}
            queued: list[str] = []
            skipped: list[str] = []
            for kid in affected:
                self._knob_statuses[kid] = "not_applied"
                knob = by_id.get(kid)
                if knob is None:
                    continue
                allowed, reason = self._queue_apply_allowed(knob)
                if not allowed:
                    if reason:
                        skipped.append(f"{knob.title} ({reason})")
                    else:
                        skipped.append(knob.title)
                    continue
                if self._queued_actions.get(kid) != "apply":
                    self._queued_actions[kid] = "apply"
                    queued.append(knob.title)
            self._save_queue()
            self._update_queue_ui()
            self._refresh_statuses()
            self._populate()
            extra = ""
            if selected_count != count:
                extra = (
                    f"\n\nRequested {count} cores; selected {selected_count} to keep SMT siblings together."
                )
            if queued:
                extra += "\n\nQueued apply for:\n" + "\n".join(f"- {name}" for name in queued)
            if skipped:
                extra += "\n\nSkipped (locked/unavailable):\n" + "\n".join(f"- {name}" for name in skipped)
            QMessageBox.information(
                self,
                "Auto-set complete",
                "Core selections updated. Apply the queued changes to take effect." + extra,
            )

        def _sync_core_plan_controls(self) -> None:
            auto = bool(self.state.get("irq_housekeeping_auto", True))
            if hasattr(self, "core_plan_auto_housekeeping") and self.core_plan_auto_housekeeping is not None:
                if self.core_plan_auto_housekeeping.isChecked() != auto:
                    self.core_plan_auto_housekeeping.blockSignals(True)
                    self.core_plan_auto_housekeeping.setChecked(auto)
                    self.core_plan_auto_housekeeping.blockSignals(False)
            self._refresh_core_plan_summary()

        def _refresh_core_plan_summary(self) -> None:
            if not hasattr(self, "core_plan_summary") or self.core_plan_summary is None:
                return
            try:
                from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups
                from audioknob_gui.platform.detect import get_cpu_count
            except Exception:
                return
            cpu_count = get_cpu_count()
            audio = sorted(set(self._irq_pinning_cpu_cores_from_state() or []))
            audio_text = ",".join(str(c) for c in audio) if audio else "unset"
            auto = bool(self.state.get("irq_housekeeping_auto", True))
            if auto:
                housekeeping = sorted(set(range(cpu_count)) - set(audio))
            else:
                housekeeping = sorted(set(self._kernel_cores_from_state("kernel_irqaffinity") or []))
            hk_text = ",".join(str(c) for c in housekeeping) if housekeeping else "unset"
            mode = "auto" if auto else "manual"
            summary = f"Audio cores: {audio_text} | Housekeeping ({mode}): {hk_text}"

            groups = read_thread_sibling_groups()
            logical = len(read_cpu_present() or [])
            physical = len(groups)
            smt = any(len(g) > 1 for g in groups)
            if smt and logical:
                summary += f"\nSMT detected: {physical} physical / {logical} logical. Auto-set keeps sibling cores together."
            self.core_plan_summary.setText(summary)

        def _show_irq_overview(self) -> None:
            try:
                from audioknob_gui.core.irq import (
                    is_irq_affinity_writable,
                    list_irqs,
                    parse_cpu_list,
                    read_cpu_present,
                    read_irq_affinity_list,
                    read_irq_effective_affinity_list,
                )
            except Exception as exc:
                QMessageBox.warning(self, "IRQ Overview", f"Failed to load IRQ helpers: {exc}")
                return

            def _read_interrupts_map() -> dict[int, str]:
                try:
                    raw = Path("/proc/interrupts").read_text(encoding="utf-8")
                except Exception:
                    return {}
                lines: dict[int, str] = {}
                for line in raw.splitlines():
                    stripped = line.strip()
                    if not stripped or not stripped[:1].isdigit():
                        continue
                    if ":" not in stripped:
                        continue
                    irq_str, rest = stripped.split(":", 1)
                    irq_str = irq_str.strip()
                    if not irq_str.isdigit():
                        continue
                    try:
                        irq = int(irq_str)
                    except Exception:
                        continue
                    lines[irq] = rest.strip()
                return lines

            cores = sorted(read_cpu_present())
            audio = sorted(set(self._irq_pinning_cpu_cores_from_state() or []))
            auto = bool(self.state.get("irq_housekeeping_auto", True))
            if auto:
                housekeeping = sorted(set(cores) - set(audio))
            else:
                housekeeping = sorted(set(self._kernel_cores_from_state("kernel_irqaffinity") or []))

            dialog = QDialog(self)
            dialog.setWindowTitle("IRQ Overview")
            dialog.resize(720, 520)
            layout = QVBoxLayout(dialog)

            audio_text = ",".join(str(c) for c in audio) if audio else "unset"
            hk_text = ",".join(str(c) for c in housekeeping) if housekeeping else "unset"
            mode = "auto" if auto else "manual"
            summary = QLabel(
                f"Audio cores: {audio_text} | Housekeeping ({mode}): {hk_text}"
            )
            summary.setWordWrap(True)
            layout.addWidget(summary)

            grid_box = QGroupBox("Core map")
            grid_layout = QGridLayout(grid_box)
            cols = 8
            base_style = (
                "padding: 4px 6px; border-radius: 3px; background-color: #2b2b2b; color: #e0e0e0;"
            )
            for idx, core in enumerate(cores):
                label = QLabel(str(core))
                label.setAlignment(Qt.AlignCenter)
                style = base_style
                if core in housekeeping:
                    style += " background-color: #1f4f2b;"
                if core in audio:
                    style += " border: 2px solid #4a90e2;"
                label.setStyleSheet(style)
                grid_layout.addWidget(label, idx // cols, idx % cols)
            layout.addWidget(grid_box)

            legend = QLabel("Legend: green fill = housekeeping cores, blue outline = audio cores.")
            legend.setWordWrap(True)
            layout.addWidget(legend)

            irq_lines = _read_interrupts_map()
            rows: list[str] = []
            for irq in list_irqs():
                affinity = read_irq_effective_affinity_list(irq)
                if not affinity:
                    affinity = read_irq_affinity_list(irq) or "unknown"
                ro = "ro" if not is_irq_affinity_writable(irq) else ""
                desc = irq_lines.get(irq, "")
                if desc:
                    rows.append(f"IRQ {irq:>4}: {affinity:<12} {ro:<3} {desc}")
                else:
                    rows.append(f"IRQ {irq:>4}: {affinity:<12} {ro}".rstrip())

            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText("\n".join(rows) if rows else "No IRQs found.")
            layout.addWidget(text)

            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.rejected.connect(dialog.reject)
            btns.accepted.connect(dialog.accept)
            layout.addWidget(btns)
            dialog.exec()

        def _smt_hint_line(self) -> str | None:
            try:
                from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups
            except Exception:
                return None
            groups = read_thread_sibling_groups()
            smt = any(len(g) > 1 for g in groups)
            if not smt:
                return None
            logical = len(read_cpu_present() or [])
            physical = len(groups)
            return (
                f"SMT detected: {physical} physical / {logical} logical. "
                "Select both siblings of a physical core for best isolation."
            )

        def _requirements_label(self, k, advanced_knobs: set[str]) -> str:
            parts: list[str] = []
            if k.id in advanced_knobs:
                parts.append("A")
            if k.requires_reboot:
                parts.append("R")
            if k.requires_groups:
                parts.append("G")
            if not parts:
                return "—"
            return " ".join(parts)

        def _requirements_key_tooltip(self) -> str:
            return "A=Advanced, R=Reboot required, G=Groups required"

        def _requirements_tooltip(self, k, advanced_knobs: set[str]) -> str:
            legend = self._requirements_key_tooltip()
            parts: list[str] = []
            if k.id in advanced_knobs:
                parts.append("Advanced")
            if k.requires_reboot:
                parts.append("Reboot required")
            if k.requires_groups:
                parts.append("Groups required")
            if not parts:
                return f"{legend}\nNo requirements"
            return f"{legend}\nRequires: {', '.join(parts)}"

        def _requirements_group_tooltip(self, label: str) -> str:
            legend = self._requirements_key_tooltip()
            if label == "—":
                return f"{legend}\nNo requirements"
            parts: list[str] = []
            for letter in label.split():
                if letter == "A":
                    parts.append("Advanced")
                elif letter == "R":
                    parts.append("Reboot required")
                elif letter == "G":
                    parts.append("Groups required")
            if not parts:
                return legend
            return f"{legend}\nRequires: {', '.join(parts)}"

        def _grouping_mode(self) -> str | None:
            if self._sort_column is None or self._sort_column == 7:
                return "category"
            if self._sort_column == 4:
                return "requirements"
            if self._sort_column == 5:
                return "status"
            if self._sort_column == 8:
                return "risk"
            return None

        def _category_label(self, key: str) -> str:
            mapping = {
                "cpu": "CPU",
                "irq": "IRQ",
                "kernel": "Kernel",
                "permissions": "Permissions",
                "power": "Power",
                "services": "Services",
                "stack": "Stack",
                "testing": "Testing",
                "vm": "Memory",
            }
            if key in mapping:
                return mapping[key]
            cleaned = key.replace("_", " ").strip()
            return cleaned.title() if cleaned else key

        def _sys_label_for_knob(self, k) -> str:
            if k.impl is None:
                return "—"
            kind = k.impl.kind
            params = k.impl.params or {}

            if kind == "kernel_cmdline":
                param = self._kernel_cmdline_param_for_state(k.id)
                if not param:
                    param = str(params.get("param", "")).strip()
                if param:
                    return param.split("=", 1)[0].strip() or param
                return "cmdline"

            if kind == "sysctl_conf":
                lines = params.get("lines") or []
                keys: list[str] = []
                for line in lines:
                    raw = str(line).strip()
                    if not raw or raw.startswith("#") or "=" not in raw:
                        continue
                    key = raw.split("=", 1)[0].strip()
                    if key and key not in keys:
                        keys.append(key)
                return ",".join(keys) if keys else "sysctl"

            if kind == "sysfs_glob_kv":
                glob = str(params.get("glob", "")).strip()
                return Path(glob).name if glob else "sysfs"

            if kind == "udev_rule":
                path = str(params.get("path", "")).strip()
                return Path(path).name if path else "udev"

            if kind == "pam_limits_audio_group":
                path = str(params.get("path", "")).strip()
                return Path(path).name if path else "limits"

            if kind == "power_profile":
                backend = self._power_profile_backend_from_state()
                if backend == "powerprofilesctl":
                    return "powerprofilesctl"
                if backend == "tuned":
                    return "tuned-adm"
                return "powerprofilesctl/tuned"

            if kind == "qjackctl_server_prefix":
                return "QjackCtl.conf"

            if kind == "pipewire_conf":
                return "pipewire.conf.d"

            if kind == "systemd_unit_toggle":
                unit = str(params.get("unit", "")).strip()
                return unit or "systemd"

            if kind == "rtirq_config":
                profile = self.state.get("system_profile")
                if isinstance(profile, dict):
                    paths = profile.get("paths")
                    if isinstance(paths, dict):
                        rtirq_path = str(paths.get("rtirq_config") or "")
                        if rtirq_path:
                            return Path(rtirq_path).name
                return "rtirq.conf"

            if kind == "irq_affinity":
                return "/proc/irq"

            if kind == "group_membership":
                return "groups"

            if kind == "user_service_mask":
                services = params.get("services")
                if isinstance(services, list):
                    items = [str(s) for s in services if s]
                    if items:
                        return ",".join(items)
                unit = str(params.get("unit", "")).strip()
                return unit or "user service"

            if kind == "baloo_disable":
                return "balooctl"

            if kind == "read_only":
                what = str(params.get("what", "")).strip()
                return what or "read_only"

            return kind

        def _visible_knobs(self) -> list:
            if getattr(self, "_view_mode", "all") == "cores":
                core_ids = self._core_knob_ids()
                return [k for k in self.registry if k.id in core_ids]
            core_ids = self._core_knob_ids()
            return [k for k in self.registry if k.id not in core_ids]

        def _refresh_user_groups(self) -> None:
            """Get current user's group memberships."""
            import grp
            try:
                user_gids = set(os.getgroups())
                self._user_groups = set()
                for group_name in ["audio", "realtime", "pipewire"]:
                    try:
                        if grp.getgrnam(group_name).gr_gid in user_gids:
                            self._user_groups.add(group_name)
                    except KeyError:
                        pass  # Group doesn't exist
            except Exception:
                self._user_groups = set()

        def _detect_desktop(self) -> str:
            """Return 'gnome', 'kde', or 'unknown' based on session env vars."""
            raw = " ".join(
                v
                for v in (
                    os.environ.get("XDG_CURRENT_DESKTOP", ""),
                    os.environ.get("XDG_SESSION_DESKTOP", ""),
                    os.environ.get("DESKTOP_SESSION", ""),
                )
                if v
            ).lower()
            if "gnome" in raw or "ubuntu" in raw:
                return "gnome"
            if "kde" in raw or "plasma" in raw:
                return "kde"
            # Fallback: infer from common session processes.
            try:
                ps_cmd = shutil.which("ps")
                if not ps_cmd:
                    for candidate in ("/bin/ps", "/usr/bin/ps"):
                        if Path(candidate).exists():
                            ps_cmd = candidate
                            break
                if not ps_cmd:
                    return "unknown"
                p = subprocess.run(
                    [ps_cmd, "-e", "-o", "comm="],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                names = set(p.stdout.split())
                if "gnome-shell" in names or any(n.startswith("gnome-session") for n in names):
                    return "gnome"
                if {"plasmashell", "ksmserver", "ksplashqml"} & names or any(n.startswith("plasma") for n in names):
                    return "kde"
            except Exception:
                pass
            return "unknown"

        def _knob_group_ok(self, k) -> bool:
            """Check if user has required groups for this knob."""
            if not k.requires_groups:
                return True  # No groups required
            # User needs to be in at least ONE of the required groups
            return bool(set(k.requires_groups) & self._user_groups)

        def _knob_commands_ok(self, k) -> bool:
            """Check if required commands are available for this knob."""
            if not k.requires_commands:
                return True  # No commands required
            from audioknob_gui.platform.packages import check_command_available
            if k.id == "power_profile_performance":
                backend = self._power_profile_backend_from_state()
                if backend == "powerprofilesctl":
                    return check_command_available("powerprofilesctl")
                if backend == "tuned":
                    return check_command_available("tuned-adm")
                return (
                    check_command_available("powerprofilesctl")
                    or check_command_available("tuned-adm")
                )
            return all(check_command_available(cmd) for cmd in k.requires_commands)

        def _knob_missing_commands(self, k) -> list[str]:
            """Return list of missing commands for this knob."""
            if not k.requires_commands:
                return []
            from audioknob_gui.platform.packages import check_command_available
            if k.id == "power_profile_performance":
                backend = self._power_profile_backend_from_state()
                if backend == "powerprofilesctl":
                    return [] if check_command_available("powerprofilesctl") else ["powerprofilesctl"]
                if backend == "tuned":
                    return [] if check_command_available("tuned-adm") else ["tuned-adm"]
                if (
                    check_command_available("powerprofilesctl")
                    or check_command_available("tuned-adm")
                ):
                    return []
                return ["powerprofilesctl", "tuned-adm"]
            return [cmd for cmd in k.requires_commands if not check_command_available(cmd)]

        def _queue_apply_allowed(self, k) -> tuple[bool, str]:
            if not self._baseline_ready:
                return False, "Baseline scan pending"
            status = self._knob_statuses.get(k.id, "unknown")
            if status == "not_applicable":
                return False, "Not available on this system"
            reboot_gate_enabled = bool(self.state.get("enable_reboot_knobs", False))
            advanced_enabled = bool(self.state.get("advanced_mode_enabled", False))
            group_pending = self._knob_statuses.get("audio_group_membership") == "pending_reboot"
            group_ok = self._knob_group_ok(k)
            if group_pending and k.requires_groups:
                group_ok = False
            commands_ok = self._knob_commands_ok(k)
            reboot_gate_lock = (
                bool(k.requires_reboot)
                and not reboot_gate_enabled
                and status not in ("applied", "pending_reboot")
            )
            advanced_gate_lock = (
                k.id in self._advanced_knob_ids()
                and not advanced_enabled
                and status not in ("applied", "pending_reboot")
            )
            reboot_dep_lock = (not reboot_gate_enabled) and bool(k.requires_groups)
            if group_pending:
                return False, f"Groups pending reboot: {', '.join(k.requires_groups)}"
            if reboot_dep_lock:
                return False, f"Requires groups: {', '.join(k.requires_groups)} (enable reboot-required changes)"
            if not group_ok:
                return False, f"Join groups: {', '.join(k.requires_groups)}"
            if reboot_gate_lock:
                return False, f"Reboot required: {k.title}"
            if advanced_gate_lock:
                return False, "Enable advanced knobs"
            if not commands_ok:
                missing = self._knob_missing_commands(k)
                return False, f"Install: {', '.join(missing)}" if missing else "Missing commands"
            return True, ""

        def _collect_log_text(self) -> str:
            gui_log = _state_path().parent / "logs" / "gui.log"
            user_worker_log = Path(_worker_log_path(is_root=False))
            root_worker_log = Path(_worker_log_path(is_root=True))

            entries: list[tuple[str, str, Path]] = [
                ("GUI log", "GUI", gui_log),
                ("Worker log (user)", "WORKER-USER", user_worker_log),
                ("Worker log (root)", "WORKER-ROOT", root_worker_log),
            ]

            lines: list[str] = []
            for label, tag, path in entries:
                lines.append(f"=== {label} ===")
                lines.append(f"Path: {path}")

                if not path.exists():
                    lines.append(f"[{tag}] [not found]")
                    lines.append("")
                    continue

                if label.endswith("(root)") and not os.access(path, os.R_OK):
                    lines.append(f"[{tag}] [not readable: requires root]")
                    lines.append("")
                    continue

                try:
                    content = path.read_text(encoding="utf-8")
                except Exception as exc:
                    lines.append(f"[{tag}] [error reading log: {exc}]")
                    lines.append("")
                    continue

                if content.strip():
                    for line in content.rstrip("\n").splitlines():
                        lines.append(f"[{tag}] {line}")
                else:
                    lines.append(f"[{tag}] [empty]")
                lines.append("")

            return "\n".join(lines).rstrip() + "\n"

        def _on_show_logs(self) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Logs")
            dialog.resize(720, 520)

            layout = QVBoxLayout(dialog)
            text = QTextEdit()
            text.setReadOnly(True)
            text.setLineWrapMode(QTextEdit.NoWrap)
            text.setPlainText(self._collect_log_text())
            layout.addWidget(text)

            btn_row = QHBoxLayout()
            copy_btn = QPushButton("Copy to Clipboard")
            copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(text.toPlainText()))
            btn_row.addWidget(copy_btn)
            clear_btn = QPushButton("Clear Logs")
            clear_btn.clicked.connect(lambda: self._on_clear_logs(text, clear_btn))
            btn_row.addWidget(clear_btn)
            btn_row.addStretch(1)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

            dialog.exec()

        def _on_clear_logs(
            self,
            text: QTextEdit | None = None,
            clear_btn: QPushButton | None = None,
        ) -> None:
            if self._logs_busy:
                QMessageBox.information(self, "Clear Logs", "Log clearing is already running.")
                return
            reply = QMessageBox.question(
                self,
                "Clear Logs",
                "Clear GUI, user worker, and root worker logs?\n\nRoot worker log requires pkexec.",
                QMessageBox.Ok | QMessageBox.Cancel,
            )
            if reply != QMessageBox.Ok:
                return
            self._logs_busy = True
            if clear_btn is not None:
                clear_btn.setEnabled(False)

            gui_log = _state_path().parent / "logs" / "gui.log"
            user_worker_log = Path(_worker_log_path(is_root=False))
            root_worker_log = Path(_worker_log_path(is_root=True))

            def _task() -> tuple[bool, object, str]:
                cleared: list[str] = []
                errors: list[str] = []

                for path in (gui_log, user_worker_log):
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("", encoding="utf-8")
                        cleared.append(str(path))
                    except Exception as exc:
                        errors.append(f"{path}: {exc}")

                if root_worker_log.exists():
                    try:
                        _run_pkexec_command(["/bin/sh", "-c", f": > {root_worker_log}"])
                        cleared.append(str(root_worker_log))
                    except Exception as exc:
                        errors.append(f"{root_worker_log}: {exc}")

                payload = {
                    "cleared": cleared,
                    "errors": errors,
                    "root_log": str(root_worker_log) if root_worker_log.exists() else None,
                }
                return True, payload, ""

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                self._logs_busy = False
                if clear_btn is not None:
                    clear_btn.setEnabled(True)
                if not isinstance(payload, dict):
                    payload = {
                        "cleared": [],
                        "errors": [message or "Log clear failed"],
                        "root_log": str(root_worker_log),
                    }
                errors = payload.get("errors") or []
                _log_gui_audit("clear-logs", payload)
                if errors:
                    details = "\n".join(str(e) for e in errors)
                    QMessageBox.warning(self, "Logs Cleared (with warnings)", details)
                else:
                    QMessageBox.information(self, "Logs Cleared", "Logs cleared successfully.")
                if text is not None:
                    text.setPlainText(self._collect_log_text())

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _summarize_effect(self, effect: dict[str, Any]) -> str:
            kind = str(effect.get("kind", ""))
            if kind == "kernel_cmdline":
                param = str(effect.get("param", "")).strip()
                path = str(effect.get("file") or effect.get("path") or "").strip()
                if param and path:
                    return f"kernel_cmdline: {param} ({path})"
                if param:
                    return f"kernel_cmdline: {param}"
                if path:
                    return f"kernel_cmdline ({path})"
                return "kernel_cmdline"
            if kind == "sysfs_write":
                path = str(effect.get("path", "")).strip()
                return f"sysfs_write: {path}" if path else "sysfs_write"
            if kind == "systemd_unit_toggle":
                unit = str(effect.get("unit", "")).strip()
                return f"systemd_unit_toggle: {unit}" if unit else "systemd_unit_toggle"
            if kind == "user_service_mask":
                services = effect.get("services", [])
                units: list[str] = []
                if isinstance(services, list):
                    for svc in services:
                        if isinstance(svc, dict):
                            unit = str(svc.get("unit", "")).strip()
                        else:
                            unit = str(svc).strip()
                        if unit:
                            units.append(unit)
                if units:
                    suffix = "..." if len(units) > 3 else ""
                    return f"user_service_mask: {', '.join(units[:3])}{suffix}"
                return "user_service_mask"
            if kind == "pipewire_restart":
                return "pipewire_restart"
            if kind == "baloo_disable":
                return "baloo_disable"
            if kind == "power_profile":
                backend = str(effect.get("backend", "")).strip()
                before = str(effect.get("before", "")).strip()
                after = str(effect.get("after", "")).strip()
                detail = " -> ".join([x for x in (before, after) if x])
                if backend and detail:
                    return f"power_profile: {backend} ({detail})"
                if backend:
                    return f"power_profile: {backend}"
                return "power_profile"
            return kind or "effect"

        def _format_tx_preview(self, item: dict[str, Any], titles: dict[str, str]) -> str:
            txid = str(item.get("txid", ""))
            scope = str(item.get("scope", "unknown"))
            ts = item.get("timestamp")
            if isinstance(ts, (int, float)) and ts > 0:
                when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            else:
                when = "-"
            lines = [f"txid: {txid}", f"scope: {scope}", f"time: {when}"]

            applied = item.get("applied") or []
            if isinstance(applied, list) and applied:
                lines.append("")
                lines.append("knobs:")
                for kid in applied:
                    if not isinstance(kid, str):
                        continue
                    title = titles.get(kid, kid)
                    if title and title != kid:
                        lines.append(f"- {title} ({kid})")
                    else:
                        lines.append(f"- {kid}")

            backups = item.get("backups") or []
            file_paths: list[str] = []
            if isinstance(backups, list):
                for meta in backups:
                    if isinstance(meta, dict):
                        path = meta.get("path")
                        if isinstance(path, str) and path not in file_paths:
                            file_paths.append(path)
            if file_paths:
                lines.append("")
                lines.append("files:")
                for path in file_paths:
                    lines.append(f"- {path}")

            effects = item.get("effects") or []
            if isinstance(effects, list) and effects:
                lines.append("")
                lines.append("effects:")
                for effect in effects:
                    if isinstance(effect, dict):
                        lines.append(f"- {self._summarize_effect(effect)}")

            return "\n".join(lines)

        def _on_show_tx_history(self) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Tx History")
            dialog.resize(780, 520)
            layout = QVBoxLayout(dialog)

            baseline_ts = self.state.get("baseline_captured_at") or "-"
            baseline_user = self.state.get("baseline_txid_user") or "-"
            baseline_root = self.state.get("baseline_txid_root") or "-"
            baseline_label = QLabel(
                f"Baseline: {baseline_ts} (user txid: {baseline_user}, root txid: {baseline_root})"
            )
            layout.addWidget(baseline_label)

            table = QTableWidget(0, 7)
            table.setHorizontalHeaderLabels(
                ["TxID", "Scope", "When", "Knobs", "Files", "Effects", "Restore"]
            )
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setAlternatingRowColors(True)
            table.setWordWrap(False)
            table.setTextElideMode(Qt.ElideRight)
            table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(table)

            btn_row = QHBoxLayout()
            refresh_btn = QPushButton("Refresh")
            btn_row.addWidget(refresh_btn)
            btn_row.addStretch(1)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

            titles = {k.id: k.title for k in self.registry}

            def _render(items: list[dict[str, Any]]) -> None:
                table.setRowCount(0)
                for row, item in enumerate(items):
                    txid = str(item.get("txid", ""))
                    scope = str(item.get("scope", "unknown"))
                    ts = item.get("timestamp")
                    if isinstance(ts, (int, float)) and ts > 0:
                        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        when = "-"

                    applied = item.get("applied") or []
                    applied_names = [
                        titles.get(kid, kid)
                        for kid in applied
                        if isinstance(kid, str)
                    ]
                    knobs_text = ", ".join(applied_names) if applied_names else "-"

                    backups = item.get("backups") or []
                    file_paths = {
                        meta.get("path")
                        for meta in backups
                        if isinstance(meta, dict) and isinstance(meta.get("path"), str)
                    }
                    files_text = str(len(file_paths)) if file_paths else "-"

                    effects = item.get("effects") or []
                    effects_text = str(len(effects)) if isinstance(effects, list) and effects else "-"

                    preview = self._format_tx_preview(item, titles)

                    table.insertRow(row)
                    tx_item = QTableWidgetItem(txid)
                    tx_item.setToolTip(preview)
                    table.setItem(row, 0, tx_item)
                    scope_item = QTableWidgetItem(scope)
                    scope_item.setToolTip(preview)
                    table.setItem(row, 1, scope_item)
                    when_item = QTableWidgetItem(when)
                    when_item.setToolTip(preview)
                    table.setItem(row, 2, when_item)
                    knobs_item = QTableWidgetItem(knobs_text)
                    knobs_item.setToolTip(preview)
                    table.setItem(row, 3, knobs_item)
                    files_item = QTableWidgetItem(files_text)
                    files_item.setToolTip(preview)
                    table.setItem(row, 4, files_item)
                    effects_item = QTableWidgetItem(effects_text)
                    effects_item.setToolTip(preview)
                    table.setItem(row, 5, effects_item)

                    restore_btn = QPushButton("Restore")
                    restore_btn.setToolTip(preview)

                    def _restore(_checked=False, *, tx=txid, sc=scope, details=preview):
                        msg = "Restore this transaction?\n\n" + details
                        if QMessageBox.question(self, "Restore Transaction", msg) != QMessageBox.Yes:
                            return

                        def _task():
                            if sc == "root":
                                result = _run_worker_restore_pkexec(tx)
                            else:
                                result = _run_worker_restore_user(tx)
                            return True, result, ""

                        worker = QueueTaskWorker(_task, parent=dialog)

                        def _on_done(success: bool, payload: object, message: str) -> None:
                            if not success:
                                if message == _PKEXEC_CANCELLED:
                                    return
                                QMessageBox.warning(
                                    dialog,
                                    "Restore Failed",
                                    message or "Restore failed",
                                )
                                return
                            QMessageBox.information(dialog, "Restore", "Transaction restored.")
                            self._refresh_statuses()
                            _refresh_history()

                        worker.finished.connect(_on_done)
                        worker.finished.connect(worker.deleteLater)
                        self._task_threads.append(worker)
                        worker.start()

                    restore_btn.clicked.connect(_restore)
                    table.setCellWidget(row, 6, restore_btn)

                table.resizeColumnsToContents()

            def _refresh_history() -> None:
                refresh_btn.setEnabled(False)

                def _task():
                    payload = {
                        "user": None,
                        "root": None,
                        "errors": [],
                        "root_cancelled": False,
                    }
                    try:
                        payload["user"] = _run_worker_history_user()
                    except Exception as exc:
                        payload["errors"].append(str(exc))
                    try:
                        payload["root"] = _run_worker_history_pkexec()
                    except Exception as exc:
                        if str(exc) == _PKEXEC_CANCELLED:
                            payload["root_cancelled"] = True
                        else:
                            payload["errors"].append(str(exc))
                    if not payload["user"] and not payload["root"]:
                        return False, payload, "No history data"
                    return True, payload, ""

                worker = QueueTaskWorker(_task, parent=dialog)

                def _on_done(success: bool, payload: object, message: str) -> None:
                    refresh_btn.setEnabled(True)
                    if not success:
                        QMessageBox.warning(dialog, "Tx History", message or "History load failed")
                        return
                    if not isinstance(payload, dict):
                        return
                    items: list[dict[str, Any]] = []
                    user_data = payload.get("user") or {}
                    root_data = payload.get("root") or {}
                    for item in user_data.get("items") or []:
                        if isinstance(item, dict):
                            item.setdefault("scope", "user")
                            items.append(item)
                    for item in root_data.get("items") or []:
                        if isinstance(item, dict):
                            item.setdefault("scope", "root")
                            items.append(item)
                    items.sort(key=lambda i: float(i.get("timestamp") or 0), reverse=True)
                    _render(items)
                    errors = payload.get("errors") or []
                    if errors:
                        details = "\n".join(str(e) for e in errors)
                        QMessageBox.warning(dialog, "Tx History (warnings)", details)

                worker.finished.connect(_on_done)
                worker.finished.connect(worker.deleteLater)
                self._task_threads.append(worker)
                worker.start()

            refresh_btn.clicked.connect(_refresh_history)
            _refresh_history()
            dialog.exec()

        def _ensure_system_profile(self) -> None:
            if not self._system_profile_needs_scan():
                return
            try:
                from audioknob_gui.worker.ops import scan_system_profile
                profile = scan_system_profile(self.registry)
                self.state["system_profile"] = profile
                save_state(self.state)
                _get_gui_logger().info(
                    "system profile scanned distro=%s boot=%s",
                    profile.get("distro_id"),
                    profile.get("boot_system"),
                )
            except Exception as exc:
                _get_gui_logger().warning("System profile scan failed: %s", exc)

        def _system_profile_needs_scan(self) -> bool:
            profile = self.state.get("system_profile")
            if not isinstance(profile, dict) or not profile:
                return True
            if profile.get("schema") != 1:
                return True
            try:
                from audioknob_gui.worker.ops import detect_distro
            except Exception:
                return True
            try:
                distro = detect_distro()
            except Exception:
                return True
            if profile.get("distro_id") != distro.distro_id:
                return True
            if profile.get("boot_system") != distro.boot_system:
                return True
            return False

        def _build_dependency_index(self) -> dict[str, list[str]]:
            index: dict[str, list[str]] = {}
            for knob in self.registry:
                for dep in getattr(knob, "depends_on", ()):
                    index.setdefault(dep, []).append(knob.id)
            return index

        def _collect_dependent_resets(self, knob_ids: list[str]) -> list[str]:
            dependents: list[str] = []
            pending = list(knob_ids)
            seen = set(knob_ids)
            while pending:
                base = pending.pop()
                for child in self._dependency_index.get(base, []):
                    if child in seen:
                        continue
                    action = self._queued_actions.get(child)
                    status = self._knob_statuses.get(child, "unknown")
                    if action == "apply" or status in ("applied", "pending_reboot"):
                        dependents.append(child)
                        seen.add(child)
                        pending.append(child)
            return dependents

        def _confirm_dependency_reset(self, reset_ids: list[str]) -> list[str] | None:
            dependents = self._collect_dependent_resets(reset_ids)
            if not dependents:
                return []
            by_id = {k.id: k for k in self.registry}
            reset_titles = [by_id[k].title for k in reset_ids if k in by_id]
            dep_titles = [by_id[k].title for k in dependents if k in by_id]
            msg = (
                "Resetting these knobs will also reset dependent knobs:\n\n"
                + "\n".join(f"- {title}" for title in dep_titles)
                + "\n\nContinue?"
            )
            if reset_titles:
                msg = (
                    "Resetting:\n"
                    + "\n".join(f"- {title}" for title in reset_titles)
                    + "\n\n"
                    + msg
                )
            if QMessageBox.question(self, "Reset Dependencies", msg) != QMessageBox.Yes:
                return None
            return dependents

        def _baseline_available(self) -> bool:
            baseline = self.state.get("baseline_statuses")
            return isinstance(baseline, dict) and bool(baseline)

        def _baseline_is_manual(self) -> bool:
            return self.state.get("baseline_source") in ("capture", "import")

        def _set_baseline_buttons_enabled(self, enabled: bool) -> None:
            for name in ("btn_baseline_capture", "btn_baseline_import"):
                btn = getattr(self, name, None)
                if isinstance(btn, QPushButton):
                    btn.setEnabled(enabled)

        def _set_baseline_state(
            self,
            statuses: dict[str, str],
            *,
            checks: dict[str, list[str]] | None = None,
            captured_at: str | None = None,
            source: str = "initial",
        ) -> None:
            if not isinstance(statuses, dict) or not statuses:
                return
            valid_ids = {k.id for k in self.registry}
            cleaned = {k: str(v) for k, v in statuses.items() if k in valid_ids}
            if not cleaned:
                return
            if not isinstance(captured_at, str) or not captured_at:
                captured_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            self.state["baseline_statuses"] = cleaned
            self.state["baseline_captured_at"] = captured_at
            self.state["baseline_txid_user"] = self.state.get("last_user_txid")
            self.state["baseline_txid_root"] = self.state.get("last_root_txid")
            self.state["baseline_source"] = source if source in ("initial", "capture", "import") else "initial"
            if checks is None:
                self.state["baseline_checks"] = self._build_baseline_checks(cleaned)
            elif isinstance(checks, dict):
                clean_checks: dict[str, list[str]] = {}
                for knob_id, lines in checks.items():
                    if knob_id not in valid_ids:
                        continue
                    if not isinstance(lines, list):
                        continue
                    clean_checks[knob_id] = [str(x) for x in lines]
                self.state["baseline_checks"] = clean_checks
            else:
                self.state["baseline_checks"] = {}
            save_state(self.state)
            self._baseline_ready = True
            self._refresh_statuses()
            self._populate()

        def _baseline_snapshot(self) -> dict[str, object]:
            from audioknob_gui import __version__

            return {
                "schema": 1,
                "baseline_statuses": dict(self.state.get("baseline_statuses") or {}),
                "baseline_checks": dict(self.state.get("baseline_checks") or {}),
                "baseline_captured_at": self.state.get("baseline_captured_at"),
                "baseline_source": self.state.get("baseline_source", "initial"),
                "exported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "app_version": __version__,
            }

        def _write_baseline_snapshot(self, path: str, snapshot: dict[str, object]) -> bool:
            try:
                payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
                Path(path).write_text(payload, encoding="utf-8")
            except Exception as exc:
                QMessageBox.warning(self, "Baseline", f"Failed to save baseline:\n{exc}")
                return False
            return True

        def _load_baseline_snapshot(self, path: str) -> dict[str, object] | None:
            try:
                raw = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception as exc:
                QMessageBox.warning(self, "Baseline", f"Failed to load baseline:\n{exc}")
                return None
            if not isinstance(raw, dict):
                QMessageBox.warning(self, "Baseline", "Baseline file is not a JSON object.")
                return None
            statuses = raw.get("baseline_statuses")
            if not isinstance(statuses, dict) or not statuses:
                QMessageBox.warning(self, "Baseline", "Baseline file is missing status data.")
                return None
            valid_ids = {k.id for k in self.registry}
            cleaned = {k: str(v) for k, v in statuses.items() if k in valid_ids}
            if not cleaned:
                QMessageBox.warning(self, "Baseline", "Baseline file has no known knob ids.")
                return None
            checks = raw.get("baseline_checks")
            clean_checks: dict[str, list[str]] | None = None
            if isinstance(checks, dict):
                clean_checks = {}
                for knob_id, lines in checks.items():
                    if knob_id not in valid_ids:
                        continue
                    if not isinstance(lines, list):
                        continue
                    clean_checks[knob_id] = [str(x) for x in lines]
            captured_at = raw.get("baseline_captured_at")
            if not isinstance(captured_at, str) or not captured_at:
                captured_at = None
            return {
                "statuses": cleaned,
                "checks": clean_checks,
                "captured_at": captured_at,
            }

        def _confirm_baseline_overwrite(self, summary: str) -> bool:
            if not self._baseline_ready:
                return True
            msg = (
                f"{summary}\n\n"
                "This will overwrite the current baseline snapshot.\n\n"
                "This does not change system settings.\n\nContinue?"
            )
            return QMessageBox.question(self, "Baseline", msg) == QMessageBox.Yes

        def _start_baseline_scan(
            self,
            *,
            on_success: Callable[[dict[str, str]], None],
            on_cancel_title: str = "Baseline Required",
            on_cancel_message: str | None = None,
            on_error_title: str = "Baseline",
            on_error_message: str | None = None,
        ) -> None:
            if self._baseline_busy:
                return
            self._baseline_busy = True
            self._set_baseline_buttons_enabled(False)

            def _task() -> tuple[bool, object, str]:
                argv = [
                    sys.executable,
                    "-m",
                    "audioknob_gui.worker.cli",
                    "--registry",
                    _registry_path(),
                    "status",
                ]
                if _pkexec_available():
                    worker = _pick_root_worker_path()
                    argv = ["pkexec", worker, "--registry", _registry_path(), "status"]
                try:
                    p = subprocess.run(argv, text=True, capture_output=True)
                except Exception as e:
                    return False, {}, str(e)
                if not p.stdout.strip():
                    err = p.stderr.strip() or "Baseline scan failed"
                    if _is_pkexec_cancel(err):
                        return False, {}, _PKEXEC_CANCELLED
                    return False, {}, err
                try:
                    payload = json.loads(p.stdout)
                except Exception:
                    err = p.stderr.strip() or p.stdout.strip() or "Baseline parse failed"
                    if _is_pkexec_cancel(err):
                        return False, {}, _PKEXEC_CANCELLED
                    return False, {}, err
                status_map: dict[str, str] = {}
                for item in payload.get("statuses", []):
                    if isinstance(item, dict) and item.get("knob_id"):
                        status_map[str(item["knob_id"])] = str(item.get("status", "unknown"))
                return True, {"statuses": status_map}, ""

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                self._baseline_busy = False
                self._set_baseline_buttons_enabled(True)
                if not success:
                    if message == _PKEXEC_CANCELLED:
                        if on_cancel_message:
                            QMessageBox.information(self, on_cancel_title, on_cancel_message)
                        return
                    if on_error_message:
                        QMessageBox.warning(self, on_error_title, on_error_message + f"\n\n{message}")
                        return
                    _get_gui_logger().warning("baseline scan failed error=%s", message)
                    return
                if not isinstance(payload, dict):
                    return
                statuses = payload.get("statuses") or {}
                if not isinstance(statuses, dict) or not statuses:
                    return
                on_success(statuses)

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _ensure_baseline_state(self) -> None:
            if self._baseline_ready or self._baseline_busy:
                return
            def _on_success(statuses: dict[str, str]) -> None:
                self._set_baseline_state(statuses, source="initial")
                _get_gui_logger().info("baseline scan complete")

            self._start_baseline_scan(
                on_success=_on_success,
                on_cancel_title="Baseline Required",
                on_cancel_message=(
                    "Initial state capture was cancelled.\n\n"
                    "Run 'Re-check State' to capture baseline before making changes."
                ),
            )

        def _build_baseline_checks(self, statuses: dict[str, str]) -> dict[str, list[str]]:
            baseline_checks: dict[str, list[str]] = {}
            for knob in self.registry:
                status = statuses.get(knob.id)
                if status is None:
                    continue
                baseline_checks[knob.id] = self._collect_live_checks(knob, status_override=status)
            return baseline_checks

        def _on_capture_baseline(self) -> None:
            if self._baseline_busy:
                return
            default_name = str(Path.home() / "audioknob-baseline.json")
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Baseline Snapshot",
                default_name,
                "JSON Files (*.json)",
            )
            if not path:
                return
            if not path.lower().endswith(".json"):
                path = path + ".json"
            if not self._confirm_baseline_overwrite("Capture baseline"):
                return

            def _on_success(statuses: dict[str, str]) -> None:
                self._set_baseline_state(statuses, source="capture")
                snapshot = self._baseline_snapshot()
                if self._write_baseline_snapshot(path, snapshot):
                    QMessageBox.information(self, "Baseline", f"Baseline saved to:\n{path}")

            self._start_baseline_scan(
                on_success=_on_success,
                on_cancel_title="Baseline",
                on_cancel_message="Baseline capture was cancelled.",
                on_error_title="Baseline",
                on_error_message="Failed to capture baseline.",
            )

        def _on_import_baseline(self) -> None:
            if self._baseline_busy:
                return
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Baseline Snapshot",
                str(Path.home()),
                "JSON Files (*.json)",
            )
            if not path:
                return
            payload = self._load_baseline_snapshot(path)
            if not payload:
                return
            captured_at = payload.get("captured_at") or "unknown"
            if not self._confirm_baseline_overwrite(
                f"Import baseline from:\n{path}\nCaptured: {captured_at}"
            ):
                return
            statuses = payload.get("statuses")
            checks = payload.get("checks")
            if not isinstance(statuses, dict):
                return
            self._set_baseline_state(
                statuses,
                checks=checks if isinstance(checks, dict) else None,
                captured_at=payload.get("captured_at"),
                source="import",
            )
            QMessageBox.information(self, "Baseline", "Baseline imported.")

        def _sanitize_queue_actions(self, raw: object) -> dict[str, str]:
            if not isinstance(raw, dict):
                return {}
            valid_ids = {k.id for k in self.registry}
            out: dict[str, str] = {}
            for knob_id, action in raw.items():
                if knob_id in valid_ids and action in ("apply", "reset"):
                    out[knob_id] = action
            return out

        def _save_queue(self) -> None:
            self.state["queued_actions"] = dict(self._queued_actions)
            save_state(self.state)

        def _queue_requires_reboot(self) -> bool:
            queued = set(self._queued_actions.keys())
            return any(k.requires_reboot for k in self.registry if k.id in queued)

        def _queue_requires_root(self) -> bool:
            queued = set(self._queued_actions.keys())
            return any(k.requires_root for k in self.registry if k.id in queued)

        def _prune_queue_from_statuses(self) -> None:
            if not self._queued_actions:
                return
            keep: dict[str, str] = {}
            for kid, action in self._queued_actions.items():
                status = self._knob_statuses.get(kid)
                if action == "apply" and status in ("applied", "pending_reboot"):
                    continue
                if action == "reset" and status in ("not_applied", "not_applicable", "sys_default"):
                    continue
                keep[kid] = action
            if keep != self._queued_actions:
                self._queued_actions = keep
                self._save_queue()

        def _update_queue_ui(self) -> None:
            count = len(self._queued_actions)
            if count:
                self.queue_label.setText(f"Queued: {count}")
                self.queue_label.setVisible(True)
                tip = "Apply queued changes"
                tip_reboot = "Apply queued changes and reboot after"
                if self._queue_requires_root():
                    tip += " (password prompt may appear)"
                    tip_reboot += " (password prompt may appear)"
                requires_reboot = self._queue_requires_reboot()
                if requires_reboot:
                    tip += " (reboot required to take effect)"
                self.btn_apply_queue.setToolTip(tip)
                self.btn_apply_queue_reboot.setToolTip(tip_reboot)
                self.btn_apply_queue.setVisible(True)
                self.btn_apply_queue_reboot.setVisible(requires_reboot)
            else:
                self.queue_label.setVisible(False)
                self.btn_apply_queue.setVisible(False)
                self.btn_apply_queue_reboot.setVisible(False)
            enabled = count > 0 and not self._queue_busy
            if not self._baseline_ready:
                enabled = False
            self.btn_apply_queue.setEnabled(enabled)
            self.btn_apply_queue_reboot.setEnabled(enabled and self._queue_requires_reboot())
            self.btn_reset.setEnabled(self._baseline_ready)

        def _apply_queue_button_state(self, btn: QPushButton, knob_id: str, action: str) -> None:
            if self._queued_actions.get(knob_id) == action:
                btn.setStyleSheet(
                    "QPushButton {"
                    " background-color: #5f8f6b;"
                    " color: #e0e0e0;"
                    " border: 1px solid #6b9a76;"
                    "}"
                    "QPushButton:hover {"
                    " background-color: #699a76;"
                    "}"
                    "QPushButton:pressed {"
                    " background-color: #4e7a5a;"
                    "}"
                )
                tip = "Queued to apply. Click to remove from queue."
                if action == "reset":
                    tip = "Queued to reset. Click to remove from queue."
                btn.setToolTip(tip)
            else:
                btn.setStyleSheet("")

        def _on_recheck_state(self) -> None:
            if self._status_busy:
                return
            _get_gui_logger().info("state recheck requested")
            if not self._baseline_ready:
                self._ensure_baseline_state()
                return
            self._refresh_statuses()

        def _refresh_statuses(self) -> None:
            """Fetch current status of all knobs (async)."""
            if self._status_busy:
                return
            self._status_busy = True

            def _task() -> tuple[bool, object, str]:
                try:
                    statuses: dict[str, str] = {}
                    argv = [
                        sys.executable,
                        "-m",
                        "audioknob_gui.worker.cli",
                        "--registry",
                        _registry_path(),
                        "status",
                    ]
                    p = subprocess.run(argv, text=True, capture_output=True, timeout=15)
                    if p.returncode == 0:
                        data = json.loads(p.stdout)
                        for item in data.get("statuses", []):
                            statuses[item["knob_id"]] = item["status"]
                    return True, statuses, ""
                except Exception as exc:
                    return False, {}, str(exc)

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                self._status_busy = False
                if success and isinstance(payload, dict):
                    self._knob_statuses = payload
                else:
                    self._knob_statuses = {}
                self._apply_session_dependent_statuses()
                self._update_reboot_banner()
                self._prune_queue_from_statuses()
                self._update_queue_ui()
                self._populate()

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _apply_session_dependent_statuses(self) -> None:
            status = self._knob_statuses.get("rt_limits_audio_group")
            if status == "applied" and not self._rt_limits_active():
                self._knob_statuses["rt_limits_audio_group"] = "pending_reboot"
            status = self._knob_statuses.get("audio_group_membership")
            if status == "applied" and not self._audio_groups_active():
                self._knob_statuses["audio_group_membership"] = "pending_reboot"
            self._apply_baseline_statuses()

        def _apply_baseline_statuses(self) -> None:
            baseline = self.state.get("baseline_statuses")
            if not isinstance(baseline, dict) or not baseline:
                return
            baseline_ts = self._parse_baseline_timestamp()
            tx_times, root_tx_unknown = self._collect_transaction_times()
            baseline_user_txid = self.state.get("baseline_txid_user")
            baseline_root_txid = self.state.get("baseline_txid_root")
            last_user_txid = self.state.get("last_user_txid")
            last_root_txid = self.state.get("last_root_txid")
            manual_baseline = self._baseline_is_manual()
            user_diverged = (
                isinstance(baseline_user_txid, str)
                and isinstance(last_user_txid, str)
                and baseline_user_txid != last_user_txid
            )
            root_diverged = (
                isinstance(baseline_root_txid, str)
                and isinstance(last_root_txid, str)
                and baseline_root_txid != last_root_txid
            )
            for knob in self.registry:
                current = self._knob_statuses.get(knob.id)
                if current in ("pending_reboot", "running", "unknown", "read_only", "not_applicable", "partial"):
                    continue
                if not manual_baseline and root_tx_unknown and knob.requires_root:
                    continue
                base = baseline.get(knob.id)
                if base is None:
                    continue
                if base in ("unknown", "not_applicable"):
                    continue
                tx_time = tx_times.get(knob.id)
                if not manual_baseline:
                    if tx_time is not None and baseline_ts is not None and baseline_ts >= tx_time:
                        continue
                    if tx_time is not None and baseline_ts is None:
                        continue
                    if tx_time is None:
                        if knob.requires_root and root_diverged:
                            continue
                        if not knob.requires_root and user_diverged:
                            continue
                if current == base:
                    self._knob_statuses[knob.id] = "sys_default"
                    continue
                if current == "applied":
                    continue
                self._knob_statuses[knob.id] = "deviated"

        def _parse_baseline_timestamp(self) -> float | None:
            raw = self.state.get("baseline_captured_at")
            if not isinstance(raw, str) or not raw:
                return None
            try:
                iso = raw.replace("Z", "+00:00")
                return datetime.fromisoformat(iso).timestamp()
            except Exception:
                return None

        def _collect_transaction_times(self) -> tuple[dict[str, float], bool]:
            """Return earliest transaction time per knob id and root access flag."""
            from audioknob_gui.core.paths import default_paths
            from audioknob_gui.core.transaction import list_transactions

            tx_times: dict[str, float] = {}
            root_unknown = False
            paths = default_paths()

            for tx in list_transactions(paths.user_state_dir):
                ts = tx.get("timestamp")
                if not isinstance(ts, (int, float)):
                    continue
                for knob_id in tx.get("applied", []):
                    if not isinstance(knob_id, str):
                        continue
                    prev = tx_times.get(knob_id)
                    if prev is None or ts < prev:
                        tx_times[knob_id] = float(ts)

            root_tx_dir = Path(paths.var_lib_dir) / "transactions"
            if root_tx_dir.exists():
                if not os.access(root_tx_dir, os.R_OK | os.X_OK):
                    root_unknown = True
                    return tx_times, root_unknown
                try:
                    for entry in root_tx_dir.iterdir():
                        if not entry.is_dir():
                            continue
                        manifest_path = entry / "manifest.json"
                        if manifest_path.exists() and not os.access(manifest_path, os.R_OK):
                            root_unknown = True
                            return tx_times, root_unknown
                except PermissionError:
                    root_unknown = True
                    return tx_times, root_unknown
                except Exception:
                    root_unknown = True
                    return tx_times, root_unknown

            try:
                root_txs = list_transactions(paths.var_lib_dir)
            except PermissionError:
                root_unknown = True
                return tx_times, root_unknown
            except Exception:
                root_unknown = True
                return tx_times, root_unknown

            for tx in root_txs:
                ts = tx.get("timestamp")
                if not isinstance(ts, (int, float)):
                    continue
                for knob_id in tx.get("applied", []):
                    if not isinstance(knob_id, str):
                        continue
                    prev = tx_times.get(knob_id)
                    if prev is None or ts < prev:
                        tx_times[knob_id] = float(ts)

            return tx_times, root_unknown

        def _rt_limits_active(self) -> bool:
            try:
                import resource
            except Exception:
                return False

            try:
                rt_soft, _ = resource.getrlimit(resource.RLIMIT_RTPRIO)
                mem_soft, _ = resource.getrlimit(resource.RLIMIT_MEMLOCK)
            except Exception:
                return False

            rt_ok = rt_soft == resource.RLIM_INFINITY or rt_soft >= 95
            mem_ok = mem_soft == resource.RLIM_INFINITY
            return rt_ok and mem_ok

        def _audio_groups_active(self) -> bool:
            try:
                from audioknob_gui.platform.detect import get_missing_groups
            except Exception:
                return True

            try:
                return len(get_missing_groups()) == 0
            except Exception:
                return True

        def _is_process_running(self, names: list[str]) -> bool:
            if shutil.which("pgrep"):
                for name in names:
                    r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
                    if r.returncode == 0:
                        return True
            r = subprocess.run(["ps", "-eo", "comm"], capture_output=True, text=True)
            if r.returncode != 0:
                return False
            for line in r.stdout.splitlines():
                cmd = line.strip()
                if cmd in names:
                    return True
            return False

        def _prime_qjackctl_preset(self) -> None:
            logger = _get_gui_logger()
            path = Path("~/.config/rncbc.org/QjackCtl.conf").expanduser()
            if path.exists():
                return
            logger.info("qjackctl config missing; will be created on apply")

        def _update_reboot_banner(self) -> None:
            needs_reboot = any(v == "pending_reboot" for v in self._knob_statuses.values())
            self._needs_reboot = needs_reboot
            self.reboot_banner.setText("Reboot required for pending changes." if needs_reboot else "")
            self.reboot_banner.setVisible(needs_reboot)
            self.reboot_button.setVisible(needs_reboot)
            self.reboot_button.setEnabled(needs_reboot)

        def _make_apply_button(self, text: str = "Apply") -> QPushButton:
            """Create an Apply button."""
            btn = QPushButton(text)
            # Ensure button labels don't clip at common font sizes and narrow columns.
            btn.setMinimumWidth(80)
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            btn.setFocusPolicy(Qt.NoFocus)
            return btn

        def _make_reset_button(self, text: str = "Reset") -> QPushButton:
            """Create a Reset button."""
            btn = QPushButton(text)
            btn.setMinimumWidth(80)
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            btn.setFocusPolicy(Qt.NoFocus)
            return btn

        def _make_action_button(self, text: str) -> QPushButton:
            """Create an action button."""
            btn = QPushButton(text)
            btn.setMinimumWidth(80)
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            btn.setFocusPolicy(Qt.NoFocus)
            return btn

        def _apply_busy_state(self, btn: QPushButton, *, busy: bool) -> None:
            if busy:
                btn.setText("Working...")
                btn.setEnabled(False)

        def _apply_baseline_lock(self, btn: QPushButton) -> None:
            if self._baseline_ready:
                return
            label = btn.text().strip().lower()
            if label not in ("apply", "reset", "install", "join", "leave"):
                return
            btn.setEnabled(False)
            btn.setToolTip("Initial state scan pending. Finish baseline scan before changes.")


        def _install_hover_tracking(self, widget: QWidget, row: int) -> None:
            widget.setProperty("hover_row", row)
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

        def _set_action_cell(self, row: int, widget: QWidget) -> None:
            self._install_hover_tracking(widget, row)
            if isinstance(widget, QPushButton):
                self._apply_baseline_lock(widget)
            self.table.setCellWidget(row, 2, widget)

        def _status_display(self, status: str) -> tuple[str, str]:
            """Return (display_text, color) for a status."""
            # Handle test results: "result:12 µs" → "12 µs"
            if status.startswith("result:"):
                return (status[7:], "#1976d2")  # Blue
            
            mapping = {
                "applied": ("✓ Applied", "#2e7d32"),      # Green
                "sys_default": ("Sys Default", "#1976d2"), # Blue
                "deviated": ("Deviated", "#607d8b"),      # Blue-gray
                "not_applied": ("—", "#757575"),          # Gray dash
                "not_applicable": ("N/A", "#9e9e9e"),     # Gray N/A
                "partial": ("◐ Partial", "#f57c00"),      # Orange
                "pending_reboot": ("⟳ Reboot", "#f57c00"), # Orange - needs reboot
                "read_only": ("—", "#9e9e9e"),            # Gray dash
                "unknown": ("—", "#9e9e9e"),              # Gray dash
                "running": ("⏳ Updating", "#1976d2"),    # Blue spinner
                "done": ("✓", "#2e7d32"),                 # Green check
                "error": ("✗", "#d32f2f"),                # Red X
            }
            return mapping.get(status, ("—", "#9e9e9e"))

        def _populate(self) -> None:
            # Disable sorting during population to avoid issues
            self.table.setSortingEnabled(False)
            self.table.clearSpans()
            self._refresh_core_plan_summary()
            reboot_gate_enabled = bool(self.state.get("enable_reboot_knobs", False))
            advanced_enabled = bool(self.state.get("advanced_mode_enabled", False))
            group_pending = self._knob_statuses.get("audio_group_membership") == "pending_reboot"
            desktop_kind = self._detect_desktop()
            advanced_knobs = self._advanced_knob_ids()
            visible_knobs = self._visible_knobs()
            ordered: list[object] = []
            grouping_mode = self._grouping_mode()

            def _sort_key(k, col: int) -> tuple:
                status = self._knob_statuses.get(k.id, "unknown")
                status_order = {
                    "applied": 0,
                    "pending_reboot": 1,
                    "deviated": 2,
                    "partial": 3,
                    "sys_default": 4,
                    "not_applied": 5,
                    "not_applicable": 6,
                    "unknown": 7,
                }
                risk_order = {"low": 0, "medium": 1, "high": 2}

                if col == 4:
                    req = self._requirements_label(k, advanced_knobs).lower()
                    return (req, k.title.lower())
                if col == 5:
                    return (status_order.get(status, 99), k.title.lower())
                if col == 7:
                    return (str(k.category).lower(), k.title.lower())
                if col == 8:
                    return (risk_order.get(str(k.risk_level), 99), k.title.lower())
                if col == 9:
                    sys_label = self._sys_label_for_knob(k).lower()
                    return (sys_label, k.title.lower())
                if col in (0, 1, 2, 3, 6):
                    return (k.title.lower(),)
                return (status_order.get(status, 99), k.title.lower())

            category_order = [
                "cpu",
                "irq",
                "kernel",
                "permissions",
                "power",
                "services",
                "stack",
                "vm",
                "testing",
            ]

            def _sorted_items(items: list[object], *, force_title: bool = False) -> list[object]:
                if self._sort_column is None:
                    return items
                if force_title:
                    return sorted(items, key=lambda k: k.title.lower(), reverse=self._sort_descending)
                col = int(self._sort_column)
                return sorted(items, key=lambda k: _sort_key(k, col), reverse=self._sort_descending)

            CATEGORY_HEADER = object()
            CATEGORY_SEPARATOR = object()
            if grouping_mode is None:
                ordered = _sorted_items(list(visible_knobs))
            elif grouping_mode == "category":
                by_category: dict[str, list[object]] = {}
                for k in visible_knobs:
                    key = str(getattr(k, "category", "uncategorized"))
                    by_category.setdefault(key, []).append(k)
                known_categories = set(category_order)
                extra_categories = sorted(set(by_category.keys()) - known_categories)
                ordered_categories = (
                    [(c, self._category_label(c)) for c in category_order]
                    + [(c, self._category_label(c)) for c in extra_categories]
                )
                if self._sort_column == 7 and self._sort_descending:
                    ordered_categories = list(reversed(ordered_categories))
                for cat_key, cat_label in ordered_categories:
                    items = by_category.get(cat_key, [])
                    if not items:
                        continue
                    ordered.append((CATEGORY_HEADER, cat_label))
                    ordered.extend(_sorted_items(items, force_title=self._sort_column is not None))
                    ordered.append(CATEGORY_SEPARATOR)
                if ordered and ordered[-1] is CATEGORY_SEPARATOR:
                    ordered.pop()
            elif grouping_mode == "requirements":
                by_req: dict[str, list[object]] = {}
                for k in visible_knobs:
                    label = self._requirements_label(k, advanced_knobs)
                    by_req.setdefault(label, []).append(k)
                req_order = ["—", "A", "R", "G", "A R", "A G", "R G", "A R G"]
                extra_labels = sorted(set(by_req.keys()) - set(req_order))
                ordered_labels = req_order + extra_labels
                if self._sort_descending:
                    ordered_labels = list(reversed(ordered_labels))
                for label in ordered_labels:
                    items = by_req.get(label, [])
                    if not items:
                        continue
                    ordered.append((CATEGORY_HEADER, label, self._requirements_group_tooltip(label)))
                    ordered.extend(_sorted_items(items, force_title=True))
                    ordered.append(CATEGORY_SEPARATOR)
                if ordered and ordered[-1] is CATEGORY_SEPARATOR:
                    ordered.pop()
            elif grouping_mode == "status":
                status_labels = {
                    "applied": "Applied",
                    "pending_reboot": "Reboot Required",
                    "deviated": "Deviated",
                    "partial": "Partial",
                    "sys_default": "Sys Default",
                    "not_applied": "Not Applied",
                    "not_applicable": "N/A",
                    "read_only": "Read Only",
                    "unknown": "Unknown",
                }
                status_order = [
                    "applied",
                    "pending_reboot",
                    "deviated",
                    "partial",
                    "sys_default",
                    "not_applied",
                    "not_applicable",
                    "read_only",
                    "unknown",
                ]
                by_status: dict[str, list[object]] = {}
                for k in visible_knobs:
                    status = self._knob_statuses.get(k.id, "unknown")
                    key = status if status in status_labels else "unknown"
                    by_status.setdefault(key, []).append(k)
                extra_statuses = sorted(set(by_status.keys()) - set(status_order))
                ordered_statuses = status_order + extra_statuses
                if self._sort_descending:
                    ordered_statuses = list(reversed(ordered_statuses))
                for key in ordered_statuses:
                    items = by_status.get(key, [])
                    if not items:
                        continue
                    label = status_labels.get(key, key)
                    ordered.append((CATEGORY_HEADER, label))
                    ordered.extend(_sorted_items(items, force_title=True))
                    ordered.append(CATEGORY_SEPARATOR)
                if ordered and ordered[-1] is CATEGORY_SEPARATOR:
                    ordered.pop()
            elif grouping_mode == "risk":
                risk_labels = {"low": "Low", "medium": "Medium", "high": "High", "unknown": "Unknown"}
                risk_order = ["low", "medium", "high", "unknown"]
                by_risk: dict[str, list[object]] = {}
                for k in visible_knobs:
                    risk = str(getattr(k, "risk_level", "unknown")).lower()
                    key = risk if risk in risk_labels else "unknown"
                    by_risk.setdefault(key, []).append(k)
                extra_risks = sorted(set(by_risk.keys()) - set(risk_order))
                ordered_risks = risk_order + extra_risks
                if self._sort_descending:
                    ordered_risks = list(reversed(ordered_risks))
                for key in ordered_risks:
                    items = by_risk.get(key, [])
                    if not items:
                        continue
                    ordered.append((CATEGORY_HEADER, risk_labels.get(key, key.title())))
                    ordered.extend(_sorted_items(items, force_title=True))
                    ordered.append(CATEGORY_SEPARATOR)
                if ordered and ordered[-1] is CATEGORY_SEPARATOR:
                    ordered.pop()

            self.table.setRowCount(len(ordered))
            self._row_dim = [False] * len(ordered)

            for r, k in enumerate(ordered):
                if isinstance(k, tuple) and k and k[0] is CATEGORY_HEADER:
                    label = str(k[1])
                    tooltip = str(k[2]) if len(k) > 2 and k[2] else ""
                    header_bg = QColor("#1f1f1f")
                    for c in range(self.table.columnCount()):
                        self.table.removeCellWidget(r, c)
                    self.table.setSpan(r, 0, 1, self.table.columnCount())
                    header_item = QTableWidgetItem(label)
                    header_item.setFlags(Qt.ItemIsEnabled)
                    header_item.setForeground(QColor("#cfcfcf"))
                    header_item.setBackground(header_bg)
                    header_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    header_font = header_item.font()
                    header_font.setBold(True)
                    header_item.setFont(header_font)
                    if tooltip:
                        header_item.setToolTip(tooltip)
                    self.table.setItem(r, 0, header_item)
                    for c in range(1, self.table.columnCount()):
                        filler = QTableWidgetItem("")
                        filler.setFlags(Qt.ItemIsEnabled)
                        filler.setBackground(header_bg)
                        self.table.setItem(r, c, filler)
                    continue
                if k is CATEGORY_SEPARATOR:
                    sep_bg = QColor("#1f1f1f")
                    for c in range(self.table.columnCount()):
                        self.table.removeCellWidget(r, c)
                    sep = QTableWidgetItem("")
                    sep.setFlags(Qt.ItemIsEnabled)
                    sep.setForeground(QColor("#9e9e9e"))
                    sep.setBackground(sep_bg)
                    sep.setTextAlignment(Qt.AlignCenter)
                    self.table.setSpan(r, 0, 1, self.table.columnCount())
                    self.table.setItem(r, 0, sep)
                    for c in range(1, self.table.columnCount()):
                        filler = QTableWidgetItem("")
                        filler.setFlags(Qt.ItemIsEnabled)
                        filler.setBackground(sep_bg)
                        self.table.setItem(r, c, filler)
                    try:
                        self.table.setRowHeight(r, 10)
                    except Exception:
                        pass
                    continue
                status = self._knob_statuses.get(k.id, "unknown")
                busy = k.id in self._busy_knobs
                display_status = "running" if busy else status
                not_applicable = (status == "not_applicable")
                not_applicable_reason = "Not available on this system"
                if k.id == "disable_tracker" and desktop_kind == "kde":
                    not_applicable = True
                    not_applicable_reason = "Requires GNOME desktop"
                elif k.id == "disable_baloo" and desktop_kind == "gnome":
                    not_applicable = True
                    not_applicable_reason = "Requires KDE desktop"
                elif k.id == "power_profile_performance" and not_applicable:
                    backend = self._power_profile_backend_from_state()
                    if backend == "powerprofilesctl":
                        not_applicable_reason = "Requires powerprofilesctl"
                    elif backend == "tuned":
                        not_applicable_reason = "Requires tuned-adm"
                    else:
                        not_applicable_reason = "Requires powerprofilesctl or tuned-adm"
                locked_bg = QColor("#1f1f1f")
                locked_fg = QColor("#7a7a7a")
                locked_style = (
                    "QPushButton { background-color: #1f1f1f; color: #7a7a7a; border: 1px solid #2a2a2a; }"
                    "QPushButton:hover { background-color: #1f1f1f; color: #7a7a7a; border: 1px solid #2a2a2a; }"
                    "QPushButton:pressed { background-color: #1f1f1f; color: #7a7a7a; border: 1px solid #2a2a2a; }"
                )

                # Check requirements
                group_ok = self._knob_group_ok(k)
                group_pending_lock = bool(k.requires_groups) and group_pending
                if group_pending_lock:
                    group_ok = False
                commands_ok = self._knob_commands_ok(k)
                missing_cmds = self._knob_missing_commands(k)
                reboot_gate_lock = bool(k.requires_reboot) and not reboot_gate_enabled and status not in ("applied", "pending_reboot")
                advanced_gate_lock = k.id in advanced_knobs and not advanced_enabled and status not in ("applied", "pending_reboot")
                reboot_dep_lock = (not reboot_gate_enabled) and bool(k.requires_groups)
                locked = not group_ok or not commands_ok or reboot_gate_lock or reboot_dep_lock or advanced_gate_lock
                row_dim = locked or not_applicable
                self._row_dim[r] = row_dim
                row_dim = locked or not_applicable
                
                # Determine lock reason
                lock_reason = ""
                if group_pending_lock:
                    lock_reason = f"Groups pending reboot: {', '.join(k.requires_groups)}"
                elif reboot_dep_lock:
                    lock_reason = f"Requires groups: {', '.join(k.requires_groups)} (enable reboot-required changes)"
                elif not group_ok:
                    lock_reason = f"Join groups: {', '.join(k.requires_groups)}"
                elif reboot_gate_lock:
                    lock_reason = f"Reboot required: {k.title}"
                elif advanced_gate_lock:
                    lock_reason = "Enable advanced knobs"
                elif not commands_ok:
                    lock_reason = f"Install: {', '.join(missing_cmds)}"
                
                # Column 0: Info button
                info_btn = QPushButton("i")
                info_btn.setFixedWidth(28)
                info_btn.setToolTip("Show details")
                info_btn.setFocusPolicy(Qt.NoFocus)
                info_btn.clicked.connect(lambda _, kid=k.id: self._show_knob_info(kid))
                self._install_hover_tracking(info_btn, r)
                if row_dim:
                    info_btn.setStyleSheet(locked_style)
                info_bg = QTableWidgetItem("")
                info_bg.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if row_dim:
                    info_bg.setBackground(locked_bg)
                self.table.setItem(r, 0, info_bg)
                self.table.setCellWidget(r, 0, info_btn)

                # Column 1: Knob title (gray if locked)
                title_item = QTableWidgetItem(k.title)
                title_item.setData(Qt.UserRole, k.id)  # Store ID for lookup
                if row_dim:
                    title_item.setForeground(locked_fg)
                    title_item.setBackground(locked_bg)
                if locked:
                    title_item.setToolTip(lock_reason)
                elif not_applicable:
                    title_item.setToolTip(not_applicable_reason)
                self.table.setItem(r, 1, title_item)

                # Column 4: Requirements
                req_item = QTableWidgetItem(self._requirements_label(k, advanced_knobs))
                req_item.setToolTip(self._requirements_tooltip(k, advanced_knobs))
                if row_dim:
                    req_item.setForeground(locked_fg)
                    req_item.setBackground(locked_bg)
                self.table.setItem(r, 4, req_item)

                # Column 5: Status (with color)
                if locked:
                    status_item = QTableWidgetItem("Locked")
                    status_item.setForeground(locked_fg)
                    status_item.setToolTip(lock_reason)
                elif not_applicable:
                    status_item = QTableWidgetItem("N/A")
                    status_item.setForeground(locked_fg)
                    status_item.setToolTip(not_applicable_reason)
                else:
                    status_text, status_color = self._status_display(display_status)
                    status_item = QTableWidgetItem(status_text)
                    status_item.setForeground(QColor(status_color))
                    tooltip_map = {
                        "applied": "Baseline captured; optimization applied successfully.",
                        "sys_default": "Baseline captured before optimization.",
                        "deviated": "Differs from both baseline and expected optimization.",
                        "partial": "Partially applied; see Status details.",
                        "pending_reboot": "Applied in boot config; reboot required.",
                        "not_applied": "Not applied.",
                        "not_applicable": "Not available on this system.",
                        "read_only": "Read-only check.",
                        "unknown": "Status unknown.",
                        "running": "Updating...",
                        "done": "Completed.",
                        "error": "Error during operation.",
                    }
                    if display_status.startswith("result:"):
                        status_item.setToolTip("Test result.")
                    else:
                        tip = tooltip_map.get(display_status)
                        if tip:
                            status_item.setToolTip(tip)
                if row_dim:
                    status_item.setBackground(locked_bg)
                self.table.setItem(r, 5, status_item)

                # Column 7: Category
                cat_item = QTableWidgetItem(self._category_label(str(k.category)))
                if row_dim:
                    cat_item.setForeground(locked_fg)
                    cat_item.setBackground(locked_bg)
                self.table.setItem(r, 7, cat_item)

                # Column 8: Risk
                risk_item = QTableWidgetItem(str(k.risk_level))
                if row_dim:
                    risk_item.setForeground(locked_fg)
                    risk_item.setBackground(locked_bg)
                self.table.setItem(r, 8, risk_item)

                # Column 9: CLI
                sys_item = QTableWidgetItem(self._sys_label_for_knob(k))
                if row_dim:
                    sys_item.setForeground(locked_fg)
                    sys_item.setBackground(locked_bg)
                self.table.setItem(r, 9, sys_item)

                # Column 2: Action button (context-sensitive)
                if k.id == "audio_group_membership":
                    # Special: group membership knob
                    label = "Leave" if status == "applied" else "Join"
                    btn = self._make_reset_button(label) if label == "Leave" else self._make_apply_button(label)
                    if label == "Leave":
                        btn.clicked.connect(self._on_leave_groups)
                    else:
                        btn.clicked.connect(self._on_join_groups)
                    self._apply_busy_state(btn, busy=busy)
                    if locked:
                        btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)
                elif group_pending_lock:
                    btn = self._make_action_button("🔒")
                    btn.setEnabled(False)
                    btn.setToolTip(lock_reason)
                    btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)
                elif reboot_dep_lock:
                    btn = self._make_action_button("🔒")
                    btn.setEnabled(False)
                    btn.setToolTip(lock_reason)
                    btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)
                elif not group_ok:
                    # Locked: user needs to join groups first
                    btn = self._make_action_button("🔒")
                    btn.setEnabled(False)
                    btn.setToolTip(lock_reason)
                    btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)
                elif reboot_gate_lock:
                    btn = self._make_action_button("🔒")
                    btn.setEnabled(False)
                    btn.setToolTip(lock_reason)
                    btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)
                elif advanced_gate_lock:
                    btn = self._make_action_button("🔒")
                    btn.setEnabled(False)
                    btn.setToolTip(lock_reason)
                    btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)
                elif not commands_ok:
                    # Locked: needs package install
                    btn = self._make_action_button("Install")
                    btn.setToolTip(f"Install: {', '.join(missing_cmds)}")
                    btn.clicked.connect(lambda _, cmds=missing_cmds: self._on_install_packages(cmds))
                    btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)
                elif not_applicable:
                    btn = self._make_action_button("N/A")
                    btn.setEnabled(False)
                    btn.setToolTip(not_applicable_reason)
                    btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)
                elif k.id == "stack_detect":
                    btn = self._make_action_button("View")
                    btn.clicked.connect(self.on_view_stack)
                    self._set_action_cell(r, btn)
                elif k.id == "scheduler_jitter_test":
                    btn = self._make_action_button("Test")
                    if busy:
                        btn.setText("Working...")
                        btn.setEnabled(False)
                    else:
                        btn.clicked.connect(lambda _, kid=k.id: self.on_run_test(kid))
                    self._set_action_cell(r, btn)
                elif k.id == "blocker_check":
                    btn = self._make_action_button("Scan")
                    btn.clicked.connect(self.on_check_blockers)
                    self._set_action_cell(r, btn)
                elif k.id == "pipewire_quantum" and not locked:
                    # Action column: Apply/Reset button
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
                        self._apply_queue_button_state(btn, k.id, "reset")
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
                        self._apply_queue_button_state(btn, k.id, "apply")
                    self._apply_busy_state(btn, busy=busy)
                    self._set_action_cell(r, btn)

                    # Config column: quantum selector
                    q_combo = QComboBox()
                    q_combo.setMinimumWidth(80)
                    q_combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
                    values = [32, 64, 128, 256, 512, 1024]
                    for v in values:
                        q_combo.addItem(str(v), v)

                    current = self._pipewire_quantum_from_state()
                    if current is None and k.impl:
                        try:
                            current = int(k.impl.params.get("quantum")) if k.impl.params.get("quantum") is not None else None
                        except Exception:
                            current = None
                    q_combo.blockSignals(True)
                    if current in values:
                        q_combo.setCurrentIndex(values.index(int(current)))
                    q_combo.blockSignals(False)

                    def _on_change(_: int, *, _combo: QComboBox = q_combo) -> None:
                        # Capture the correct combo; otherwise a later reassignment in _populate()
                        # can cause late-binding bugs (e.g. writing sample rate into quantum).
                        self.state["pipewire_quantum"] = int(_combo.currentData())
                        save_state(self.state)
                        # Optimistic UI: config changed, so action should become Apply until proven otherwise.
                        self._knob_statuses["pipewire_quantum"] = "not_applied"
                        self._refresh_statuses()
                        self._populate()

                    q_combo.currentIndexChanged.connect(_on_change)
                    self._install_hover_tracking(q_combo, r)
                    self.table.setCellWidget(r, 3, q_combo)

                elif k.id == "pipewire_sample_rate" and not locked:
                    # Action column: Apply/Reset button
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
                        self._apply_queue_button_state(btn, k.id, "reset")
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
                        self._apply_queue_button_state(btn, k.id, "apply")
                    self._apply_busy_state(btn, busy=busy)
                    self._set_action_cell(r, btn)

                    # Config column: sample rate selector
                    r_combo = QComboBox()
                    r_combo.setMinimumWidth(80)
                    r_combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
                    values = [44100, 48000, 88200, 96000, 192000]
                    for v in values:
                        r_combo.addItem(f"{v} Hz", v)

                    current = self._pipewire_sample_rate_from_state()
                    if current is None and k.impl:
                        try:
                            current = int(k.impl.params.get("rate")) if k.impl.params.get("rate") is not None else None
                        except Exception:
                            current = None
                    r_combo.blockSignals(True)
                    if current in values:
                        r_combo.setCurrentIndex(values.index(int(current)))
                    r_combo.blockSignals(False)

                    def _on_rate_change(_: int, *, _combo: QComboBox = r_combo) -> None:
                        self.state["pipewire_sample_rate"] = int(_combo.currentData())
                        save_state(self.state)
                        self._knob_statuses["pipewire_sample_rate"] = "not_applied"
                        self._refresh_statuses()
                        self._populate()

                    r_combo.currentIndexChanged.connect(_on_rate_change)
                    self._install_hover_tracking(r_combo, r)
                    self.table.setCellWidget(r, 3, r_combo)
                elif k.id == "qjackctl_server_prefix_rt":
                    # Normal apply/reset button in Action column
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
                        self._apply_queue_button_state(btn, k.id, "reset")
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
                        self._apply_queue_button_state(btn, k.id, "apply")
                    self._apply_busy_state(btn, busy=busy)
                    if locked:
                        btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)

                    # Config column: CPU core selection
                    cfg_btn = self._make_action_button("Cores")
                    cfg_btn.setToolTip("Configure CPU cores for pinning")
                    cfg_btn.setFocusPolicy(Qt.NoFocus)
                    cfg_btn.clicked.connect(lambda _, kid=k.id: self.on_configure_knob(kid))
                    self._install_hover_tracking(cfg_btn, r)
                    if locked:
                        cfg_btn.setEnabled(False)
                        cfg_btn.setStyleSheet(locked_style)
                    self.table.setCellWidget(r, 3, cfg_btn)
                elif k.id == "power_profile_performance":
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
                        self._apply_queue_button_state(btn, k.id, "reset")
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
                        self._apply_queue_button_state(btn, k.id, "apply")
                    self._apply_busy_state(btn, busy=busy)
                    if locked:
                        btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)

                    backend_combo = QComboBox()
                    backend_combo.setMinimumWidth(130)
                    backend_combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
                    backend_combo.addItem("Auto", "auto")
                    backend_combo.addItem("powerprofilesctl", "powerprofilesctl")
                    backend_combo.addItem("tuned", "tuned")
                    backend_combo.setToolTip(
                        "Power profile backend: auto uses the active backend; tuned uses latency-performance."
                    )
                    current_backend = self._power_profile_backend_from_state()
                    if current_backend not in ("auto", "powerprofilesctl", "tuned"):
                        current_backend = "auto"
                    backend_combo.blockSignals(True)
                    for idx in range(backend_combo.count()):
                        if backend_combo.itemData(idx) == current_backend:
                            backend_combo.setCurrentIndex(idx)
                            break
                    backend_combo.blockSignals(False)

                    def _on_backend_change(_: int, *, _combo: QComboBox = backend_combo) -> None:
                        self.state["power_profile_backend"] = str(_combo.currentData())
                        save_state(self.state)
                        # Config changed; force re-evaluation until apply succeeds.
                        self._knob_statuses["power_profile_performance"] = "not_applied"
                        self._refresh_statuses()
                        self._populate()

                    backend_combo.currentIndexChanged.connect(_on_backend_change)
                    self._install_hover_tracking(backend_combo, r)

                    config_locked = group_pending_lock or reboot_dep_lock or reboot_gate_lock or advanced_gate_lock
                    if config_locked:
                        backend_combo.setEnabled(False)
                        backend_combo.setStyleSheet(
                            "QComboBox { background-color: #1f1f1f; color: #7a7a7a; border: 1px solid #2a2a2a; }"
                        )
                    self.table.setCellWidget(r, 3, backend_combo)
                elif k.id == "irq_pinning":
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
                        self._apply_queue_button_state(btn, k.id, "reset")
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
                        self._apply_queue_button_state(btn, k.id, "apply")
                    self._apply_busy_state(btn, busy=busy)
                    if locked:
                        btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)

                    cfg_btn = self._make_action_button("Devices")
                    cfg_btn.setToolTip("Configure devices and CPU cores")
                    cfg_btn.setFocusPolicy(Qt.NoFocus)
                    cfg_btn.clicked.connect(lambda _, kid=k.id: self.on_configure_knob(kid))
                    self._install_hover_tracking(cfg_btn, r)
                    if locked:
                        cfg_btn.setEnabled(False)
                        cfg_btn.setStyleSheet(locked_style)
                    self.table.setCellWidget(r, 3, cfg_btn)
                elif k.id in ("kernel_isolcpus", "kernel_nohz_full", "kernel_rcu_nocbs", "kernel_irqaffinity"):
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
                        self._apply_queue_button_state(btn, k.id, "reset")
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
                        self._apply_queue_button_state(btn, k.id, "apply")
                    self._apply_busy_state(btn, busy=busy)
                    if locked:
                        btn.setStyleSheet(locked_style)
                    self._set_action_cell(r, btn)

                    cfg_btn = self._make_action_button("Cores")
                    cfg_btn.setToolTip("Configure CPU cores")
                    cfg_btn.setFocusPolicy(Qt.NoFocus)
                    cfg_btn.clicked.connect(lambda _, kid=k.id: self.on_configure_knob(kid))
                    self._install_hover_tracking(cfg_btn, r)
                    if locked:
                        cfg_btn.setEnabled(False)
                        cfg_btn.setStyleSheet(locked_style)
                    self.table.setCellWidget(r, 3, cfg_btn)
                elif k.impl is None:
                    # Placeholder knob - not implemented yet
                    btn = self._make_action_button("—")
                    btn.setEnabled(False)
                    btn.setToolTip("Not implemented yet")
                    self._set_action_cell(r, btn)
                else:
                    # Normal knob: show Apply or Reset based on current status
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
                        self._apply_queue_button_state(btn, k.id, "reset")
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
                        self._apply_queue_button_state(btn, k.id, "apply")
                    self._apply_busy_state(btn, busy=busy)
                    self._set_action_cell(r, btn)

                # Column 3: Config - clear if no widget was set for this row
                # (PipeWire rows set their own widgets above; other rows need clearing)
                if k.id not in (
                    "pipewire_quantum",
                    "pipewire_sample_rate",
                    "power_profile_performance",
                    "qjackctl_server_prefix_rt",
                    "irq_pinning",
                    "kernel_isolcpus",
                    "kernel_nohz_full",
                    "kernel_rcu_nocbs",
                    "kernel_irqaffinity",
                ):
                    self.table.removeCellWidget(r, 3)
                if row_dim and self.table.item(r, 3) is None:
                    dim_item = QTableWidgetItem("")
                    dim_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    dim_item.setBackground(locked_bg)
                    self.table.setItem(r, 3, dim_item)
                elif not row_dim:
                    item = self.table.item(r, 3)
                    if item is not None and item.text() == "":
                        self.table.takeItem(r, 3)

                # Column 6: Status check
                if k.impl and k.impl.kind == "read_only":
                    check_btn = self._make_action_button("N/A")
                    check_btn.setEnabled(False)
                    check_btn.setToolTip("Not applicable for read-only tests")
                    check_btn.setFocusPolicy(Qt.NoFocus)
                    check_btn.setStyleSheet(locked_style)
                else:
                    check_btn = self._make_action_button("Status")
                    check_btn.setToolTip("Show live CLI status details")
                    check_btn.clicked.connect(lambda _, kid=k.id: self._show_cli_status(kid))
                self._install_hover_tracking(check_btn, r)
                self.table.setCellWidget(r, 6, check_btn)
                if row_dim:
                    config_locked = group_pending_lock or reboot_dep_lock or reboot_gate_lock or advanced_gate_lock
                    for col in range(self.table.columnCount()):
                        widget = self.table.cellWidget(r, col)
                        if widget is None:
                            continue
                        if (
                            k.id == "power_profile_performance"
                            and col == 3
                            and isinstance(widget, QComboBox)
                            and not config_locked
                        ):
                            continue
                        if isinstance(widget, QPushButton):
                            widget.setStyleSheet(locked_style)
                        else:
                            widget.setEnabled(False)
            
            # Keep built-in sorting disabled; we handle per-category sorting.
            self.table.setSortingEnabled(False)
            # Reflow row heights so text/widgets don't clip when font size changes.
            try:
                self.table.resizeRowsToContents()
            except Exception:
                pass

        def _apply_font_size(self, size: int) -> None:
            """Apply font size to the application."""
            font = QApplication.instance().font()
            font.setPointSize(size)
            QApplication.instance().setFont(font)
            # Force-propagate the font to key widgets and table contents.
            # (On some platforms/styles, changing QApplication font doesn't fully repaint existing widgets.)
            try:
                self.setFont(font)
                self.table.setFont(font)
                self.table.horizontalHeader().setFont(font)
                self.font_spinner.setFont(font)
                self.reboot_toggle.setFont(font)
                self.advanced_toggle.setFont(font)
                self.btn_reset.setFont(font)
                for r in range(self.table.rowCount()):
                    for c in range(self.table.columnCount()):
                        it = self.table.item(r, c)
                        if it is not None:
                            it.setFont(font)
                        w = self.table.cellWidget(r, c)
                        if w is not None:
                            w.setFont(font)

                # Reflow rows so widgets/text don't clip at larger font sizes.
                self._apply_default_column_widths()
                self.table.resizeRowsToContents()
                self.table.viewport().update()
                self._apply_window_constraints()
            except Exception:
                pass

        def _apply_default_column_widths(self) -> None:
            try:
                from PySide6.QtGui import QFontMetrics
            except Exception:
                return

            fm = QFontMetrics(self.table.font())

            def _w(text: str, pad: int = 24) -> int:
                return fm.horizontalAdvance(text) + pad

            knob_titles = [k.title for k in self.registry] or ["Knob"]
            knob_width = max([_w("Knob")] + [_w(t) for t in knob_titles])

            status_texts = [
                "Locked",
                "✓ Applied",
                "Sys Default",
                "⚠ Deviated",
                "⟳ Reboot",
                "◐ Partial",
                "N/A",
                "⏳ Updating",
                "—",
            ]
            status_width = max([_w("Status")] + [_w(t) for t in status_texts])

            requirements_texts = [
                "Requirements",
                "A",
                "R",
                "G",
                "A R",
                "A G",
                "R G",
                "A R G",
                "—",
            ]
            requirements_width = max(_w(t) for t in requirements_texts)

            category_texts = [str(k.category) for k in self.registry] + ["Category"]
            category_width = max(_w(t) for t in category_texts)

            risk_texts = [str(k.risk_level) for k in self.registry] + ["Risk"]
            risk_width = max(_w(t) for t in risk_texts)

            sys_texts = [self._sys_label_for_knob(k) for k in self.registry] + ["CLI"]
            sys_width = max(_w(t[:24] + ("..." if len(t) > 24 else "")) for t in sys_texts)

            action_texts = ["Apply", "Reset", "Install", "View", "Test", "Scan", "Join", "Leave", "Action"]
            action_width = max(_w(t, pad=40) for t in action_texts)
            action_width = max(action_width, 80)

            config_texts = ["Config", "Cores", "Devices", "44100 Hz", "192000 Hz", "512", "1024"]
            config_width = max(_w(t, pad=44) for t in config_texts)
            config_width = max(config_width, 128)

            check_texts = ["Check", "Status"]
            check_width = max(_w(t, pad=40) for t in check_texts)
            check_width = max(check_width, 96)

            self._min_column_widths = {
                0: 32,
                2: action_width,
                3: config_width,
                6: check_width,
            }

            self.table.setColumnWidth(0, 32)  # Info button
            self.table.setColumnWidth(1, knob_width)
            self.table.setColumnWidth(2, action_width)
            self.table.setColumnWidth(3, config_width)
            self.table.setColumnWidth(4, requirements_width)
            self.table.setColumnWidth(5, status_width)
            self.table.setColumnWidth(6, check_width)
            self.table.setColumnWidth(7, category_width)
            self.table.setColumnWidth(8, risk_width)
            self.table.setColumnWidth(9, sys_width)
            self._enforce_min_column_widths()

        def _apply_window_constraints(self) -> None:
            """Allow resizing up to the available screen size."""
            try:
                from PySide6.QtGui import QGuiApplication

                screen = QGuiApplication.primaryScreen()
                avail = screen.availableGeometry() if screen else None
                if not avail:
                    return
                self.setMaximumSize(avail.width(), avail.height())
            except Exception:
                return

        def _enforce_min_column_widths(self) -> None:
            header = self.table.horizontalHeader()
            for col, min_w in self._min_column_widths.items():
                if header.sectionSize(col) < min_w:
                    header.resizeSection(col, min_w)

        def _on_section_resized(self, logical: int, _old: int, new: int) -> None:
            min_w = self._min_column_widths.get(int(logical))
            if min_w and new < min_w:
                self.table.horizontalHeader().resizeSection(logical, min_w)

        def _apply_stylesheet(self) -> None:
            """Apply clean dark theme."""
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #1f1f1f;
                    color: #e0e0e0;
                }
                QTableWidget {
                    background-color: #1f1f1f;
                    alternate-background-color: #353535;
                    gridline-color: #1f1f1f;
                    border: 1px solid #1f1f1f;
                }
                QTableWidget::item {
                    background-color: #2f2f2f;
                    padding: 4px;
                    font-weight: normal;
                }
                QTableWidget::item:alternate {
                    background-color: #353535;
                }
                QTableWidget::item:selected {
                    background-color: #46525d;
                    color: #e0e0e0;
                }
                QHeaderView::section {
                    background-color: #1f1f1f;
                    color: #e0e0e0;
                    padding: 6px;
                    font-weight: normal;
                    border: none;
                    border-bottom: 1px solid #2a2a2a;
                }
                QTabBar::tab {
                    background-color: #2b2b2b;
                    color: #cfcfcf;
                    padding: 6px 10px;
                    border: 1px solid #1f1f1f;
                    border-bottom: none;
                }
                QTabBar::tab:selected {
                    background-color: #353535;
                    color: #e0e0e0;
                }
                QTabBar::tab:!selected {
                    margin-top: 2px;
                }
                QPushButton {
                    background-color: #4a4a4a;
                    color: #e0e0e0;
                    border: 1px solid #555555;
                    padding: 5px 10px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #555555;
                }
                QPushButton:pressed {
                    background-color: #333333;
                }
                QPushButton:disabled {
                    background-color: #2f2f2f;
                    color: #7a7a7a;
                    border: 1px solid #3a3a3a;
                }
                QComboBox, QSpinBox {
                    background-color: #404040;
                    color: #e0e0e0;
                    border: 1px solid #555555;
                    padding: 4px;
                    border-radius: 3px;
                }
                QComboBox:disabled, QSpinBox:disabled {
                    background-color: #2f2f2f;
                    color: #7a7a7a;
                    border: 1px solid #3a3a3a;
                }
                QComboBox QAbstractItemView {
                    background-color: #404040;
                    color: #e0e0e0;
                    selection-background-color: #505050;
                }
                QScrollBar:vertical {
                    background-color: #333333;
                    width: 10px;
                }
                QScrollBar::handle:vertical {
                    background-color: #555555;
                    min-height: 20px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """)

        def _on_font_change(self, size: int) -> None:
            """Handle font size change from spinner."""
            self._apply_font_size(size)
            self.state["font_size"] = size
            save_state(self.state)

        def _on_reboot_toggle(self, enabled: bool) -> None:
            """Handle reboot-required knob toggle."""
            self.state["enable_reboot_knobs"] = bool(enabled)
            save_state(self.state)
            v_scroll = None
            try:
                v_scroll = self.table.verticalScrollBar().value()
                self.table.clearSelection()
                self._clear_dim_hover()
            except Exception:
                v_scroll = None
            self._populate()
            if v_scroll is not None:
                try:
                    self.table.verticalScrollBar().setValue(v_scroll)
                except Exception:
                    pass

        def _on_reboot_now(self, *, force: bool = False) -> None:
            if not force and not getattr(self, "_needs_reboot", False):
                return
            if self._reboot_busy:
                return
            msg = (
                "Restart now to apply pending changes?\n\n"
                "Unsaved work in other apps may be lost."
            )
            if QMessageBox.question(self, "Reboot", msg) != QMessageBox.Yes:
                return
            self._reboot_busy = True
            self.reboot_button.setEnabled(False)

            def _task() -> tuple[bool, object, str]:
                try:
                    _run_pkexec_command(["systemctl", "reboot"])
                except Exception as e:
                    return False, {}, str(e)
                return True, {}, ""

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                self._reboot_busy = False
                self.reboot_button.setEnabled(True)
                if not success and message != _PKEXEC_CANCELLED:
                    QMessageBox.warning(self, "Reboot Failed", message or "Reboot failed")

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _on_header_sort(self, column: int) -> None:
            if self._sort_column == column:
                self._sort_descending = not self._sort_descending
            else:
                self._sort_column = column
                self._sort_descending = False
            order = Qt.DescendingOrder if self._sort_descending else Qt.AscendingOrder
            self.table.horizontalHeader().setSortIndicator(column, order)
            self._populate()

        def _on_row_hover(self, row: int, _column: int) -> None:
            if row >= 0:
                self._set_dim_hover_row(row)
                self.table.selectRow(row)

        def eventFilter(self, obj, event):
            if obj is self and event.type() in (QEvent.Leave, QEvent.WindowDeactivate, QEvent.FocusOut):
                self.table.clearSelection()
                self._clear_dim_hover()
                return False
            if obj in (self.table.viewport(), self.table.horizontalHeader(), self.table) and event.type() == QEvent.Leave:
                pos = self.table.mapFromGlobal(QCursor.pos())
                if not self.table.rect().contains(pos):
                    self.table.clearSelection()
                    self._clear_dim_hover()
                return False
            hover_row = obj.property("hover_row")
            if isinstance(hover_row, int):
                if event.type() in (QEvent.Enter, QEvent.MouseMove):
                    self._set_dim_hover_row(hover_row)
                    self.table.selectRow(hover_row)
                elif event.type() == QEvent.Leave:
                    pos = self.table.mapFromGlobal(QCursor.pos())
                    if not self.table.rect().contains(pos):
                        self.table.clearSelection()
                        self._clear_dim_hover()
                return False
            return super().eventFilter(obj, event)

        def _set_dim_hover_row(self, row: int) -> None:
            prev = getattr(self, "_hover_row", None)
            if prev == row:
                return
            if prev is not None:
                self._restore_dim_row(prev)
            self._hover_row = row
            self._clear_dim_row(row)

        def _clear_dim_hover(self) -> None:
            prev = getattr(self, "_hover_row", None)
            if prev is None:
                return
            self._restore_dim_row(prev)
            self._hover_row = None

        def _clear_dim_row(self, row: int) -> None:
            if getattr(self, "_row_dim", None) is None:
                return
            if row >= len(self._row_dim) or not self._row_dim[row]:
                return
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item is not None:
                    item.setBackground(QColor())

        def _restore_dim_row(self, row: int) -> None:
            if getattr(self, "_row_dim", None) is None:
                return
            if row >= len(self._row_dim) or not self._row_dim[row]:
                return
            dim_bg = QColor("#2f2f2f")
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item is not None:
                    item.setBackground(dim_bg)

        def _qjackctl_cpu_cores_from_state(self) -> list[int] | None:
            raw = self.state.get("qjackctl_cpu_cores")
            if raw is None:
                return None
            if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
                return [int(x) for x in raw]
            return None

        def _pipewire_quantum_from_state(self) -> int | None:
            raw = self.state.get("pipewire_quantum")
            if raw is None:
                return None
            try:
                v = int(raw)
            except Exception:
                return None
            if v in (32, 64, 128, 256, 512, 1024):
                return v
            return None

        def _pipewire_sample_rate_from_state(self) -> int | None:
            raw = self.state.get("pipewire_sample_rate")
            if raw is None:
                return None
            try:
                v = int(raw)
            except Exception:
                return None
            if v in (44100, 48000, 88200, 96000, 192000):
                return v
            return None

        def _power_profile_backend_from_state(self) -> str:
            raw = str(self.state.get("power_profile_backend") or "").strip().lower()
            if raw in ("powerprofilesctl", "tuned"):
                return raw
            return "auto"

        def _tuned_conflict_ids(self) -> list[str]:
            return [
                "cpu_governor_performance_persistent",
                "kernel_cstate_limit",
                "kernel_intel_idle_cstate_limit",
            ]

        def _irq_pinning_devices_from_state(self) -> list[str]:
            raw = self.state.get("irq_pinning_devices")
            if not isinstance(raw, list):
                return []
            return [str(x) for x in raw if isinstance(x, (str, int)) and str(x).strip()]

        def _irq_pinning_cpu_cores_from_state(self) -> list[int] | None:
            raw = self.state.get("irq_pinning_cpu_cores")
            if raw is None:
                return None
            if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
                return [int(x) for x in raw]
            return None

        def _kernel_core_key(self, knob_id: str) -> str | None:
            mapping = {
                "kernel_isolcpus": "kernel_isolcpus_cores",
                "kernel_nohz_full": "kernel_nohz_full_cores",
                "kernel_rcu_nocbs": "kernel_rcu_nocbs_cores",
                "kernel_irqaffinity": "kernel_irqaffinity_cores",
            }
            return mapping.get(knob_id)

        def _kernel_cores_from_state(self, knob_id: str) -> list[int] | None:
            key = self._kernel_core_key(knob_id)
            if not key:
                return None
            raw = self.state.get(key)
            if raw is None:
                return None
            if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
                return [int(x) for x in raw]
            return None

        def _kernel_cmdline_param_for_state(self, knob_id: str) -> str | None:
            key = self._kernel_core_key(knob_id)
            if not key:
                return None
            cores = None
            if knob_id == "kernel_irqaffinity" and self.state.get("irq_housekeeping_auto", True):
                try:
                    from audioknob_gui.core.irq import cpu_list_from_cores, read_cpu_present
                except Exception:
                    return None
                audio = set(self._irq_pinning_cpu_cores_from_state() or [])
                housekeeping = read_cpu_present() - audio
                if not housekeeping:
                    return None
                cpu_list = cpu_list_from_cores(sorted(housekeeping))
            else:
                cores = self._kernel_cores_from_state(knob_id)
                if not cores:
                    return None
                try:
                    from audioknob_gui.core.irq import cpu_list_from_cores
                except Exception:
                    return None
                cpu_list = cpu_list_from_cores(cores)
            if not cpu_list:
                return None
            prefixes = {
                "kernel_isolcpus": "isolcpus",
                "kernel_nohz_full": "nohz_full",
                "kernel_rcu_nocbs": "rcu_nocbs",
                "kernel_irqaffinity": "irqaffinity",
            }
            prefix = prefixes.get(knob_id)
            if not prefix:
                return None
            return f"{prefix}={cpu_list}"

        def on_configure_knob(self, knob_id: str) -> None:
            if knob_id == "qjackctl_server_prefix_rt":
                from audioknob_gui.platform.detect import get_cpu_count

                cpu_count = get_cpu_count()
                selected = set(self._qjackctl_cpu_cores_from_state() or [])
                lines = [
                    "Select CPU cores to pin JACK to (taskset -c).",
                    "Tip: cores 0-1 are often busiest (IRQs/system tasks).",
                ]
                smt_line = self._smt_hint_line()
                if smt_line:
                    lines.append(smt_line)
                d = CpuCoreDialog(cpu_count=cpu_count, selected=selected, lines=lines, parent=self)
                if d.exec() != QDialog.Accepted:
                    return

                chosen = d.selected_cores()
                # Empty selection means "no pinning" (remove taskset prefix).
                # None (unset) means "don't override existing pinning".
                self.state["qjackctl_cpu_cores"] = chosen
                save_state(self.state)
                status = self._knob_statuses.get(knob_id)
                if status in ("applied", "pending_reboot"):
                    _get_gui_logger().info("qjackctl cores updated; reapplying")
                    self._on_apply_knob(knob_id)
                    return
                QMessageBox.information(
                    self,
                    "Saved",
                    "Saved CPU core selection for QjackCtl."
                    + (f" Cores: {','.join(map(str, chosen))}" if chosen else " (no pinning)"),
                )
                return

            if knob_id == "irq_pinning":
                from audioknob_gui.core.irq import list_audio_devices
                from audioknob_gui.platform.detect import get_cpu_count

                devices = list_audio_devices()
                if not devices:
                    QMessageBox.warning(
                        self,
                        "No audio devices",
                        "No audio devices were detected. Connect a device and try again.",
                    )
                    return

                cpu_count = get_cpu_count()
                selected_devices = set(self._irq_pinning_devices_from_state())
                selected_cores = set(self._irq_pinning_cpu_cores_from_state() or [])

                d = IrqPinningDialog(
                    cpu_count=cpu_count,
                    selected_cores=selected_cores,
                    devices=devices,
                    selected_devices=selected_devices,
                    parent=self,
                )
                if d.exec() != QDialog.Accepted:
                    return

                chosen_devices = d.selected_device_keys()
                chosen_cores = d.selected_core_list()
                self.state["irq_pinning_devices"] = chosen_devices
                self.state["irq_pinning_cpu_cores"] = chosen_cores
                save_state(self.state)
                self._sync_core_plan_controls()

                status = self._knob_statuses.get(knob_id)
                if status in ("applied", "pending_reboot"):
                    _get_gui_logger().info("irq pinning config updated; reapplying")
                    self._on_apply_knob(knob_id)
                    return
                QMessageBox.information(
                    self,
                    "Saved",
                    "Saved IRQ pinning configuration."
                    + (f" Devices: {len(chosen_devices)}" if chosen_devices else " (no devices)")
                    + (f" Cores: {','.join(map(str, chosen_cores))}" if chosen_cores else " (no cores)"),
                )
                return

            if knob_id in ("kernel_isolcpus", "kernel_nohz_full", "kernel_rcu_nocbs", "kernel_irqaffinity"):
                from audioknob_gui.platform.detect import get_cpu_count

                cpu_count = get_cpu_count()
                allow_auto = knob_id == "kernel_irqaffinity"
                auto_enabled = bool(self.state.get("irq_housekeeping_auto", True))
                selected = set(self._kernel_cores_from_state(knob_id) or [])
                titles = {
                    "kernel_isolcpus": "Configure isolcpus cores",
                    "kernel_nohz_full": "Configure nohz_full cores",
                    "kernel_rcu_nocbs": "Configure rcu_nocbs cores",
                    "kernel_irqaffinity": "Configure irqaffinity cores",
                }
                lines = {
                    "kernel_isolcpus": [
                        "Select CPU cores to isolate from the scheduler.",
                        "These cores should be reserved for audio workloads.",
                    ],
                    "kernel_nohz_full": [
                        "Select CPU cores for full tickless mode.",
                        "Use the same isolated cores for best results.",
                    ],
                    "kernel_rcu_nocbs": [
                        "Select CPU cores to offload RCU callbacks.",
                        "Use the same isolated cores for best results.",
                    ],
                    "kernel_irqaffinity": [
                        "Select housekeeping cores for default IRQ handling.",
                        "Use non-isolated cores to keep IRQs off audio cores.",
                    ],
                }
                dialog_lines = list(lines.get(knob_id) or [])
                smt_line = self._smt_hint_line()
                if smt_line:
                    dialog_lines.append(smt_line)
                auto_hint = None
                auto_label = None
                if allow_auto:
                    audio_cores = set(self._irq_pinning_cpu_cores_from_state() or [])
                    auto_label = "Auto housekeeping (invert audio cores)"
                    auto_hint = "Auto uses IRQ Pinning audio cores to remove them from housekeeping."
                    if audio_cores:
                        audio_list = ",".join(str(c) for c in sorted(audio_cores))
                        auto_hint += f" Audio cores: {audio_list}."
                        housekeeping = sorted(set(range(cpu_count)) - audio_cores)
                        if housekeeping:
                            hk_list = ",".join(str(c) for c in housekeeping)
                            auto_hint += f" Housekeeping: {hk_list}."
                    if auto_enabled:
                        if audio_cores:
                            selected = set(range(cpu_count)) - audio_cores
                        else:
                            selected = set(range(cpu_count))
                d = CpuCoreDialog(
                    cpu_count=cpu_count,
                    selected=selected,
                    allow_auto=allow_auto,
                    auto_enabled=auto_enabled,
                    auto_label=auto_label,
                    auto_hint=auto_hint,
                    title=titles.get(knob_id, "Configure CPU cores"),
                    lines=dialog_lines,
                    parent=self,
                )
                if d.exec() != QDialog.Accepted:
                    return

                chosen = d.selected_cores()
                if allow_auto:
                    self.state["irq_housekeeping_auto"] = d.auto_enabled()
                key = self._kernel_core_key(knob_id)
                if key:
                    self.state[key] = chosen
                    save_state(self.state)
                    self._sync_core_plan_controls()

                status = self._knob_statuses.get(knob_id)
                if status in ("applied", "pending_reboot"):
                    _get_gui_logger().info("%s cores updated; reapplying", knob_id)
                    self._on_apply_knob(knob_id)
                    return
                if allow_auto and self.state.get("irq_housekeeping_auto"):
                    QMessageBox.information(self, "Saved", "Saved IRQ housekeeping configuration (auto).")
                    return
                QMessageBox.information(
                    self,
                    "Saved",
                    "Saved CPU core selection."
                    + (f" Cores: {','.join(map(str, chosen))}" if chosen else " (no cores)"),
                )
                return

            if knob_id == "pipewire_quantum":
                from PySide6.QtWidgets import QComboBox

                class PipeWireQuantumDialog(QDialog):
                    def __init__(self, current: int | None, parent: QWidget | None = None) -> None:
                        super().__init__(parent)
                        self.setWindowTitle("Configure PipeWire buffer (quantum)")
                        self.resize(420, 160)

                        root = QVBoxLayout(self)
                        root.addWidget(QLabel("Select PipeWire buffer size (quantum)."))
                        root.addWidget(QLabel("Recommended: 128 or 256. Smaller can underrun; larger adds latency."))

                        self.combo = QComboBox()
                        self._values = [32, 64, 128, 256, 512, 1024]
                        for v in self._values:
                            self.combo.addItem(str(v), v)
                        if current in self._values:
                            self.combo.setCurrentIndex(self._values.index(current))
                        root.addWidget(self.combo)

                        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
                        btns.accepted.connect(self.accept)
                        btns.rejected.connect(self.reject)
                        root.addWidget(btns)

                    def selected_value(self) -> int:
                        return int(self.combo.currentData())

                current = self._pipewire_quantum_from_state() or 256
                d = PipeWireQuantumDialog(current=current, parent=self)
                if d.exec() != QDialog.Accepted:
                    return
                chosen = d.selected_value()
                self.state["pipewire_quantum"] = chosen
                save_state(self.state)
                QMessageBox.information(self, "Saved", f"Saved PipeWire quantum = {chosen}. Apply the PipeWire knob to take effect.")
                return

            if knob_id == "pipewire_sample_rate":
                from PySide6.QtWidgets import QComboBox

                class PipeWireSampleRateDialog(QDialog):
                    def __init__(self, current: int | None, parent: QWidget | None = None) -> None:
                        super().__init__(parent)
                        self.setWindowTitle("Configure PipeWire sample rate")
                        self.resize(420, 160)

                        root = QVBoxLayout(self)
                        root.addWidget(QLabel("Select PipeWire default sample rate."))
                        root.addWidget(QLabel("Common: 48000 Hz. Higher rates for high-res audio."))

                        self.combo = QComboBox()
                        self._values = [44100, 48000, 88200, 96000, 192000]
                        for v in self._values:
                            self.combo.addItem(f"{v} Hz", v)
                        if current in self._values:
                            self.combo.setCurrentIndex(self._values.index(current))
                        root.addWidget(self.combo)

                        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
                        btns.accepted.connect(self.accept)
                        btns.rejected.connect(self.reject)
                        root.addWidget(btns)

                    def selected_value(self) -> int:
                        return int(self.combo.currentData())

                current = self._pipewire_sample_rate_from_state() or 48000
                d = PipeWireSampleRateDialog(current=current, parent=self)
                if d.exec() != QDialog.Accepted:
                    return
                chosen = d.selected_value()
                self.state["pipewire_sample_rate"] = chosen
                save_state(self.state)
                QMessageBox.information(self, "Saved", f"Saved PipeWire sample rate = {chosen} Hz. Apply the PipeWire knob to take effect.")
                return

            return

        def on_tests(self) -> None:
            headline, detail, payload = jitter_test_summary(duration_s=5, use_pkexec=True)
            self.state["jitter_test_last"] = payload
            save_state(self.state)
            QMessageBox.information(self, headline, detail)

        def on_run_test(self, knob_id: str) -> None:
            """Run a test and update the status column with results."""
            if knob_id == "scheduler_jitter_test":
                if knob_id in self._busy_knobs:
                    return
                self._busy_knobs.add(knob_id)
                # Show a brief "running" indicator
                self._update_knob_status(knob_id, "running", "⏳ Running...")
                self._populate()

                def _task() -> tuple[bool, object, str]:
                    headline, detail, payload = jitter_test_summary(duration_s=5, use_pkexec=False)
                    return True, {"headline": headline, "detail": detail, "payload": payload}, ""

                worker = QueueTaskWorker(_task, parent=self)

                def _on_done(success: bool, payload: object, message: str) -> None:
                    self._busy_knobs.discard(knob_id)
                    if not success or not isinstance(payload, dict):
                        self._knob_statuses[knob_id] = "error"
                        self._populate()
                        QMessageBox.warning(self, "Jitter Test Failed", message or "Jitter test failed")
                        return

                    detail = str(payload.get("detail", ""))
                    result = payload.get("payload")
                    if isinstance(result, dict):
                        self.state["jitter_test_last"] = result
                        save_state(self.state)
                        max_us = result.get("max_us")
                        if isinstance(max_us, int):
                            self._knob_statuses[knob_id] = f"result:{max_us} µs"
                        else:
                            self._knob_statuses[knob_id] = "error"
                            QMessageBox.warning(self, "Jitter Test Failed", detail or "No results")
                    else:
                        self._knob_statuses[knob_id] = "error"
                        QMessageBox.warning(self, "Jitter Test Failed", detail or "No results")

                    self._populate()

                worker.finished.connect(_on_done)
                worker.finished.connect(worker.deleteLater)
                self._task_threads.append(worker)
                worker.start()

        def _update_knob_status(self, knob_id: str, status: str, display: str) -> None:
            """Update the status cell for a specific knob."""
            # Keep backing store in sync so subsequent _populate() reflects the new state.
            self._knob_statuses[knob_id] = status
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 1)
                if item is None:
                    continue
                if item.data(Qt.UserRole) == knob_id:
                    status_item = QTableWidgetItem(display)
                    status_item.setForeground(QColor("#1976d2"))
                    # Status column is col 5 (col 1 is knob title).
                    self.table.setItem(r, 5, status_item)
                    break

        def on_view_stack(self) -> None:
            """Show detected audio stack information."""
            try:
                from audioknob_gui.platform.detect import detect_stack, list_alsa_playback_devices
                
                stack = detect_stack()
                devices = list_alsa_playback_devices()
                
                html_lines = [
                    "<h3>Audio Stack Detection</h3>",
                    "<table style='width:100%'>",
                    f"<tr><td><b>PipeWire:</b></td><td>{'✓ Active' if stack.pipewire_active else '○ Not active'}</td></tr>",
                    f"<tr><td><b>WirePlumber:</b></td><td>{'✓ Active' if stack.wireplumber_active else '○ Not active'}</td></tr>",
                    f"<tr><td><b>JACK:</b></td><td>{'✓ Active' if stack.jack_active else '○ Not active'}</td></tr>",
                    "</table>",
                    "<hr/>",
                    f"<h4>ALSA Playback Devices ({len(devices)})</h4>",
                    "<table style='width:100%'>",
                ]
                
                # Show ALL devices - no truncation
                for dev in devices:
                    name = dev.get("name", "")
                    desc = dev.get("desc", dev.get("raw", "Unknown"))
                    html_lines.append(f"<tr><td><b>{name}</b></td><td>{desc}</td></tr>")
                
                html_lines.append("</table>")
                
                if not devices:
                    html_lines.append("<p style='color:#666'>No ALSA devices found.</p>")
                
                html = "".join(html_lines)
                
                # Show in resizable dialog
                dialog = QDialog(self)
                dialog.setWindowTitle("Audio Stack Detection")
                dialog.resize(600, 450)
                layout = QVBoxLayout(dialog)
                
                text = QTextEdit()
                text.setReadOnly(True)
                text.setHtml(html)
                layout.addWidget(text)
                
                # Button row
                btn_layout = QHBoxLayout()
                
                def copy_to_clipboard():
                    # Plain text version for clipboard
                    plain = []
                    plain.append("Audio Stack Detection")
                    plain.append(f"PipeWire: {'Active' if stack.pipewire_active else 'Not active'}")
                    plain.append(f"WirePlumber: {'Active' if stack.wireplumber_active else 'Not active'}")
                    plain.append(f"JACK: {'Active' if stack.jack_active else 'Not active'}")
                    plain.append("")
                    plain.append(f"ALSA Playback Devices ({len(devices)}):")
                    for dev in devices:
                        plain.append(f"  {dev.get('name', '')} - {dev.get('desc', dev.get('raw', ''))}")
                    QApplication.clipboard().setText("\n".join(plain))
                
                copy_btn = QPushButton("Copy to Clipboard")
                copy_btn.clicked.connect(copy_to_clipboard)
                btn_layout.addWidget(copy_btn)
                btn_layout.addStretch()
                
                close_btn = QPushButton("Close")
                close_btn.clicked.connect(dialog.reject)
                btn_layout.addWidget(close_btn)
                layout.addLayout(btn_layout)
                
                dialog.exec()
                
            except Exception as e:
                QMessageBox.critical(self, "Detection Failed", f"Could not detect audio stack: {e}")

        def _show_knob_info(self, knob_id: str) -> None:
            """Show detailed information about a knob."""
            k = next((k for k in self.registry if k.id == knob_id), None)
            if not k:
                return

            def _kernel_cmdline_tokens() -> list[str]:
                try:
                    raw = Path("/proc/cmdline").read_text(encoding="utf-8").strip()
                except Exception:
                    return []
                return [t for t in raw.split() if t]

            def _param_present(tokens: list[str], param: str) -> bool:
                if "=" in param:
                    return param in tokens
                for token in tokens:
                    if token == param or token.startswith(param + "="):
                        return True
                return False

            def _kernel_is_rt() -> bool:
                try:
                    rel = os.uname().release.lower()
                except Exception:
                    return False
                return bool(re.search(r"(?:^|[-_])rt\\d|(?:^|[-_])rt$|realtime", rel))
            
            def _read_interrupts_map() -> dict[int, str]:
                try:
                    raw = Path("/proc/interrupts").read_text(encoding="utf-8")
                except Exception:
                    return {}
                lines: dict[int, str] = {}
                for line in raw.splitlines():
                    stripped = line.strip()
                    if not stripped or not stripped[:1].isdigit():
                        continue
                    if ":" not in stripped:
                        continue
                    irq_str, rest = stripped.split(":", 1)
                    irq_str = irq_str.strip()
                    if not irq_str.isdigit():
                        continue
                    try:
                        irq = int(irq_str)
                    except Exception:
                        continue
                    lines[irq] = rest.strip()
                return lines

            def _shell_single_quote(value: str) -> str:
                return "'" + value.replace("'", "'\"'\"'") + "'"

            def _fmt_jitter_value(value: object) -> str:
                if isinstance(value, float):
                    return f"{value:.1f}"
                if isinstance(value, int):
                    return str(value)
                return "—"
            
            # Build detailed info
            status = self._knob_statuses.get(k.id, "unknown")
            status_text, _ = self._status_display(status)
            
            impl_info = "Not implemented yet"
            if k.impl:
                impl_info = f"<b>Kind:</b> {k.impl.kind}<br/>"
                # For configurable knobs, show current configured values rather than registry defaults.
                params = dict(k.impl.params)
                if k.id == "pipewire_quantum":
                    q = self._pipewire_quantum_from_state()
                    if q is not None:
                        params["quantum"] = q
                if k.id == "pipewire_sample_rate":
                    r = self._pipewire_sample_rate_from_state()
                    if r is not None:
                        params["rate"] = r
                if k.id == "irq_pinning":
                    devices = self._irq_pinning_devices_from_state()
                    cores = self._irq_pinning_cpu_cores_from_state()
                    if devices:
                        params["device_keys"] = devices
                    if cores is not None:
                        params["cpu_cores"] = ",".join(str(c) for c in cores)
                if k.id == "power_profile_performance":
                    params["backend"] = self._power_profile_backend_from_state()
                if k.id in ("kernel_isolcpus", "kernel_nohz_full", "kernel_rcu_nocbs", "kernel_irqaffinity"):
                    override = self._kernel_cmdline_param_for_state(k.id)
                    if override:
                        params["param"] = override

                for key, val in params.items():
                    if isinstance(val, list):
                        impl_info += f"<b>{key}:</b><br/>"
                        for item in val:
                            impl_info += f"  • {item}<br/>"
                    else:
                        impl_info += f"<b>{key}:</b> {val}<br/>"

            registry_path = _registry_path()
            reg_q = _shell_single_quote(registry_path)
            status_py = (
                "import json,subprocess; "
                f"data=json.loads(subprocess.check_output([\"python3\",\"-m\",\"audioknob_gui.worker.cli\",\"--registry\",\"{registry_path}\",\"status\"])); "
                f"print([s for s in data.get(\"statuses\",[]) if s.get(\"knob_id\")==\"{k.id}\"][0])"
            )
            status_cmd = f"python3 -c {_shell_single_quote(status_py)}"
            if k.capabilities.apply:
                if k.requires_root:
                    apply_cmd = f"pkexec /usr/libexec/audioknob-gui-worker --registry {reg_q} apply {k.id}"
                    reset_cmd = f"pkexec /usr/libexec/audioknob-gui-worker --registry {reg_q} restore-knob {k.id}"
                else:
                    apply_cmd = f"python3 -m audioknob_gui.worker.cli --registry {reg_q} apply-user {k.id}"
                    reset_cmd = f"python3 -m audioknob_gui.worker.cli --registry {reg_q} restore-knob {k.id}"
            else:
                apply_cmd = "N/A (read-only)"
                reset_cmd = "N/A (read-only)"

            cli_html = (
                "<hr/>"
                "<p><b>CLI sanity checks:</b></p>"
                f"<pre>{html_lib.escape(status_cmd)}\n"
                f"{html_lib.escape(apply_cmd)}\n"
                f"{html_lib.escape(reset_cmd)}</pre>"
            )
            
            extra_html = ""
            if k.id == "scheduler_jitter_test":
                last = self.state.get("jitter_test_last")
                if isinstance(last, dict):
                    max_us = last.get("max_us")
                    returncode = last.get("returncode")
                    note = last.get("note")
                    threads = last.get("threads")
                    thread_samples = last.get("thread_samples")
                    extra_html += "<hr/><p><b>Last jitter test:</b></p>"
                    if isinstance(max_us, int):
                        extra_html += f"<p>Max: {max_us} µs</p>"
                    else:
                        extra_html += "<p>Result: unavailable</p>"
                    if isinstance(threads, list) and threads:
                        extra_html += "<table>"
                        extra_html += (
                            "<tr>"
                            "<td><b>Thread</b></td>"
                            "<td><b>Samples</b></td>"
                            "<td><b>Min</b></td>"
                            "<td><b>Median</b></td>"
                            "<td><b>Avg</b></td>"
                            "<td><b>P95</b></td>"
                            "<td><b>Max</b></td>"
                            "</tr>"
                        )
                        for item in sorted(threads, key=lambda t: t.get("thread", 0)):
                            t = item.get("thread")
                            if not isinstance(t, int):
                                continue
                            extra_html += (
                                "<tr>"
                                f"<td>{t}</td>"
                                f"<td>{_fmt_jitter_value(item.get('samples'))}</td>"
                                f"<td>{_fmt_jitter_value(item.get('min_us'))}</td>"
                                f"<td>{_fmt_jitter_value(item.get('median_us'))}</td>"
                                f"<td>{_fmt_jitter_value(item.get('avg_us'))}</td>"
                                f"<td>{_fmt_jitter_value(item.get('p95_us'))}</td>"
                                f"<td>{_fmt_jitter_value(item.get('max_us'))}</td>"
                                "</tr>"
                            )
                        extra_html += "</table>"
                        if isinstance(thread_samples, list) and thread_samples:
                            extra_html += "<p>Tip: use \"Show Sample List\" to view raw values.</p>"
                    else:
                        extra_html += "<p>No per-thread results captured yet.</p>"
                    if note:
                        extra_html += f"<p><b>Note:</b> {html_lib.escape(str(note))}</p>"
                    if returncode is not None:
                        extra_html += f"<p><b>Return code:</b> {returncode}</p>"
                else:
                    extra_html += "<hr/><p><b>Last jitter test:</b> not run yet.</p>"
            if k.id == "qjackctl_server_prefix_rt" and self._is_process_running(["qjackctl", "qjackctl6"]):
                extra_html += (
                    "<hr/><p><b>Note:</b> Quit QjackCtl before applying this knob. "
                    "QjackCtl rewrites its config on exit.</p>"
                )
            if k.id in (
                "qjackctl_server_prefix_rt",
                "irq_pinning",
                "kernel_isolcpus",
                "kernel_nohz_full",
                "kernel_rcu_nocbs",
                "kernel_irqaffinity",
                "kernel_threadirqs",
                "rtirq_enable",
            ):
                try:
                    from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups

                    groups = read_thread_sibling_groups()
                    logical = len(read_cpu_present() or [])
                    physical = len(groups)
                    smt = any(len(g) > 1 for g in groups)
                    group_chunks: list[str] = []
                    for group in groups[:8]:
                        group_chunks.append("(" + ",".join(str(c) for c in group) + ")")
                    if len(groups) > 8:
                        group_chunks.append(f"(+{len(groups) - 8} more)")
                    layout_line = ""
                    if group_chunks:
                        layout_line = "Sibling groups: " + " ".join(group_chunks)
                    extra_html += "<hr/><p><b>CPU core layout:</b></p>"
                    if smt and logical:
                        extra_html += (
                            f"<p>SMT detected: {physical} physical / {logical} logical cores.</p>"
                            "<p>For best isolation, select both siblings from a physical core.</p>"
                        )
                    else:
                        extra_html += "<p>SMT/Hyper-Threading not detected.</p>"
                    if layout_line:
                        extra_html += f"<p>{layout_line}</p>"
                    if k.id == "kernel_threadirqs":
                        extra_html += (
                            "<p>Note: threadirqs makes IRQ handlers schedulable threads "
                            "but does not change CPU topology.</p>"
                        )
                        extra_html += (
                            "<p>Pairing tip: Enable RTIRQ to raise IRQ thread priorities once IRQs are threaded.</p>"
                        )
                    if k.id == "rtirq_enable":
                        tokens = _kernel_cmdline_tokens()
                        threaded = _param_present(tokens, "threadirqs")
                        rt_kernel = _kernel_is_rt()
                        if threaded or rt_kernel:
                            extra_html += (
                                "<p>Threaded IRQs detected; RTIRQ can raise IRQ thread priorities.</p>"
                            )
                        else:
                            extra_html += (
                                "<p><b>Warning:</b> RTIRQ only affects threaded IRQs. "
                                "Enable Threaded IRQs or use an RT kernel for RTIRQ to take effect.</p>"
                            )
                except Exception:
                    pass
            if k.id == "irq_pinning":
                try:
                    active = subprocess.run(
                        ["systemctl", "is-active", "irqbalance.service"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    ).stdout.strip()
                    if active == "active":
                        extra_html += (
                            "<hr/><p><b>Warning:</b> irqbalance is active and can override IRQ pinning.</p>"
                        )
                    device_keys = self._irq_pinning_devices_from_state()
                    if device_keys:
                        try:
                            from audioknob_gui.core.irq import collect_target_irqs, resolve_selected_devices

                            selected, _missing = resolve_selected_devices(device_keys)
                            target_irqs = collect_target_irqs(selected)
                        except Exception:
                            target_irqs = []
                        if target_irqs:
                            irq_lines = _read_interrupts_map()
                            extra_html += "<hr/><p><b>IRQ lines (from /proc/interrupts):</b></p><pre>"
                            for irq in sorted(set(target_irqs)):
                                line = irq_lines.get(irq, "")
                                if line:
                                    shared = " (shared?)" if "," in line else ""
                                    extra_html += f"IRQ {irq}: {html_lib.escape(line)}{shared}\n"
                                else:
                                    extra_html += f"IRQ {irq}: not found\n"
                            extra_html += "</pre>"
                            extra_html += (
                                "<p>If a line lists multiple devices (comma-separated), the IRQ is shared.</p>"
                            )
                except Exception:
                    pass
            if k.id == "rt_limits_audio_group":
                try:
                    import resource

                    rt_soft, rt_hard = resource.getrlimit(resource.RLIMIT_RTPRIO)
                    mem_soft, mem_hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)

                    def _limit_str(value: int) -> str:
                        if value == resource.RLIM_INFINITY:
                            return "unlimited"
                        return str(value)

                    extra_html += "<hr/><p><b>Session limits (ulimit):</b></p>"
                    extra_html += (
                        f"<p>rtprio: {_limit_str(rt_soft)} (soft), {_limit_str(rt_hard)} (hard)<br/>"
                        f"memlock: {_limit_str(mem_soft)} (soft), {_limit_str(mem_hard)} (hard)</p>"
                    )
                    extra_html += "<p>Note: limits apply after log out/in or reboot.</p>"
                except Exception:
                    pass
            if k.id == "kernel_rt_throttling_off":
                try:
                    value = Path("/proc/sys/kernel/sched_rt_runtime_us").read_text(encoding="utf-8").strip()
                    extra_html += (
                        "<hr/><p><b>Current sched_rt_runtime_us:</b> "
                        f"{html_lib.escape(value)}</p>"
                    )
                    extra_html += (
                        "<p><b>Warning:</b> disabling RT throttling can let runaway RT tasks "
                        "starve the system and may block suspend. Reset before sleep if needed.</p>"
                    )
                except Exception:
                    pass
            if k.id in ("kernel_cstate_limit", "kernel_intel_idle_cstate_limit"):
                driver = None
                try:
                    driver = Path("/sys/devices/system/cpu/cpu0/cpuidle/current_driver").read_text(encoding="utf-8").strip()
                except Exception:
                    driver = None
                extra_html += "<hr/><p><b>CPU idle driver:</b> "
                extra_html += html_lib.escape(driver) if driver else "unknown"
                extra_html += "</p>"
                if k.id == "kernel_cstate_limit" and driver == "intel_idle":
                    extra_html += (
                        "<p><b>Note:</b> intel_idle is active. The Intel C-States knob may be more effective.</p>"
                    )
                if k.id == "kernel_intel_idle_cstate_limit" and driver and driver != "intel_idle":
                    extra_html += (
                        "<p><b>Note:</b> intel_idle is not active on this system.</p>"
                    )
                extra_html += (
                    "<p>Limiting C-states can increase power draw and heat. Reset if needed.</p>"
                )
                extra_html += (
                    "<p><b>Warning:</b> limiting C-states can keep fans running and may affect suspend behavior.</p>"
                )
            if k.id == "power_profile_performance":
                try:
                    from audioknob_gui.worker.ops import read_power_profile, select_power_profile_backend

                    pref = self._power_profile_backend_from_state()
                    params = dict(k.impl.params) if k.impl else {}
                    params["backend"] = pref
                    backend = select_power_profile_backend(params)
                    pref_label = pref if pref != "auto" else "auto (active backend)"
                    extra_html += "<hr/><p><b>Backend preference:</b> "
                    extra_html += html_lib.escape(pref_label)
                    extra_html += "</p>"
                    if backend:
                        current = read_power_profile(backend["backend"], backend["cmd"])
                        if backend["backend"] == "powerprofilesctl":
                            expected = str(params.get("ppd_profile", "performance")).strip() or "performance"
                        else:
                            expected = str(params.get("tuned_profile", "latency-performance")).strip() or "latency-performance"
                        extra_html += "<p><b>Resolved backend:</b> "
                        extra_html += html_lib.escape(backend["backend"])
                        extra_html += "</p>"
                        if current:
                            extra_html += (
                                f"<p>Current: {html_lib.escape(current)}"
                                f" (target: {html_lib.escape(expected)})</p>"
                            )
                        if backend["backend"] == "tuned":
                            conflict_ids = self._tuned_conflict_ids()
                            by_id = {kn.id: kn for kn in self.registry}
                            conflict_titles = []
                            for cid in conflict_ids:
                                title = by_id.get(cid).title if cid in by_id else cid
                                state = self._knob_statuses.get(cid)
                                if state in ("applied", "pending_reboot"):
                                    conflict_titles.append(f"{title} ({state})")
                                else:
                                    conflict_titles.append(title)
                            if conflict_titles:
                                extra_html += (
                                    "<p><b>Potential conflicts:</b> "
                                    + html_lib.escape(", ".join(conflict_titles))
                                    + "</p>"
                                )
                            extra_html += (
                                "<p><b>Note:</b> tuned manages system power/governor settings. "
                                "Avoid stacking overlapping knobs unless you know their combined effect.</p>"
                            )
                    else:
                        extra_html += (
                            "<p><b>Resolved backend:</b> none detected "
                            "(powerprofilesctl or tuned-adm required).</p>"
                        )
                except Exception:
                    pass
            if k.id == "qjackctl_server_prefix_rt":
                extra_html += (
                    "<hr/><p><b>Buffer math:</b> total buffer = frames/period × periods/buffer. "
                    "Lower values reduce latency but increase xrun risk. "
                    "Periods/buffer = 2 is typical; 3 is safer; 1 is often unstable.</p>"
                )

            def _requirements_info_line() -> str | None:
                parts: list[str] = []
                if k.requires_root:
                    parts.append("root access")
                if k.requires_reboot:
                    parts.append("reboot")
                if k.requires_groups:
                    parts.append(f"group membership: {', '.join(k.requires_groups)}")
                if k.requires_commands:
                    parts.append(f"commands: {', '.join(k.requires_commands)}")
                if k.id in self._advanced_knob_ids():
                    parts.append("advanced mode")
                if not parts:
                    return None
                return "requires " + "; ".join(parts)

            def _format_description(desc: str) -> str:
                lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]
                tagged = any(ln.startswith("[") and len(ln) > 2 and ln[2] == "]" for ln in lines)
                if not tagged:
                    return f"<p>{html_lib.escape(desc)}</p>"
                groups: dict[str, list[str]] = {"i": [], "r": [], "+": [], "-": [], "?": []}
                for line in lines:
                    tag = None
                    text = line
                    if line.startswith("[") and len(line) > 2 and line[2] == "]":
                        tag = line[1].lower()
                        text = line[3:].strip()
                    if tag in ("i", "r", "+", "-"):
                        groups[tag].append(text)
                    else:
                        groups["?"].append(text)
                req_line = _requirements_info_line()
                if req_line:
                    groups["r"].insert(0, req_line)
                parts_html: list[str] = []
                for line in groups["i"]:
                    parts_html.append(f"<p><b>[i]</b> {html_lib.escape(line)}</p>")
                for line in groups["r"]:
                    parts_html.append(f"<p><b>[r]</b> {html_lib.escape(line)}</p>")
                for line in groups["+"]:
                    parts_html.append(f"<p><b>[+]</b> {html_lib.escape(line)}</p>")
                for line in groups["-"]:
                    parts_html.append(f"<p><b>[-]</b> {html_lib.escape(line)}</p>")
                for line in groups["?"]:
                    parts_html.append(f"<p>{html_lib.escape(line)}</p>")
                return "\n".join(parts_html)

            description_html = _format_description(k.description)

            html = f"""
            <h3>{k.title}</h3>
            {description_html}
            <hr/>
            <table>
            <tr><td><b>ID:</b></td><td>{k.id}</td></tr>
            <tr><td><b>Status:</b></td><td>{status_text}</td></tr>
            <tr><td><b>Category:</b></td><td>{k.category}</td></tr>
            <tr><td><b>Risk:</b></td><td>{k.risk_level}</td></tr>
            <tr><td><b>Requires root:</b></td><td>{'Yes' if k.requires_root else 'No'}</td></tr>
            <tr><td><b>Requires reboot:</b></td><td>{'Yes' if k.requires_reboot else 'No'}</td></tr>
            </table>
            <hr/>
            <p><b>Implementation:</b></p>
            <p>{impl_info}</p>
            {extra_html}
            {cli_html}
            """
            
            dialog = QDialog(self)
            dialog.setWindowTitle(k.title)
            dialog.resize(500, 400)
            layout = QVBoxLayout(dialog)

            text = QTextEdit()
            text.setReadOnly(True)
            text.setHtml(html)
            layout.addWidget(text)

            # Add config button for knobs that support it
            if k.id == "qjackctl_server_prefix_rt":
                config_btn = QPushButton("Configure CPU Cores...")
                config_btn.clicked.connect(lambda: (dialog.accept(), self.on_configure_knob(k.id)))
                layout.addWidget(config_btn)
            if k.id == "pipewire_quantum":
                config_btn = QPushButton("Configure Buffer Size...")
                config_btn.clicked.connect(lambda: (dialog.accept(), self.on_configure_knob(k.id)))
                layout.addWidget(config_btn)
            if k.id == "pipewire_sample_rate":
                config_btn = QPushButton("Configure Sample Rate...")
                config_btn.clicked.connect(lambda: (dialog.accept(), self.on_configure_knob(k.id)))
                layout.addWidget(config_btn)
            if k.id == "irq_pinning":
                config_btn = QPushButton("Configure IRQ Pinning...")
                config_btn.clicked.connect(lambda: (dialog.accept(), self.on_configure_knob(k.id)))
                layout.addWidget(config_btn)
            if k.id in ("kernel_isolcpus", "kernel_nohz_full", "kernel_rcu_nocbs", "kernel_irqaffinity"):
                config_btn = QPushButton("Configure CPU Cores...")
                config_btn.clicked.connect(lambda: (dialog.accept(), self.on_configure_knob(k.id)))
                layout.addWidget(config_btn)
            if k.id == "scheduler_jitter_test":
                last = self.state.get("jitter_test_last")
                samples = last.get("thread_samples") if isinstance(last, dict) else None
                if isinstance(samples, list) and samples:
                    samples_btn = QPushButton("Show Sample List...")
                    samples_btn.clicked.connect(lambda: self._show_jitter_samples(samples))
                    layout.addWidget(samples_btn)

            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.rejected.connect(dialog.reject)
            layout.addWidget(btns)

            dialog.exec()

        def _show_jitter_samples(self, samples: list[dict]) -> None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Jitter Test Samples")
            dialog.resize(640, 420)
            layout = QVBoxLayout(dialog)

            text = QTextEdit()
            text.setReadOnly(True)
            lines: list[str] = []
            for item in sorted(samples, key=lambda t: t.get("thread", 0)):
                thread_id = item.get("thread")
                values = item.get("samples")
                if not isinstance(thread_id, int) or not isinstance(values, list):
                    continue
                lines.append(f"Thread {thread_id} ({len(values)} samples):")
                lines.append("  " + ", ".join(str(v) for v in values))
                lines.append("")
            if not lines:
                lines.append("No samples captured.")
            text.setPlainText("\n".join(lines))
            layout.addWidget(text)

            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.rejected.connect(dialog.reject)
            layout.addWidget(btns)

            dialog.exec()

        def _collect_live_checks(self, knob, *, status_override: str | None = None) -> list[str]:
            def _read_file(path: str, *, max_lines: int = 40) -> list[str]:
                p = Path(path).expanduser()
                if not p.exists():
                    return [f"{path}: missing"]
                try:
                    content = p.read_text(encoding="utf-8").splitlines()
                except Exception as e:
                    return [f"{path}: unreadable: {e}"]
                if len(content) > max_lines:
                    content = content[:max_lines] + ["... (truncated)"]
                return [f"{path}:"] + content

            def _param_present(tokens: list[str], param: str) -> bool:
                if "=" in param:
                    return param in tokens
                for token in tokens:
                    if token == param or token.startswith(param + "="):
                        return True
                return False

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

            def _read_proc_cmdline(pid: int) -> str:
                try:
                    raw = Path(f"/proc/{pid}/cmdline").read_bytes()
                except Exception:
                    return ""
                return " ".join(x for x in raw.decode("utf-8", errors="replace").split("\0") if x)

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

            def _read_jackd_rt_summary(pids: list[int]) -> tuple[int, int, list[int]]:
                total_threads = 0
                rt_threads = 0
                rt_priorities: list[int] = []
                for pid in pids:
                    task_dir = Path(f"/proc/{pid}/task")
                    try:
                        entries = list(task_dir.iterdir())
                    except Exception:
                        continue
                    for entry in entries:
                        if not entry.name.isdigit():
                            continue
                        total_threads += 1
                        tid = int(entry.name)
                        try:
                            policy = os.sched_getscheduler(tid)
                        except Exception:
                            continue
                        if policy in (os.SCHED_FIFO, os.SCHED_RR):
                            rt_threads += 1
                            try:
                                prio = os.sched_getparam(tid).sched_priority
                            except Exception:
                                prio = None
                            if prio is not None:
                                rt_priorities.append(prio)
                return total_threads, rt_threads, sorted(set(rt_priorities))

            lines: list[str] = []
            lines.append(f"knob_id: {knob.id}")
            lines.append(f"title: {knob.title}")
            status = status_override or self._knob_statuses.get(knob.id, "unknown")
            lines.append(f"status: {status}")
            lines.append("")

            kind = knob.impl.kind if knob.impl else ""
            params = dict(knob.impl.params) if knob.impl else {}
            lines.append(f"kind: {kind}")
            if knob.id == "power_profile_performance":
                params["backend"] = self._power_profile_backend_from_state()

            if kind == "qjackctl_server_prefix":
                path = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
                lines.append("")
                lines.append("qjackctl_config:")
                cfg = None
                try:
                    from audioknob_gui.core.qjackctl import read_config, resolve_server_config_path

                    cfg = read_config(Path(path).expanduser())
                except Exception:
                    cfg = None
                if cfg is not None:
                    active_preset = cfg.def_preset if cfg.def_preset else "(default)"
                    lines.append(f"active_preset: {active_preset}")
                    cmd = cfg.server_cmd or ""
                    tokens = cmd.split()
                    ensure_rt = bool(params.get("ensure_rt", True))
                    ensure_prio = bool(params.get("ensure_priority", False))
                    expected_prio = 90 if ensure_prio else None
                    rt_cfg_ok = True
                    prio_cfg_ok = True
                    if ensure_rt:
                        rt_cfg_ok = cfg.realtime is True or any(
                            t in ("-R", "--realtime") or t.startswith("--realtime") for t in tokens
                        )
                    if ensure_prio:
                        prio_cfg_ok = (cfg.priority == expected_prio) or any(
                            t.startswith("-P") for t in tokens
                        )
                    expected_cores = self._qjackctl_cpu_cores_from_state()
                    if expected_cores is None:
                        cpu_cores = params.get("cpu_cores")
                        if cpu_cores is not None:
                            try:
                                from audioknob_gui.core.irq import parse_cpu_list

                                expected_cores = sorted(parse_cpu_list(str(cpu_cores)))
                            except Exception:
                                expected_cores = None
                    config_pin_ok = True
                    runtime_pin_ok = None
                    if expected_cores is not None:
                        expected_list = ",".join(str(c) for c in expected_cores)
                        if expected_list:
                            try:
                                from audioknob_gui.core.qjackctl import (
                                    build_post_start_script,
                                    default_post_start_script_path,
                                )

                                expected_script = build_post_start_script(expected_list)
                                expected_path = str(default_post_start_script_path())
                                config_pin_ok = (
                                    cfg.post_startup_enabled
                                    and cfg.post_startup_shell == expected_path
                                )
                                if config_pin_ok:
                                    try:
                                        script_text = Path(expected_path).read_text(encoding="utf-8")
                                        config_pin_ok = script_text == expected_script
                                    except Exception:
                                        config_pin_ok = False
                            except Exception:
                                config_pin_ok = False
                            try:
                                from audioknob_gui.core.irq import parse_cpu_list

                                expected_set = set(expected_cores)
                                runtime_pin_ok = True
                                for pid in _find_pids_by_comm("jackd"):
                                    allowed = _read_proc_cpu_allowed_list(pid)
                                    if not allowed:
                                        continue
                                    if parse_cpu_list(allowed) != expected_set:
                                        runtime_pin_ok = False
                                        break
                            except Exception:
                                runtime_pin_ok = None
                        else:
                            config_pin_ok = not cfg.post_startup_enabled and not cfg.post_startup_shell

                    if status == "partial":
                        if cfg.server_config_enabled:
                            lines.append("partial_reason: ServerConfig enabled; QjackCtl may override GUI settings.")
                        if ensure_rt and not rt_cfg_ok:
                            lines.append("partial_reason: Realtime not enabled in QjackCtl config.")
                        if ensure_prio and not prio_cfg_ok:
                            lines.append("partial_reason: Priority not set to expected value in QjackCtl config.")
                        if expected_cores is not None and not config_pin_ok:
                            lines.append("partial_reason: Post-start script missing or mismatched for CPU pinning.")
                        if runtime_pin_ok is False:
                            lines.append("partial_reason: running jackd not pinned to selected cores.")
                include_preset_lines = cfg is not None and bool(cfg.def_preset)
                base_keys = (
                    "ServerConfig",
                    "ServerConfigName",
                    "PostStartupScript",
                    "PostStartupScriptShell",
                    "\\Server",
                    "\\ServerPrefix",
                    "Realtime",
                    "Priority",
                )
                if include_preset_lines:
                    keys = ("Preset", "DefPreset", *base_keys)
                else:
                    keys = base_keys
                for line in _read_file(path, max_lines=200):
                    if line.strip().startswith("OldPreset"):
                        continue
                    if any(key in line for key in keys):
                        lines.append(line)
                if cfg is not None and cfg.server_config_enabled:
                    lines.append("")
                    if cfg.server_config_name:
                        lines.append(f"server_config: {cfg.server_config_name}")
                        server_path = resolve_server_config_path(cfg.server_config_name)
                        if server_path is None:
                            lines.append("server_config_path: unknown")
                        else:
                            lines.extend(_read_file(str(server_path), max_lines=40))
                    else:
                        lines.append("server_config: enabled (missing ServerConfigName)")
                lines.append("")
                pids = _find_pids_by_comm("jackd")
                if not pids:
                    lines.append("jackd: not running")
                else:
                    lines.append(f"jackd_pids: {', '.join(str(p) for p in pids)}")
                    for pid in pids:
                        cmdline = _read_proc_cmdline(pid)
                        if cmdline:
                            lines.append(f"jackd_cmd[{pid}]: {cmdline}")
                        allowed = _read_proc_cpu_allowed_list(pid)
                        if allowed:
                            lines.append(f"jackd_cpus_allowed_list[{pid}]: {allowed}")
                    total_threads, rt_threads, rt_priorities = _read_jackd_rt_summary(pids)
                    if total_threads:
                        lines.append(f"jackd_threads: {total_threads}")
                        lines.append(f"jackd_rt_threads: {rt_threads}")
                        if rt_priorities:
                            lines.append(f"jackd_rt_priorities: {', '.join(str(p) for p in rt_priorities)}")
            elif kind == "irq_affinity":
                from audioknob_gui.core.irq import collect_target_irqs, resolve_selected_devices

                def _read_irq_affinity(irq: int) -> str | None:
                    p = Path(f"/proc/irq/{irq}/smp_affinity_list")
                    if not p.exists():
                        return None
                    try:
                        return p.read_text(encoding="utf-8").strip()
                    except Exception:
                        return None

                lines.append("")
                lines.append("irq_pinning:")
                device_keys = self._irq_pinning_devices_from_state()
                cores = self._irq_pinning_cpu_cores_from_state()
                cpu_list = ",".join(str(c) for c in (cores or []))
                lines.append(f"cpu_cores: {cpu_list or 'unset'}")
                lines.append(f"device_keys: {', '.join(device_keys) if device_keys else 'unset'}")
                auto_housekeeping = bool(self.state.get("irq_housekeeping_auto", True))
                lines.append(f"housekeeping_auto: {auto_housekeeping}")
                if auto_housekeeping:
                    try:
                        from audioknob_gui.core.irq import read_cpu_present
                        audio_set = set(cores or [])
                        housekeeping = sorted(read_cpu_present() - audio_set)
                        hk_list = ",".join(str(c) for c in housekeeping)
                        lines.append(f"housekeeping_cores: {hk_list or 'unset'}")
                    except Exception:
                        lines.append("housekeeping_cores: unknown")
                else:
                    manual = self._kernel_cores_from_state("kernel_irqaffinity") or []
                    manual_list = ",".join(str(c) for c in manual)
                    lines.append(f"housekeeping_cores: {manual_list or 'unset'}")

                selected, missing = resolve_selected_devices(device_keys)
                if missing:
                    lines.append(f"missing_devices: {', '.join(missing)}")
                if selected:
                    for device in selected:
                        label = str(device.get("label") or device.get("key"))
                        bus = str(device.get("bus") or "unknown")
                        irqs = device.get("irqs") or []
                        lines.append(f"device: {label} [{bus}] irqs={','.join(str(i) for i in irqs) if irqs else 'none'}")
                        warning = device.get("warning")
                        if warning:
                            lines.append(f"warning: {warning}")
                else:
                    lines.append("device: none")

                target_irqs = collect_target_irqs(selected)
                mismatched: list[int] = []
                if target_irqs:
                    for irq in target_irqs:
                        current = _read_irq_affinity(irq)
                        if current is None:
                            lines.append(f"irq[{irq}]: missing")
                        else:
                            lines.append(f"irq[{irq}] affinity: {current}")
                            try:
                                from audioknob_gui.core.irq import parse_cpu_list

                                if cores and parse_cpu_list(current) != set(cores):
                                    mismatched.append(irq)
                            except Exception:
                                pass
                if status == "partial" and mismatched:
                    lines.append(
                        f"partial_reason: IRQs not on selected cores: {', '.join(str(i) for i in mismatched)}"
                    )
                if status == "partial" and missing:
                    lines.append("partial_reason: missing devices (selection not found); check device list.")
                if status == "partial" and cores:
                    try:
                        from audioknob_gui.core.irq import list_irqs, parse_cpu_list, read_irq_affinity_list

                        audio_set = set(cores)
                        sweep_ok = True
                        for irq in list_irqs():
                            if irq in target_irqs:
                                continue
                            current = read_irq_affinity_list(irq)
                            if current is None:
                                continue
                            if parse_cpu_list(current) & audio_set:
                                sweep_ok = False
                                break
                        if not sweep_ok:
                            lines.append(
                                "partial_reason: some non-audio IRQs still target audio cores (housekeeping sweep)."
                            )
                    except Exception:
                        pass
            elif kind == "rtirq_config":
                from audioknob_gui.core.rtirq import normalize_rtirq_list, rtirq_block_present
                from audioknob_gui.worker.ops import read_os_release, resolve_rtirq_config_path

                distro_id = read_os_release().get("ID", "")
                cfg_path = resolve_rtirq_config_path(distro_id)
                lines.append(f"rtirq_config: {cfg_path}")
                name_list = normalize_rtirq_list(params.get("name_list", ["snd", "usb"]))
                high_list = normalize_rtirq_list(params.get("high_list", name_list))
                prio_high = int(params.get("prio_high", 90))
                prio_decr = int(params.get("prio_decr", 5))
                cfg_ok = False
                try:
                    content = Path(cfg_path).read_text(encoding="utf-8")
                    cfg_ok = rtirq_block_present(
                        content,
                        name_list=name_list,
                        high_list=high_list,
                        prio_high=prio_high,
                        prio_decr=prio_decr,
                    )
                except Exception:
                    cfg_ok = False
                lines.append(f"rtirq_block: {cfg_ok}")
                unit = str(params.get("unit", "rtirq.service"))
                enabled = None
                active = None
                try:
                    enabled = subprocess.run(
                        ["systemctl", "is-enabled", unit],
                        capture_output=True,
                        text=True,
                    ).stdout.strip() or None
                except Exception:
                    enabled = None
                try:
                    active = subprocess.run(
                        ["systemctl", "is-active", unit],
                        capture_output=True,
                        text=True,
                    ).stdout.strip() or None
                except Exception:
                    active = None
                if enabled is not None:
                    lines.append(f"service_enabled: {enabled}")
                if active is not None:
                    lines.append(f"service_active: {active}")
                if status == "partial":
                    if cfg_ok and active != "active":
                        lines.append("partial_reason: config present but rtirq service not active.")
                    elif not cfg_ok and active == "active":
                        lines.append("partial_reason: rtirq service active but config block missing.")
            elif kind == "power_profile":
                try:
                    from audioknob_gui.worker.ops import read_power_profile, select_power_profile_backend
                except Exception:
                    read_power_profile = None
                    select_power_profile_backend = None
                pref = self._power_profile_backend_from_state()
                params_local = dict(params)
                params_local["backend"] = pref
                lines.append("")
                lines.append(f"backend_preference: {pref}")
                backend = select_power_profile_backend(params_local) if select_power_profile_backend else None
                if not backend:
                    lines.append("resolved_backend: none")
                    lines.append("note: powerprofilesctl or tuned-adm required")
                else:
                    lines.append(f"resolved_backend: {backend.get('backend')}")
                    cmd = backend.get("cmd") or ""
                    if cmd:
                        lines.append(f"cmd: {cmd}")
                    unit = backend.get("service")
                    if unit:
                        try:
                            r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
                            lines.append(f"service_active: {r.stdout.strip() or r.stderr.strip()}")
                        except Exception:
                            pass
                    if read_power_profile:
                        current = read_power_profile(backend["backend"], backend["cmd"])
                        if backend["backend"] == "powerprofilesctl":
                            target = str(params.get("ppd_profile", "performance")).strip() or "performance"
                        else:
                            target = str(params.get("tuned_profile", "latency-performance")).strip() or "latency-performance"
                        lines.append(f"current: {current or 'unknown'}")
                        lines.append(f"target: {target}")
                    try:
                        if backend["backend"] == "powerprofilesctl":
                            r = subprocess.run([backend["cmd"], "list"], capture_output=True, text=True)
                            output = (r.stdout or r.stderr or "").strip()
                            if output:
                                lines.append("available_profiles:")
                                lines.extend(output.splitlines()[:20])
                        elif backend["backend"] == "tuned":
                            r = subprocess.run([backend["cmd"], "list"], capture_output=True, text=True)
                            output = (r.stdout or r.stderr or "").strip()
                            if output:
                                lines.append("available_profiles:")
                                lines.extend(output.splitlines()[:20])
                    except Exception:
                        pass
            elif kind == "systemd_unit_toggle":
                unit = str(params.get("unit", ""))
                if unit:
                    lines.append(f"unit: {unit}")
                    for label, cmd in (
                        ("is-enabled", ["systemctl", "is-enabled", unit]),
                        ("is-active", ["systemctl", "is-active", unit]),
                    ):
                        r = subprocess.run(cmd, capture_output=True, text=True)
                        lines.append(f"{label}: {r.stdout.strip() or r.stderr.strip()}")
            elif kind == "user_service_mask":
                services = params.get("services")
                if isinstance(services, list):
                    from audioknob_gui.worker.ops import resolve_user_services

                    resolved = resolve_user_services([str(s) for s in services if s])
                    if resolved:
                        lines.append(f"user_services: {', '.join(resolved)}")
                    if not resolved:
                        lines.append("user units: [no matches]")
                    for svc in resolved:
                        lines.append(f"user unit: {svc}")
                        for label, cmd in (
                            ("user is-enabled", ["systemctl", "--user", "is-enabled", svc]),
                            ("user is-active", ["systemctl", "--user", "is-active", svc]),
                        ):
                            r = subprocess.run(cmd, capture_output=True, text=True)
                            lines.append(f"{label}: {r.stdout.strip() or r.stderr.strip()}")
                else:
                    unit = str(params.get("unit", ""))
                    if unit:
                        lines.append(f"user_services: {unit}")
                        for label, cmd in (
                            ("user is-enabled", ["systemctl", "--user", "is-enabled", unit]),
                            ("user is-active", ["systemctl", "--user", "is-active", unit]),
                        ):
                            r = subprocess.run(cmd, capture_output=True, text=True)
                            lines.append(f"{label}: {r.stdout.strip() or r.stderr.strip()}")
            elif kind == "sysctl_conf":
                path = str(params.get("path", ""))
                if path:
                    lines.extend(_read_file(path))
                    if status == "partial":
                        wanted_lines = [str(x) for x in params.get("lines", [])]
                        try:
                            content = Path(path).read_text(encoding="utf-8")
                            missing = [line for line in wanted_lines if line not in content]
                        except Exception:
                            missing = []
                        if missing:
                            lines.append(f"partial_reason: missing lines: {', '.join(missing)}")
                keys: list[str] = []
                expected: dict[str, str] = {}
                for line in params.get("lines", []) or []:
                    raw = str(line).strip()
                    if not raw or raw.startswith("#") or "=" not in raw:
                        continue
                    key, _, value = raw.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key and key not in keys:
                        keys.append(key)
                        expected[key] = value
                if keys:
                    try:
                        from audioknob_gui.platform.packages import which_command
                    except Exception:
                        which_command = None
                    sysctl_cmd = None
                    if which_command:
                        sysctl_cmd = which_command("sysctl")
                    if not sysctl_cmd:
                        sysctl_cmd = shutil.which("sysctl") or "sysctl"
                    for key in keys:
                        try:
                            r = subprocess.run([sysctl_cmd, "-n", key], capture_output=True, text=True)
                            current = r.stdout.strip() or r.stderr.strip() or "unknown"
                        except Exception as e:
                            current = f"error: {e}"
                        exp = expected.get(key)
                        if exp is not None:
                            lines.append(f"sysctl {key}: {current} (expected: {exp})")
                        else:
                            lines.append(f"sysctl {key}: {current}")
            elif kind == "sysfs_glob_kv":
                pattern = str(params.get("glob", ""))
                if pattern:
                    paths = sorted(glob.glob(pattern))
                    expected_val = str(params.get("value", "")).strip()
                    total = len(paths)
                    match = 0
                    unreadable = 0
                    for p in paths:
                        try:
                            val = Path(p).read_text(encoding="utf-8").strip()
                            if expected_val and val == expected_val:
                                match += 1
                        except Exception:
                            unreadable += 1
                    mismatch = max(0, total - match - unreadable)
                    if expected_val:
                        lines.append(
                            f"sysfs_summary: total={total} match={match} mismatch={mismatch} unreadable={unreadable} "
                            f"(expected: {expected_val})"
                        )
                    else:
                        lines.append(
                            f"sysfs_summary: total={total} unreadable={unreadable}"
                        )
                    for p in paths[:8]:
                        try:
                            val = Path(p).read_text(encoding="utf-8").strip()
                            lines.append(f"{p}: {val}")
                        except Exception as e:
                            lines.append(f"{p}: unreadable: {e}")
                    if knob.id == "cpu_governor_performance_persistent":
                        try:
                            from audioknob_gui.worker.ops import (
                                read_os_release,
                                resolve_cpupower_config_path,
                                resolve_cpu_governor_service,
                            )
                            os_release = read_os_release()
                            distro_id = os_release.get("ID", "")
                            cfg_path = resolve_cpupower_config_path(distro_id)
                            lines.append(f"cpupower_config: {cfg_path}")
                            try:
                                cfg_text = Path(cfg_path).read_text(encoding="utf-8")
                            except Exception as e:
                                cfg_text = None
                                lines.append(f"cpupower_config_read_error: {e}")
                            if cfg_text:
                                for line in cfg_text.splitlines():
                                    if "GOVERNOR" in line:
                                        lines.append(f"cpupower_config_governor: {line.strip()}")
                                        break
                            service = resolve_cpu_governor_service(distro_id)
                            if service:
                                for label, cmd in (
                                    ("service_enabled", ["systemctl", "is-enabled", service]),
                                    ("service_active", ["systemctl", "is-active", service]),
                                ):
                                    r = subprocess.run(cmd, capture_output=True, text=True)
                                    lines.append(f"{label}: {r.stdout.strip() or r.stderr.strip()}")
                        except Exception:
                            pass
            elif kind == "kernel_cmdline":
                param = str(params.get("param", ""))
                override = self._kernel_cmdline_param_for_state(knob.id)
                if override:
                    param = override
                running_has = None
                boot_has = None
                if param:
                    try:
                        running = Path("/proc/cmdline").read_text(encoding="utf-8").strip()
                        lines.append(f"/proc/cmdline: {running}")
                        tokens = running.split()
                        running_has = _param_present(tokens, param)
                        lines.append(f"/proc/cmdline has {param}: {running_has}")
                    except Exception as e:
                        lines.append(f"/proc/cmdline read error: {e}")
                    try:
                        from audioknob_gui.worker.ops import detect_distro
                        import shlex
                        distro = detect_distro()
                        boot_path = distro.kernel_cmdline_file
                        if boot_path:
                            boot_text = Path(boot_path).read_text(encoding="utf-8")
                            in_boot = False
                            if distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                                in_boot = _param_present(boot_text.split(), param)
                            elif distro.boot_system == "grub2":
                                for line in boot_text.splitlines():
                                    if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                                        _, _, rhs = line.partition("=")
                                        rhs = rhs.strip().strip('"')
                                        try:
                                            tokens = shlex.split(rhs)
                                        except Exception:
                                            tokens = rhs.split()
                                        in_boot = _param_present(tokens, param)
                                        break
                            boot_has = in_boot
                            lines.append(f"{boot_path} has {param}: {in_boot}")
                    except Exception as e:
                        lines.append(f"boot config read error: {e}")
                if status == "partial" and param and running_has is not None and boot_has is not None:
                    if boot_has and not running_has:
                        lines.append("partial_reason: boot config set but reboot not applied yet.")
                    elif running_has and not boot_has:
                        lines.append("partial_reason: running kernel has param but boot config missing.")
                    else:
                        lines.append("partial_reason: running/boot config mismatch; verify bootloader updates.")
            elif kind == "udev_rule":
                path = str(params.get("path", ""))
                if path:
                    lines.extend(_read_file(path))
                    expected = str(params.get("content", "")).strip()
                    if expected:
                        try:
                            current = Path(path).read_text(encoding="utf-8")
                            present = expected in current
                        except Exception:
                            present = False
                        lines.append(f"expected_rule_present: {present}")
            elif kind == "pipewire_conf":
                path = str(params.get("path", "~/.config/pipewire/pipewire.conf.d/99-audioknob.conf"))
                lines.extend(_read_file(path))
                try:
                    for label, cmd in (
                        ("pipewire_active", ["systemctl", "--user", "is-active", "pipewire"]),
                        ("wireplumber_active", ["systemctl", "--user", "is-active", "wireplumber"]),
                        ("pipewire_pulse_active", ["systemctl", "--user", "is-active", "pipewire-pulse"]),
                    ):
                        r = subprocess.run(cmd, capture_output=True, text=True)
                        lines.append(f"{label}: {r.stdout.strip() or r.stderr.strip()}")
                except Exception:
                    pass
                try:
                    if shutil.which("pw-metadata"):
                        r = subprocess.run(
                            ["pw-metadata", "-n", "settings", "0"],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        output = (r.stdout or r.stderr or "").strip()
                        if output:
                            clock_rate = None
                            clock_quantum = None
                            for line in output.splitlines():
                                if "clock.rate" in line:
                                    match = re.search(r"clock\\.rate\\s*=\\s*(\\d+)", line)
                                    if match:
                                        clock_rate = match.group(1)
                                if "clock.quantum" in line:
                                    match = re.search(r"clock\\.quantum\\s*=\\s*(\\d+)", line)
                                    if match:
                                        clock_quantum = match.group(1)
                            if clock_rate or clock_quantum:
                                lines.append(
                                    f"pipewire_runtime: rate={clock_rate or 'unknown'} "
                                    f"quantum={clock_quantum or 'unknown'}"
                                )
                except Exception:
                    pass
            elif kind == "group_membership":
                r = subprocess.run(["id"], capture_output=True, text=True)
                lines.append(f"id: {r.stdout.strip()}")
                try:
                    from audioknob_gui.platform.detect import get_missing_groups

                    missing = get_missing_groups()
                    if missing:
                        lines.append(f"missing_groups: {', '.join(missing)}")
                    else:
                        lines.append("missing_groups: none")
                except Exception:
                    pass
            elif kind == "pam_limits_audio_group":
                path = str(params.get("path", ""))
                if path:
                    lines.extend(_read_file(path))
                    if status == "partial":
                        wanted_lines = [str(x) for x in params.get("lines", [])]
                        try:
                            content = Path(path).read_text(encoding="utf-8")
                            missing = [line for line in wanted_lines if line not in content]
                        except Exception:
                            missing = []
                        if missing:
                            lines.append(f"partial_reason: missing lines: {', '.join(missing)}")
                try:
                    import resource
                    rt_soft, rt_hard = resource.getrlimit(resource.RLIMIT_RTPRIO)
                    mem_soft, mem_hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)
                    lines.append(f"rtprio: {rt_soft}/{rt_hard}")
                    lines.append(f"memlock: {mem_soft}/{mem_hard}")
                except Exception as e:
                    lines.append(f"limits read error: {e}")
            elif kind == "baloo_disable":
                cmd = "balooctl6" if shutil.which("balooctl6") else "balooctl"
                lines.append(f"command: {cmd}")
                if shutil.which(cmd):
                    r = subprocess.run([cmd, "status"], capture_output=True, text=True)
                    lines.append(r.stdout.strip() or r.stderr.strip())
                else:
                    lines.append("balooctl not found")
            elif kind == "read_only":
                what = str(params.get("what", "")).strip()
                if what:
                    lines.append(f"read_only: {what}")
                if knob.id == "scheduler_jitter_test":
                    last = self.state.get("jitter_test_last")
                    if isinstance(last, dict):
                        max_us = last.get("max_us")
                        threads = last.get("threads")
                        lines.append("last_jitter_test:")
                        if isinstance(max_us, int):
                            lines.append(f"  max_us: {max_us}")
                        if isinstance(threads, list):
                            lines.append(f"  threads: {len(threads)}")

            return lines

        def _show_cli_status(self, knob_id: str) -> None:
            k = next((k for k in self.registry if k.id == knob_id), None)
            if not k:
                return

            def _cli_status() -> str:
                try:
                    status_data = json.loads(
                        subprocess.check_output(
                            [
                                sys.executable,
                                "-m",
                                "audioknob_gui.worker.cli",
                                "--registry",
                                _registry_path(),
                                "status",
                            ],
                            text=True,
                        )
                    )
                    item = next(
                        (s for s in status_data.get("statuses", []) if s.get("knob_id") == k.id),
                        None,
                    )
                    if item:
                        return str(item.get("status", "unknown"))
                    return "not found"
                except Exception as e:
                    return f"error: {e}"

            dialog = QDialog(self)
            dialog.setWindowTitle(f"{k.title} Status Check")
            dialog.resize(640, 460)
            layout = QVBoxLayout(dialog)

            header = QLabel(f"<b>{k.title}</b>")
            layout.addWidget(header)

            gui_status_label = QLabel(f"GUI status: {self._knob_statuses.get(k.id, 'unknown')}")
            layout.addWidget(gui_status_label)

            cli_status_label = QLabel("CLI status: (not run yet)")
            layout.addWidget(cli_status_label)

            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText("Click Refresh to run CLI status and preview checks.")
            layout.addWidget(text)

            btn_row = QHBoxLayout()
            refresh_btn = QPushButton("Refresh")
            refresh_btn.setFocusPolicy(Qt.NoFocus)
            btn_row.addWidget(refresh_btn)
            btn_row.addStretch(1)
            close_btn = QPushButton("Close")
            close_btn.setFocusPolicy(Qt.NoFocus)
            close_btn.clicked.connect(dialog.reject)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

            def _render(payload: dict) -> None:
                gui_status_label.setText(f"GUI status: {self._knob_statuses.get(k.id, 'unknown')}")
                cli_status_label.setText(f"CLI status: {payload.get('cli_status', 'unknown')}")

                checks = payload.get("live_checks") or []
                baseline_checks = self.state.get("baseline_checks", {})
                if isinstance(baseline_checks, dict) and baseline_checks.get(k.id):
                    checks = list(checks)
                    checks.append("")
                    checks.append("initial state:")
                    checks.extend(str(x) for x in baseline_checks[k.id])
                text.setPlainText("\n".join(checks))

            def _run_checks() -> None:
                refresh_btn.setEnabled(False)
                cli_status_label.setText("CLI status: running...")
                text.setPlainText("Running CLI checks...")

                def _task():
                    return True, {
                        "cli_status": _cli_status(),
                        "live_checks": self._collect_live_checks(k),
                    }, ""

                worker = QueueTaskWorker(_task, parent=dialog)

                def _on_done(success: bool, payload: object, message: str) -> None:
                    refresh_btn.setEnabled(True)
                    if not success:
                        cli_status_label.setText(f"CLI status: error: {message or 'unknown'}")
                        text.setPlainText(message or "CLI check failed")
                        return
                    if isinstance(payload, dict):
                        _render(payload)
                    else:
                        text.setPlainText("CLI check returned no data.")

                worker.finished.connect(_on_done)
                worker.finished.connect(worker.deleteLater)
                self._task_threads.append(worker)
                worker.start()

            refresh_btn.clicked.connect(_run_checks)
            _run_checks()

            dialog.exec()

        def on_check_blockers(self) -> None:
            """Run comprehensive realtime configuration scan."""
            dialog = QDialog(self)
            dialog.setWindowTitle("RT Config Scan")
            dialog.resize(600, 400)
            layout = QVBoxLayout(dialog)
            status_label = QLabel("Running scan...")
            layout.addWidget(status_label)

            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText("Collecting system info...")
            layout.addWidget(text)

            # Button row with Show Full Scan option
            btn_layout = QHBoxLayout()

            full_html: dict[str, str] = {}
            def show_full_scan() -> None:
                html = full_html.get("full")
                if html:
                    text.setHtml(html)
                    dialog.setWindowTitle(full_html.get("title", "RT Config Scan (Full)"))

            full_btn = QPushButton("Show Full Scan")
            full_btn.setEnabled(False)
            full_btn.clicked.connect(show_full_scan)
            btn_layout.addWidget(full_btn)
            btn_layout.addStretch()

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)

            def _task() -> tuple[bool, object, str]:
                from audioknob_gui.testing.rtcheck import run_full_scan, format_scan_html, CheckStatus

                result = run_full_scan()

                actionable_checks = [c for c in result.checks if c.fix_knob is not None]
                actionable_issues = [
                    c for c in actionable_checks if c.status not in (CheckStatus.PASS, CheckStatus.SKIP)
                ]

                html = ["<h3>RT Configuration Issues You Can Fix</h3>"]

                if actionable_issues:
                    html.append(f"<p>Found {len(actionable_issues)} issue(s) with available fixes.</p>")
                    html.append("<table style='width:100%'>")
                    for c in actionable_issues:
                        color = {"warn": "#f57c00", "fail": "#d32f2f"}.get(c.status.value, "#000")
                        icon = {"warn": "⚠", "fail": "✗"}.get(c.status.value, "?")
                        html.append(f"<tr><td style='color:{color}'>{icon}</td>")
                        html.append(f"<td><b>{c.name}</b></td>")
                        html.append(f"<td>{c.message}</td></tr>")
                        html.append("<tr><td></td><td colspan='2' style='color:#666; font-size:0.9em'>")
                        if c.detail:
                            html.append(f"{c.detail}<br/>")
                        html.append(f"<i>Fix: Use '{c.fix_knob}' knob in the main menu</i>")
                        html.append("</td></tr>")
                    html.append("</table>")
                else:
                    html.append("<p style='color:#2e7d32'>✓ All fixable checks passed!</p>")

                html.append("<hr/>")
                html.append(
                    f"<p style='color:#666; font-size:0.9em'>Full scan: {result.passed} passed, "
                    f"{result.warnings} warnings, {result.failed} failed (score: {result.score}%)</p>"
                )

                return True, {
                    "summary_html": "".join(html),
                    "full_html": format_scan_html(result),
                    "score": result.score,
                }, ""

            worker = QueueTaskWorker(_task, parent=dialog)

            def _on_done(success: bool, payload: object, message: str) -> None:
                if not success or not isinstance(payload, dict):
                    status_label.setText("Scan failed")
                    text.setPlainText(message or "Scan failed")
                    return
                status_label.setText("Scan complete")
                text.setHtml(payload.get("summary_html", ""))
                score = payload.get("score")
                full_html["full"] = payload.get("full_html", "")
                if isinstance(score, int):
                    full_html["title"] = f"RT Config Scan (Full) - Score: {score}%"
                full_btn.setEnabled(bool(full_html.get("full")))

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

            dialog.exec()

        def _on_join_groups(self) -> None:
            """Add current user to audio groups."""
            from audioknob_gui.platform.detect import get_available_audio_groups, get_missing_groups
            from audioknob_gui.platform.packages import which_command
            
            logger = _get_gui_logger()
            if "audio_group_membership" in self._busy_knobs:
                return
            missing = get_missing_groups()
            available = get_available_audio_groups()
            
            if not missing:
                QMessageBox.information(
                    self, 
                    "Groups OK", 
                    "You are already in all available audio groups!"
                )
                return
            
            # Show what groups we'll add
            groups_to_add = [g for g in missing if g in available]
            if not groups_to_add:
                QMessageBox.warning(
                    self,
                    "No Groups Available",
                    "No audio groups exist on this system."
                )
                return
            
            reply = QMessageBox.question(
                self,
                "Join Audio Groups",
                f"Add user to these groups?\n\n• {chr(10).join(groups_to_add)}\n\n"
                f"Note: You must log out and back in for changes to take effect.",
                QMessageBox.Ok | QMessageBox.Cancel
            )
            
            if reply != QMessageBox.Ok:
                return
            
            # Run usermod via pkexec for each group
            import getpass
            usermod = which_command("usermod")
            if not usermod:
                QMessageBox.critical(self, "Error", "usermod not found on this system.")
                logger.error("join groups failed: usermod not found")
                _log_gui_audit(
                    "join-groups",
                    {
                        "user": os.environ.get("USER") or "",
                        "groups": groups_to_add,
                        "error": "usermod not found",
                    },
                )
                return

            user = os.environ.get("USER") or getpass.getuser()
            self._busy_knobs.add("audio_group_membership")
            self._knob_statuses["audio_group_membership"] = "running"
            self._populate()

            def _task() -> tuple[bool, object, str]:
                errors: list[str] = []
                successes: list[str] = []
                results: list[dict[str, object]] = []

                for group in groups_to_add:
                    try:
                        cmd = ["pkexec", usermod, "-aG", group, user]
                        p = subprocess.run(cmd, capture_output=True, text=True)
                        results.append(
                            {
                                "group": group,
                                "cmd": cmd,
                                "returncode": p.returncode,
                                "stdout": p.stdout,
                                "stderr": p.stderr,
                            }
                        )
                        if p.returncode == 0:
                            successes.append(group)
                        else:
                            errors.append(f"{group}: {p.stderr.strip() or 'Failed'}")
                    except Exception as e:
                        results.append({"group": group, "error": str(e)})
                        errors.append(f"{group}: {e}")

                payload = {
                    "user": user,
                    "groups": groups_to_add,
                    "added": successes,
                    "errors": errors,
                    "results": results,
                }
                return len(errors) == 0, payload, ""

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                self._busy_knobs.discard("audio_group_membership")
                errors: list[str] = []
                added: list[str] = []
                if isinstance(payload, dict):
                    errors = payload.get("errors") or []
                    added = payload.get("added") or []
                if not added and not errors and message:
                    errors = [message]

                msg = []
                if added:
                    msg.append(f"<b style='color: #2e7d32;'>Added to:</b> {', '.join(added)}")
                if errors:
                    msg.append(f"<br/><b style='color: #d32f2f;'>Errors:</b><br/>{'<br/>'.join(errors)}")
                if added:
                    msg.append("<br/><br/><b>Reboot required for changes to take effect.</b>")

                QMessageBox.information(self, "Group Membership", "".join(msg))
                logger.info("join groups user=%s added=%s errors=%s", user, ",".join(added), "; ".join(errors))
                if isinstance(payload, dict):
                    _log_gui_audit("join-groups", payload)

                if added:
                    self._knob_statuses["audio_group_membership"] = "pending_reboot"
                    self._update_reboot_banner()

                self._refresh_user_groups()
                self._populate()

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _on_leave_groups(self) -> None:
            """Remove current user from audio groups."""
            from audioknob_gui.platform.detect import get_available_audio_groups
            from audioknob_gui.platform.packages import which_command

            logger = _get_gui_logger()
            if "audio_group_membership" in self._busy_knobs:
                return
            self._refresh_user_groups()
            available = get_available_audio_groups()
            groups_to_remove = [g for g in available if g in self._user_groups]

            if not groups_to_remove:
                QMessageBox.information(
                    self,
                    "No Groups",
                    "You are not currently in any audio groups."
                )
                return

            reply = QMessageBox.question(
                self,
                "Leave Audio Groups",
                f"Remove user from these groups?\n\n• {chr(10).join(groups_to_remove)}\n\n"
                f"Note: A reboot is required for changes to take effect.",
                QMessageBox.Ok | QMessageBox.Cancel
            )
            if reply != QMessageBox.Ok:
                return

            import getpass
            user = os.environ.get("USER") or getpass.getuser()
            gpasswd = which_command("gpasswd")
            usermod = which_command("usermod")
            if not gpasswd and not usermod:
                QMessageBox.critical(self, "Error", "Neither gpasswd nor usermod found on this system.")
                logger.error("leave groups failed: no gpasswd/usermod")
                _log_gui_audit(
                    "leave-groups",
                    {
                        "user": user,
                        "groups": groups_to_remove,
                        "error": "no gpasswd/usermod",
                    },
                )
                return
            self._busy_knobs.add("audio_group_membership")
            self._knob_statuses["audio_group_membership"] = "running"
            self._populate()

            def _task() -> tuple[bool, object, str]:
                errors: list[str] = []
                successes: list[str] = []
                results: list[dict[str, object]] = []

                if gpasswd:
                    for group in groups_to_remove:
                        try:
                            cmd = ["pkexec", gpasswd, "-d", user, group]
                            p = subprocess.run(cmd, capture_output=True, text=True)
                            results.append(
                                {
                                    "group": group,
                                    "cmd": cmd,
                                    "returncode": p.returncode,
                                    "stdout": p.stdout,
                                    "stderr": p.stderr,
                                }
                            )
                            if p.returncode == 0:
                                successes.append(group)
                            else:
                                errors.append(f"{group}: {p.stderr.strip() or 'Failed'}")
                        except Exception as e:
                            results.append({"group": group, "error": str(e)})
                            errors.append(f"{group}: {e}")
                else:
                    try:
                        import grp
                        keep_groups = []
                        for gid in os.getgroups():
                            try:
                                keep_groups.append(grp.getgrgid(gid).gr_name)
                            except KeyError:
                                pass
                        keep_groups = [g for g in keep_groups if g not in groups_to_remove]
                        group_list = ",".join(sorted(set(keep_groups)))
                        cmd = ["pkexec", usermod, "-G", group_list, user]
                        p = subprocess.run(cmd, capture_output=True, text=True)
                        results.append(
                            {
                                "groups": groups_to_remove,
                                "cmd": cmd,
                                "returncode": p.returncode,
                                "stdout": p.stdout,
                                "stderr": p.stderr,
                            }
                        )
                        if p.returncode == 0:
                            successes.extend(groups_to_remove)
                        else:
                            errors.append(p.stderr.strip() or "Failed to update groups")
                    except Exception as e:
                        results.append({"groups": groups_to_remove, "error": str(e)})
                        errors.append(str(e))

                payload = {
                    "user": user,
                    "groups": groups_to_remove,
                    "removed": successes,
                    "errors": errors,
                    "results": results,
                }
                return len(errors) == 0, payload, ""

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                self._busy_knobs.discard("audio_group_membership")
                errors: list[str] = []
                removed: list[str] = []
                if isinstance(payload, dict):
                    errors = payload.get("errors") or []
                    removed = payload.get("removed") or []
                if not removed and not errors and message:
                    errors = [message]

                msg = []
                if removed:
                    msg.append(f"<b style='color: #2e7d32;'>Removed from:</b> {', '.join(removed)}")
                if errors:
                    msg.append(f"<br/><b style='color: #d32f2f;'>Errors:</b><br/>{'<br/>'.join(errors)}")
                if removed:
                    msg.append("<br/><br/><b>Reboot required for changes to take effect.</b>")

                QMessageBox.information(self, "Group Membership", "".join(msg))
                logger.info("leave groups user=%s removed=%s errors=%s", user, ",".join(removed), "; ".join(errors))
                if isinstance(payload, dict):
                    _log_gui_audit("leave-groups", payload)

                if removed:
                    self._knob_statuses["audio_group_membership"] = "pending_reboot"
                    self._update_reboot_banner()

                self._refresh_user_groups()
                self._populate()

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _on_install_packages(self, commands: list[str]) -> None:
            """Install packages that provide the given commands."""
            from audioknob_gui.platform.packages import get_package_name, detect_package_manager

            if self._install_busy:
                QMessageBox.information(self, "Install in progress", "Package installation is already running.")
                return

            logger = _get_gui_logger()
            # Map commands to package names
            packages = []
            unknown = []
            for cmd in commands:
                pkg = get_package_name(cmd)
                if pkg:
                    packages.append(pkg)
                else:
                    unknown.append(cmd)
            
            if unknown:
                QMessageBox.warning(
                    self,
                    "Unknown Package",
                    f"Cannot determine package for: {', '.join(unknown)}\n\n"
                    f"Please install manually."
                )
                _log_gui_audit(
                    "install-packages",
                    {
                        "commands": commands,
                        "packages": packages,
                        "unknown": unknown,
                        "error": "unknown package mapping",
                    },
                )
                return
            
            packages = list(set(packages))  # Dedupe
            
            # Confirm installation
            reply = QMessageBox.question(
                self,
                "Install Packages",
                f"Install the following packages?\n\n• {chr(10).join(packages)}",
                QMessageBox.Ok | QMessageBox.Cancel
            )
            
            if reply != QMessageBox.Ok:
                _log_gui_audit(
                    "install-packages",
                    {
                        "commands": commands,
                        "packages": packages,
                        "status": "cancelled",
                    },
                )
                return
            
            # Run package manager via pkexec
            manager = detect_package_manager()
            
            try:
                from audioknob_gui.platform.packages import PackageManager
                import shutil
                
                if manager == PackageManager.RPM:
                    if shutil.which("zypper"):
                        cmd = ["pkexec", "zypper", "--non-interactive", "install", *packages]
                    else:
                        cmd = ["pkexec", "dnf", "install", "-y", *packages]
                elif manager == PackageManager.DPKG:
                    cmd = ["pkexec", "apt-get", "install", "-y", *packages]
                elif manager == PackageManager.PACMAN:
                    cmd = ["pkexec", "pacman", "-S", "--noconfirm", *packages]
                else:
                    QMessageBox.warning(self, "Error", "Unknown package manager")
                    _log_gui_audit(
                        "install-packages",
                        {
                            "commands": commands,
                            "packages": packages,
                            "error": "unknown package manager",
                        },
                    )
                    return

                def _run_install(*, retry: bool) -> None:
                    def _task() -> tuple[bool, object, str]:
                        try:
                            p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                        except subprocess.TimeoutExpired:
                            return False, {
                                "cmd": cmd,
                                "returncode": -1,
                                "stdout": "",
                                "stderr": "timeout",
                                "retry": retry,
                                "timeout": True,
                            }, "timeout"
                        return p.returncode == 0, {
                            "cmd": cmd,
                            "returncode": p.returncode,
                            "stdout": p.stdout,
                            "stderr": p.stderr,
                            "retry": retry,
                        }, ""

                    worker = QueueTaskWorker(_task, parent=self)

                    def _on_done(success: bool, payload: object, message: str) -> None:
                        if not isinstance(payload, dict):
                            self._install_busy = False
                            QMessageBox.critical(self, "Error", message or "Install error")
                            return

                        stderr = (payload.get("stderr") or "").strip()
                        stdout = (payload.get("stdout") or "").strip()
                        rc = payload.get("returncode")
                        retry_flag = bool(payload.get("retry"))

                        if success:
                            if any(cmd_name in ("qjackctl", "qjackctl6") for cmd_name in commands):
                                self._prime_qjackctl_preset()
                            QMessageBox.information(
                                self,
                                "Success",
                                f"Installed: {', '.join(packages)}"
                            )
                            _log_gui_audit(
                                "install-packages",
                                {
                                    "commands": commands,
                                    "packages": packages,
                                    "cmd": cmd,
                                    "returncode": rc,
                                    "stdout": stdout,
                                    "stderr": stderr,
                                    "retry": retry_flag,
                                },
                            )
                            self._populate()
                            self._install_busy = False
                            return

                        if payload.get("timeout"):
                            QMessageBox.critical(self, "Timeout", "Package installation timed out")
                            _log_gui_audit(
                                "install-packages",
                                {
                                    "commands": commands,
                                    "packages": packages,
                                    "cmd": cmd,
                                    "error": "timeout",
                                },
                            )
                            self._install_busy = False
                            return

                        combined = (stderr + "\n" + stdout).lower()
                        logger.error("install packages failed cmd=%s rc=%s stderr=%s stdout=%s", cmd, rc, stderr, stdout)
                        _log_gui_audit(
                            "install-packages",
                            {
                                "commands": commands,
                                "packages": packages,
                                "cmd": cmd,
                                "returncode": rc,
                                "stdout": stdout,
                                "stderr": stderr,
                                "retry": retry_flag,
                            },
                        )

                        no_provider = any(
                            needle in combined
                            for needle in (
                                "no provider of",
                                "no provider found",
                                "nothing provides",
                                "not found in enabled repositories",
                                "not found in enabled repos",
                            )
                        )
                        if no_provider and manager == PackageManager.RPM and shutil.which("zypper"):
                            reply = QMessageBox.question(
                                self,
                                "Add Repositories",
                                "Packages not found in enabled repos.\n\n"
                                "Add repositories and retry?\n\n"
                                "• multimedia:proaudio\n"
                                "• packman",
                                QMessageBox.Ok | QMessageBox.Cancel
                            )
                            if reply == QMessageBox.Ok:
                                repo_defs = [
                                    ("multimedia:proaudio", "https://download.opensuse.org/repositories/multimedia:/proaudio/openSUSE_Tumbleweed/"),
                                    ("packman", "https://ftp.gwdg.de/pub/linux/misc/packman/suse/openSUSE_Tumbleweed/"),
                                ]

                                def _repo_task() -> tuple[bool, object, str]:
                                    repo_errors = []
                                    for name, url in repo_defs:
                                        add_cmd = ["pkexec", "zypper", "ar", "-f", "-n", name, url, name]
                                        r = subprocess.run(add_cmd, capture_output=True, text=True, timeout=120)
                                        if r.returncode != 0:
                                            msg = (r.stderr.strip() or r.stdout.strip())
                                            if "already exists" not in msg.lower():
                                                repo_errors.append(f"{name}: {msg or 'failed'}")

                                    if not repo_errors:
                                        refresh_cmd = ["pkexec", "zypper", "--gpg-auto-import-keys", "refresh"]
                                        r = subprocess.run(refresh_cmd, capture_output=True, text=True, timeout=300)
                                        if r.returncode != 0:
                                            repo_errors.append(r.stderr.strip() or r.stdout.strip() or "refresh failed")

                                    if repo_errors:
                                        return False, {"errors": repo_errors}, "repo add failed"
                                    return True, {"errors": []}, ""

                                repo_worker = QueueTaskWorker(_repo_task, parent=self)

                                def _on_repo_done(success: bool, payload: object, message: str) -> None:
                                    if not success or not isinstance(payload, dict):
                                        self._install_busy = False
                                        QMessageBox.critical(self, "Repo Add Failed", message or "Repo add failed")
                                        return
                                    repo_errors = payload.get("errors") or []
                                    if repo_errors:
                                        self._install_busy = False
                                        logger.error("repo add failed errors=%s", "; ".join(repo_errors))
                                        QMessageBox.critical(
                                            self,
                                            "Repo Add Failed",
                                            "Failed to add repositories:\n\n" + "\n".join(repo_errors)
                                        )
                                        return

                                    _run_install(retry=True)

                                repo_worker.finished.connect(_on_repo_done)
                                repo_worker.finished.connect(repo_worker.deleteLater)
                                self._task_threads.append(repo_worker)
                                repo_worker.start()
                                return

                        if any(needle in combined for needle in ("no provider of", "nothing provides")):
                            QMessageBox.critical(
                                self,
                                "Install Failed",
                                "Package not found in enabled repositories.\n\n"
                                "rtirq may not be available for this distro snapshot."
                            )
                        else:
                            QMessageBox.critical(
                                self,
                                "Install Failed",
                                f"Failed to install packages:\n\n{stderr or stdout}"
                            )
                        self._install_busy = False

                    worker.finished.connect(_on_done)
                    worker.finished.connect(worker.deleteLater)
                    self._task_threads.append(worker)
                    worker.start()

                self._install_busy = True
                _run_install(retry=False)

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Install error: {e}")
                _log_gui_audit(
                    "install-packages",
                    {
                        "commands": commands,
                        "packages": packages,
                        "cmd": cmd if "cmd" in locals() else None,
                        "error": str(e),
                    },
                )
                self._install_busy = False

        def _on_apply_knob(self, knob_id: str) -> None:
            """Apply a single knob optimization."""
            k = next((k for k in self.registry if k.id == knob_id), None)
            if not k:
                return
            if knob_id == "qjackctl_server_prefix_rt" and self._is_process_running(["qjackctl", "qjackctl6"]):
                QMessageBox.information(
                    self,
                    "Close QjackCtl First",
                    "Quit QjackCtl before applying QjackCtl RT.\n\n"
                    "QjackCtl rewrites its config on exit, which can undo changes.",
                )
                return

            def _task():
                if knob_id == "qjackctl_server_prefix_rt":
                    self._prime_qjackctl_preset()
                if k.requires_root:
                    result = _run_worker_apply_pkexec([knob_id])
                    return True, {"result": result, "requires_root": True}, ""
                result = _run_worker_apply_user([knob_id])
                return True, {"result": result, "requires_root": False}, ""

            self._run_knob_task(knob_id, "apply", _task)

        def _on_queue_knob(self, knob_id: str, action: str) -> None:
            if knob_id in self._busy_knobs:
                return
            if self._queued_actions.get(knob_id) == action:
                self._queued_actions.pop(knob_id, None)
            else:
                self._queued_actions[knob_id] = action
            self._save_queue()
            self._update_queue_ui()
            self._populate()

        def _on_advanced_mode_toggle(self, enabled: bool) -> None:
            self.state["advanced_mode_enabled"] = bool(enabled)
            save_state(self.state)
            v_scroll = None
            try:
                v_scroll = self.table.verticalScrollBar().value()
                self.table.clearSelection()
                self._clear_dim_hover()
            except Exception:
                v_scroll = None
            self._populate()
            if v_scroll is not None:
                try:
                    self.table.verticalScrollBar().setValue(v_scroll)
                except Exception:
                    pass

        def _power_profile_backend_is_tuned(self) -> bool:
            pref = self._power_profile_backend_from_state()
            if pref == "tuned":
                return True
            if pref == "powerprofilesctl":
                return False
            try:
                from audioknob_gui.worker.ops import select_power_profile_backend

                params = {"backend": "auto"}
                backend = select_power_profile_backend(params)
                return bool(backend) and backend.get("backend") == "tuned"
            except Exception:
                return False

        def _prompt_tuned_conflicts(self, conflict_ids: list[str]) -> str:
            by_id = {k.id: k for k in self.registry}
            titles = [by_id.get(cid).title if cid in by_id else cid for cid in conflict_ids]
            msg = (
                "tuned can override settings from these knobs:\n\n"
                + ", ".join(titles)
                + "\n\nQueue resets for the conflicting knobs?"
            )
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("tuned conflicts")
            box.setText(msg)
            reset_btn = box.addButton("Queue resets", QMessageBox.AcceptRole)
            box.addButton("Continue", QMessageBox.DestructiveRole)
            cancel_btn = box.addButton(QMessageBox.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked == reset_btn:
                return "reset"
            if clicked == cancel_btn:
                return "cancel"
            return "continue"

        def _on_apply_queue(self, reboot_after: bool) -> bool:
            if not self._queued_actions or self._queue_busy:
                return False
            if self._busy_knobs:
                QMessageBox.information(
                    self,
                    "Busy",
                    "Finish current operations before applying queued changes.",
                )
                return False
            by_id = {k.id: k for k in self.registry}
            queued = [(kid, action) for kid, action in self._queued_actions.items() if kid in by_id]
            if not queued:
                return False
            if any(kid == "power_profile_performance" and action == "apply" for kid, action in queued):
                if self._power_profile_backend_is_tuned():
                    conflict_ids = [
                        cid
                        for cid in self._tuned_conflict_ids()
                        if self._queued_actions.get(cid) == "apply"
                        or self._knob_statuses.get(cid) in ("applied", "pending_reboot")
                    ]
                    if conflict_ids:
                        choice = self._prompt_tuned_conflicts(conflict_ids)
                        if choice == "cancel":
                            return False
                        if choice == "reset":
                            for cid in conflict_ids:
                                self._queued_actions[cid] = "reset"
                            self._save_queue()
                            self._update_queue_ui()
                            self._populate()
                            queued = [(kid, action) for kid, action in self._queued_actions.items() if kid in by_id]
                            if not queued:
                                return False
            if any(kid == "qjackctl_server_prefix_rt" for kid, _ in queued) and self._is_process_running(
                ["qjackctl", "qjackctl6"]
            ):
                QMessageBox.information(
                    self,
                    "Close QjackCtl First",
                    "Quit QjackCtl before applying QjackCtl RT.\n\n"
                    "QjackCtl rewrites its config on exit, which can undo changes.",
                )
                return False
            reset_ids = [kid for kid, action in queued if action == "reset"]
            if reset_ids:
                dependents = self._confirm_dependency_reset(reset_ids)
                if dependents is None:
                    return False
                if dependents:
                    for kid in dependents:
                        self._queued_actions[kid] = "reset"
                    self._save_queue()
                    self._update_queue_ui()
                    self._populate()
                    queued = [(kid, action) for kid, action in self._queued_actions.items() if kid in by_id]
                    if not queued:
                        return False
            titles = []
            for kid, action in queued:
                verb = "Apply" if action == "apply" else "Reset"
                titles.append(f"{verb}: {by_id[kid].title}")
            confirm = ConfirmDialog(titles, parent=self)
            confirm.exec()
            if not confirm.ok:
                return False

            _get_gui_logger().info(
                "apply queue start reboot_after=%s actions=%s",
                reboot_after,
                ",".join(f"{kid}:{action}" for kid, action in queued),
            )

            self._queue_needs_reboot = reboot_after
            self._queue_busy = True
            self._queue_inflight = list(queued)
            for kid, _ in queued:
                self._busy_knobs.add(kid)
                self._knob_statuses[kid] = "running"
            self._update_queue_ui()
            self._populate()

            apply_ids = [kid for kid, action in queued if action == "apply"]
            reset_ids = [kid for kid, action in queued if action == "reset"]
            apply_root_ids = [kid for kid in apply_ids if by_id[kid].requires_root]
            apply_user_ids = [kid for kid in apply_ids if not by_id[kid].requires_root]
            reset_root_ids = [kid for kid in reset_ids if by_id[kid].requires_root]
            reset_user_ids = [kid for kid in reset_ids if not by_id[kid].requires_root]

            def _task():
                payload: dict[str, object] = {
                    "apply_user": None,
                    "apply_root": None,
                    "reset_user": None,
                    "reset_root": None,
                }
                errors: list[str] = []
                if apply_user_ids:
                    try:
                        if "qjackctl_server_prefix_rt" in apply_user_ids:
                            self._prime_qjackctl_preset()
                        payload["apply_user"] = _run_worker_apply_user(apply_user_ids)
                    except Exception as e:
                        errors.append(str(e))
                if apply_root_ids:
                    try:
                        payload["apply_root"] = _run_worker_apply_pkexec(apply_root_ids)
                    except Exception as e:
                        errors.append(str(e))
                if reset_user_ids:
                    try:
                        result = _run_worker_restore_many_user(reset_user_ids)
                        payload["reset_user"] = result
                        if not result.get("success", True):
                            errs = result.get("errors") or []
                            if not errs:
                                errs = [result.get("error") or "restore failed"]
                            errors.extend(errs)
                    except Exception as e:
                        errors.append(str(e))
                if reset_root_ids:
                    try:
                        result = _run_worker_restore_many_pkexec(reset_root_ids)
                        payload["reset_root"] = result
                        if not result.get("success", True):
                            errs = result.get("errors") or []
                            if not errs:
                                errs = [result.get("error") or "restore failed"]
                            errors.extend(errs)
                    except Exception as e:
                        errors.append(str(e))
                if errors:
                    if _PKEXEC_CANCELLED in errors and len(errors) == 1:
                        return False, payload, _PKEXEC_CANCELLED
                    return False, payload, "\n".join(errors)
                return True, payload, ""

            worker = QueueTaskWorker(_task, parent=self)
            worker.finished.connect(self._on_apply_queue_finished)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()
            return True

        def _on_reset_knob(self, knob_id: str, requires_root: bool) -> None:
            """Reset a single knob to original."""
            def _task():
                success, msg = self._restore_knob_internal(knob_id, requires_root)
                return success, {"message": msg}, msg

            self._run_knob_task(knob_id, "reset", _task)

        def _run_knob_task(self, knob_id: str, action: str, fn) -> None:
            if knob_id in self._busy_knobs:
                return
            self._busy_knobs.add(knob_id)
            self._knob_statuses[knob_id] = "running"
            self._populate()

            worker = KnobTaskWorker(knob_id, action, fn, parent=self)
            worker.finished.connect(self._on_knob_task_finished)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _prune_task_threads(self) -> None:
            self._task_threads = [
                w for w in self._task_threads
                if isValid(w) and w.isRunning()
            ]

        def _handle_apply_followups(self, result: dict) -> None:
            warnings = result.get("warnings") or []
            if warnings:
                QMessageBox.warning(
                    self,
                    "Apply Warning",
                    "\n\n".join(str(w) for w in warnings),
                )
            followups = result.get("followups") or []
            if followups:
                label = followups[0].get("label", "Run bootloader update")
                cmd = followups[0].get("cmd", [])
                if isinstance(cmd, list) and cmd:
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Warning)
                    box.setWindowTitle("Bootloader Update Required")
                    box.setText(
                        "Kernel cmdline changes need a bootloader update to take effect."
                    )
                    box.setInformativeText(label)
                    run_btn = box.addButton("Run update now", QMessageBox.AcceptRole)
                    box.addButton("Later", QMessageBox.RejectRole)
                    box.exec()
                    if box.clickedButton() == run_btn:
                        update_cmd = [str(x) for x in cmd]

                        def _task() -> tuple[bool, object, str]:
                            try:
                                _run_pkexec_command(update_cmd)
                            except Exception as e:
                                return False, {"cmd": update_cmd}, str(e)
                            return True, {"cmd": update_cmd}, ""

                        worker = QueueTaskWorker(_task, parent=self)

                        def _on_done(success: bool, payload: object, message: str) -> None:
                            if not success and message != _PKEXEC_CANCELLED:
                                QMessageBox.warning(self, "Update Failed", message or "Update failed")

                        worker.finished.connect(_on_done)
                        worker.finished.connect(worker.deleteLater)
                        self._task_threads.append(worker)
                        worker.start()

        def _on_knob_task_finished(self, knob_id: str, action: str, success: bool, payload: object, message: str) -> None:
            self._busy_knobs.discard(knob_id)
            self._prune_task_threads()

            if success and action == "apply":
                try:
                    if isinstance(payload, dict):
                        result = payload.get("result", {})
                        if payload.get("requires_root"):
                            self.state["last_root_txid"] = result.get("txid")
                        else:
                            self.state["last_user_txid"] = result.get("txid")
                        save_state(self.state)
                except Exception:
                    pass
                if isinstance(payload, dict):
                    self._handle_apply_followups(payload.get("result", {}))

            if not success:
                if message == _PKEXEC_CANCELLED:
                    self._queue_needs_reboot = False
                    self._refresh_statuses()
                    self._populate()
                    _get_gui_logger().info("apply queue cancelled")
                    return
                if action == "reset" and (_is_no_transaction_error(message) or _is_force_reset_error(message)):
                    reason = "reset_no_effect" if _is_force_reset_error(message) else None
                    if self._confirm_force_reset(knob_id, reason=reason):
                        self._run_force_reset(knob_id)
                    else:
                        self._refresh_statuses()
                        self._populate()
                    return
                if action == "apply":
                    _get_gui_logger().error("apply knob failed id=%s error=%s", knob_id, message)
                    QMessageBox.critical(self, "Failed", message or "Unknown error")
                else:
                    QMessageBox.warning(self, "Reset Failed", message or "Unknown error")

            self._refresh_statuses()
            if success and action == "apply" and knob_id == "rt_limits_audio_group":
                if not self._rt_limits_active():
                    self._knob_statuses["rt_limits_audio_group"] = "pending_reboot"
                    self._update_reboot_banner()
                    QMessageBox.information(
                        self,
                        "Reboot Required",
                        "RT Limits were applied, but your session does not have them yet.\n\n"
                        "Log out/in or reboot to activate.",
                    )
            self._populate()

        def _on_apply_queue_finished(self, success: bool, payload: object, message: str) -> None:
            inflight = [kid for kid, _ in self._queue_inflight]
            self._queue_inflight = []
            for kid in inflight:
                self._busy_knobs.discard(kid)
            self._queue_busy = False
            self._prune_task_threads()

            applied_ids: set[str] = set()
            restored_ids: set[str] = set()
            user_result: dict[str, Any] = {}
            root_result: dict[str, Any] = {}
            reset_user: dict[str, Any] = {}
            reset_root: dict[str, Any] = {}
            if isinstance(payload, dict):
                user_result = payload.get("apply_user") or {}
                root_result = payload.get("apply_root") or {}
                reset_user = payload.get("reset_user") or {}
                reset_root = payload.get("reset_root") or {}
                if user_result:
                    try:
                        self.state["last_user_txid"] = user_result.get("txid")
                        applied_ids.update(user_result.get("applied") or [])
                    except Exception:
                        pass
                if root_result:
                    try:
                        self.state["last_root_txid"] = root_result.get("txid")
                        applied_ids.update(root_result.get("applied") or [])
                    except Exception:
                        pass
                if reset_user:
                    restored_ids.update(reset_user.get("restored") or [])
                if reset_root:
                    restored_ids.update(reset_root.get("restored") or [])
                if user_result or root_result:
                    try:
                        save_state(self.state)
                    except Exception:
                        pass
                if root_result:
                    self._handle_apply_followups(root_result)

            if not success:
                if message == _PKEXEC_CANCELLED:
                    self._queue_needs_reboot = False
                    self._refresh_statuses()
                    self._populate()
                    return

                missing_user, other_user = self._collect_no_transaction_knobs(reset_user)
                missing_root, other_root = self._collect_no_transaction_knobs(reset_root)
                missing_ids = list(dict.fromkeys(missing_user + missing_root))
                other_errors = other_user + other_root
                unsupported: list[str] = []

                if missing_ids:
                    _get_gui_logger().warning(
                        "apply queue missing transactions=%s",
                        ",".join(missing_ids),
                    )

                show_error = True
                if missing_ids and not other_errors:
                    show_error = False

                if show_error:
                    _get_gui_logger().error("apply queue failed error=%s", message)
                    QMessageBox.critical(self, "Failed", message or "Unknown error")

                if missing_ids:
                    supported = [kid for kid in missing_ids if self._force_reset_supported(kid)]
                    unsupported = [kid for kid in missing_ids if kid not in supported]
                    if supported:
                        _get_gui_logger().info(
                            "apply queue force reset prompt supported=%s",
                            ",".join(supported),
                        )
                    if supported and self._confirm_force_reset_many(supported):
                        _get_gui_logger().info(
                            "apply queue force reset accepted supported=%s",
                            ",".join(supported),
                        )
                        for kid in supported:
                            self._queued_actions.pop(kid, None)
                        self._save_queue()
                        self._update_queue_ui()
                        self._run_force_reset_many(supported)
                    elif supported:
                        _get_gui_logger().info("apply queue force reset cancelled")
                if unsupported:
                    _get_gui_logger().warning(
                        "apply queue force reset unsupported=%s",
                        ",".join(unsupported),
                    )
                    msg = (
                        "No transaction was recorded for:\n"
                        + "\n".join(unsupported)
                        + "\n\nForce reset is not supported for these knobs."
                    )
                    QMessageBox.warning(self, "Force reset unavailable", msg)
            else:
                _get_gui_logger().info(
                    "apply queue done applied=%s restored=%s",
                    ",".join(sorted(applied_ids)) or "-",
                    ",".join(sorted(restored_ids)) or "-",
                )
                if applied_ids or restored_ids:
                    pass

            queue_reboot = self._queue_needs_reboot
            self._queue_needs_reboot = False
            if applied_ids or restored_ids:
                updated = False
                for kid in list(self._queued_actions.keys()):
                    action = self._queued_actions.get(kid)
                    if action == "apply" and kid in applied_ids:
                        self._queued_actions.pop(kid, None)
                        updated = True
                    elif action == "reset" and kid in restored_ids:
                        self._queued_actions.pop(kid, None)
                        updated = True
                if updated:
                    self._save_queue()
            self._refresh_statuses()
            if "rt_limits_audio_group" in applied_ids and not self._rt_limits_active():
                self._knob_statuses["rt_limits_audio_group"] = "pending_reboot"
                self._update_reboot_banner()
                QMessageBox.information(
                    self,
                    "Reboot Required",
                    "RT Limits were applied, but your session does not have them yet.\n\n"
                    "Log out/in or reboot to activate.",
                )
            if success and queue_reboot:
                self._on_reboot_now(force=True)
            self._populate()

        def _confirm_force_reset(self, knob_id: str, *, reason: str | None = None) -> bool:
            k = next((k for k in self.registry if k.id == knob_id), None)
            if not k:
                return False
            if reason == "reset_no_effect":
                msg = (
                    "Reset did not revert this knob to defaults.\n\n"
                    "Force reset will attempt to revert the setting to system defaults "
                    "even if it was not applied by this app.\n\n"
                    "Continue?"
                )
            else:
                msg = (
                    "No transaction was recorded for this knob.\n\n"
                    "Force reset will attempt to revert the setting to system defaults "
                    "even if it was not applied by this app.\n\n"
                    "Continue?"
                )
            return QMessageBox.question(self, "Force reset", msg) == QMessageBox.Yes

        def _run_force_reset(self, knob_id: str) -> None:
            k = next((k for k in self.registry if k.id == knob_id), None)
            if not k:
                return

            def _task():
                if k.requires_root:
                    result = _run_worker_force_reset_pkexec(knob_id)
                else:
                    result = _run_worker_force_reset_user(knob_id)
                return True, {"result": result}, result.get("message", "")

            self._run_knob_task(knob_id, "force_reset", _task)

        def _force_reset_supported(self, knob_id: str) -> bool:
            k = next((k for k in self.registry if k.id == knob_id), None)
            if not k or not k.impl:
                return False
            return k.impl.kind in (
                "systemd_unit_toggle",
                "kernel_cmdline",
                "sysfs_glob_kv",
                "pam_limits_audio_group",
                "sysctl_conf",
                "udev_rule",
                "pipewire_conf",
                "rtirq_config",
                "user_service_mask",
                "baloo_disable",
            )

        def _collect_no_transaction_knobs(self, result: dict[str, Any]) -> tuple[list[str], list[str]]:
            no_tx: list[str] = []
            other_errors: list[str] = []
            if not isinstance(result, dict):
                return no_tx, other_errors

            results = result.get("results") or []
            for item in results:
                if not isinstance(item, dict):
                    continue
                knob_id = item.get("knob_id")
                errors: list[str] = []
                if item.get("error"):
                    errors.append(str(item["error"]))
                errors.extend([str(e) for e in item.get("errors") or []])
                if not errors:
                    continue
                if any(_is_no_transaction_error(e) or _is_force_reset_error(e) for e in errors):
                    if knob_id and knob_id not in no_tx:
                        no_tx.append(knob_id)
                    for err in errors:
                        if not (_is_no_transaction_error(err) or _is_force_reset_error(err)):
                            other_errors.append(err)
                else:
                    other_errors.extend(errors)

            for err in result.get("errors") or []:
                err_str = str(err)
                if _is_no_transaction_error(err_str) or _is_force_reset_error(err_str):
                    if ":" in err_str:
                        kid = err_str.split(":", 1)[0].strip()
                        if kid and kid not in no_tx:
                            no_tx.append(kid)
                else:
                    other_errors.append(err_str)

            return no_tx, other_errors

        def _confirm_force_reset_many(self, knob_ids: list[str]) -> bool:
            by_id = {k.id: k for k in self.registry}
            names = []
            for kid in knob_ids:
                k = by_id.get(kid)
                if k:
                    names.append(f"{k.title} ({k.id})")
                else:
                    names.append(kid)
            msg = (
                "Force reset recommended for:\n\n"
                + "\n".join(names)
                + "\n\nForce reset will attempt to revert the settings to system defaults "
                "even if they were not applied by this app or if reset did not change them.\n\n"
                "Continue?"
            )
            return QMessageBox.question(self, "Force reset", msg) == QMessageBox.Yes

        def _run_force_reset_many(self, knob_ids: list[str]) -> None:
            by_id = {k.id: k for k in self.registry}
            for kid in knob_ids:
                self._busy_knobs.add(kid)
                self._knob_statuses[kid] = "running"
            self._populate()
            _get_gui_logger().info("force reset start knobs=%s", ",".join(knob_ids))

            def _task():
                results = []
                errors: list[str] = []
                for kid in knob_ids:
                    k = by_id.get(kid)
                    if not k:
                        errors.append(f"{kid}: unknown knob")
                        continue
                    try:
                        if k.requires_root:
                            result = _run_worker_force_reset_pkexec(kid)
                        else:
                            result = _run_worker_force_reset_user(kid)
                        results.append(result)
                        if not result.get("success", True):
                            msg = result.get("message") or result.get("error") or "force reset failed"
                            errors.append(f"{kid}: {msg}")
                    except Exception as e:
                        errors.append(f"{kid}: {e}")
                return len(errors) == 0, {"results": results, "errors": errors}, "\n".join(errors)

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                for kid in knob_ids:
                    self._busy_knobs.discard(kid)
                self._refresh_statuses()
                self._populate()
                if success:
                    _get_gui_logger().info("force reset done knobs=%s", ",".join(knob_ids))
                else:
                    _get_gui_logger().error("force reset failed error=%s", message)
                if not success:
                    QMessageBox.warning(
                        self,
                        "Force reset incomplete",
                        message or "Some knobs failed to reset.",
                    )

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _restore_knob_internal(self, knob_id: str, requires_root: bool) -> tuple[bool, str]:
            """Restore a single knob to its original state."""
            if requires_root:
                try:
                    worker = _pick_root_worker_path()
                    argv = ["pkexec", worker, "restore-knob", knob_id]
                    p = subprocess.run(argv, text=True, capture_output=True)
                    if not p.stdout.strip():
                        err = p.stderr.strip() or "Unknown error"
                        if _is_pkexec_cancel(err):
                            return False, _PKEXEC_CANCELLED
                        return False, err
                    try:
                        result = json.loads(p.stdout)
                    except Exception:
                        err = p.stderr.strip() or p.stdout.strip() or "Unknown error"
                        if _is_pkexec_cancel(err):
                            return False, _PKEXEC_CANCELLED
                        return False, err
                    if result.get("success"):
                        return True, f"Reset {knob_id}"
                    errors = result.get("errors") or []
                    if errors:
                        return False, "\n".join(str(e) for e in errors)
                    return False, result.get("error", "Unknown error")
                except Exception as e:
                    return False, str(e)
            else:
                try:
                    argv = [
                        sys.executable, "-m", "audioknob_gui.worker.cli",
                        "restore-knob", knob_id
                    ]
                    p = subprocess.run(argv, text=True, capture_output=True)
                    if not p.stdout.strip():
                        err = p.stderr.strip() or "Unknown error"
                        if _is_pkexec_cancel(err):
                            return False, _PKEXEC_CANCELLED
                        return False, err
                    try:
                        result = json.loads(p.stdout)
                    except Exception:
                        err = p.stderr.strip() or p.stdout.strip() or "Unknown error"
                        if _is_pkexec_cancel(err):
                            return False, _PKEXEC_CANCELLED
                        return False, err
                    if result.get("success"):
                        return True, f"Reset {knob_id}"
                    errors = result.get("errors") or []
                    if errors:
                        return False, "\n".join(str(e) for e in errors)
                    return False, result.get("error", "Unknown error")
                except Exception as e:
                    return False, str(e)
        
        def _restore_knob(self, knob_id: str, requires_root: bool) -> tuple[bool, str]:
            """Legacy wrapper for batch restore."""
            return self._restore_knob_internal(knob_id, requires_root)

        def on_reset_defaults(self) -> None:
            """Reset ALL audioknob-gui changes to system defaults."""
            # First, show what will be reset
            _get_gui_logger().info("reset defaults requested")
            try:
                argv = [
                    sys.executable,
                    "-m",
                    "audioknob_gui.worker.cli",
                    "list-pending",
                ]
                p = subprocess.run(argv, text=True, capture_output=True)
                if p.returncode != 0:
                    raise RuntimeError(p.stderr.strip() or "list-pending failed")
                changes = json.loads(p.stdout)
            except Exception as e:
                QMessageBox.critical(self, "Failed", f"Could not list changes: {e}")
                return

            file_count = changes.get("count", 0)
            effects_count = changes.get("effects_count", 0)
            has_root_effects = changes.get("has_root_effects", False)
            has_user_effects = changes.get("has_user_effects", False)
            
            # Check if there's anything to reset (files OR effects)
            if file_count == 0 and effects_count == 0:
                QMessageBox.information(
                    self,
                    "Nothing to reset",
                    "No audioknob-gui changes found.\n\n"
                    "Either no changes have been applied, or they've already been reset."
                )
                return

            # Show summary and confirm
            files = changes.get("files", [])
            effects = changes.get("effects", [])
            summary_lines = []
            
            # List files
            for f in files[:10]:  # Show first 10
                strategy = f.get("reset_strategy", "backup")
                pkg = f.get("package", "")
                line = f"• {f['path']}"
                if strategy == "delete":
                    line += " [will delete]"
                elif strategy == "package" and pkg:
                    line += f" [restore from {pkg}]"
                else:
                    line += " [restore backup]"
                summary_lines.append(line)
            if len(files) > 10:
                summary_lines.append(f"... and {len(files) - 10} more files")
            
            # List effects
            if effects:
                summary_lines.append("")
                summary_lines.append("Effects to restore:")
                effect_kinds = {}
                for e in effects:
                    kind = e.get("kind", "unknown")
                    effect_kinds[kind] = effect_kinds.get(kind, 0) + 1
                for kind, count in effect_kinds.items():
                    if kind == "sysfs_write":
                        summary_lines.append(f"• {count} sysfs value(s)")
                    elif kind == "systemd_unit_toggle":
                        summary_lines.append(f"• {count} systemd service(s)")
                    elif kind == "user_service_mask":
                        summary_lines.append(f"• {count} user service mask(s)")
                    elif kind == "baloo_disable":
                        summary_lines.append(f"• Baloo indexer")
                    elif kind == "kernel_cmdline":
                        summary_lines.append(f"• {count} kernel cmdline change(s)")
                    else:
                        summary_lines.append(f"• {count} {kind} effect(s)")

            confirm_dialog = QDialog(self)
            confirm_dialog.setWindowTitle("Reset to System Defaults")
            confirm_dialog.resize(600, 350)
            layout = QVBoxLayout(confirm_dialog)

            total_changes = file_count + effects_count
            layout.addWidget(QLabel(
                f"<b>Reset {total_changes} change(s) to system defaults?</b><br/><br/>"
                "<i>You'll be prompted for your password if root access is needed.</i>"
            ))

            text_widget = QTextEdit()
            text_widget.setReadOnly(True)
            text_widget.setPlainText("\n".join(summary_lines))
            layout.addWidget(text_widget)

            btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            layout.addWidget(btns)

            confirmed = [False]

            def on_ok():
                confirmed[0] = True
                confirm_dialog.accept()

            btns.accepted.connect(on_ok)
            btns.rejected.connect(confirm_dialog.reject)

            confirm_dialog.exec()
            if not confirmed[0]:
                return

            # Execute reset in two phases: user-scope first, then root-scope
            root_files = [f for f in files if f.get("scope") == "root"]
            needs_root = bool(root_files) or has_root_effects

            self.btn_reset.setEnabled(False)
            self.btn_reset.setText("Working...")

            def _task() -> tuple[bool, object, str]:
                results_text: list[str] = []
                errors: list[str] = []
                needs_reboot = False

                # Phase 1: User-scope reset (no pkexec needed)
                try:
                    argv = [
                        sys.executable,
                        "-m",
                        "audioknob_gui.worker.cli",
                        "reset-defaults",
                        "--scope", "user",
                    ]
                    p = subprocess.run(argv, text=True, capture_output=True, timeout=120)
                    if p.returncode != 0:
                        err_msg = p.stderr.strip() or p.stdout.strip() or f"Exit code {p.returncode}"
                        errors.append(f"User reset failed: {err_msg}")
                    elif p.stdout:
                        try:
                            result = json.loads(p.stdout)
                            if result.get("reset_count", 0) > 0:
                                results_text.append(f"Reset {result['reset_count']} user file(s)")
                            errors.extend(result.get("errors", []))
                            needs_reboot = bool(result.get("needs_reboot", False)) or needs_reboot
                        except json.JSONDecodeError as e:
                            errors.append(f"User reset: invalid response: {e}")
                except Exception as e:
                    errors.append(f"User reset failed: {e}")

                # Phase 2: Root-scope reset (needs pkexec)
                if needs_root:
                    try:
                        worker = _pick_root_worker_path()
                        argv = [
                            "pkexec",
                            worker,
                            "reset-defaults",
                            "--scope", "root",
                        ]
                        p = subprocess.run(argv, text=True, capture_output=True, timeout=300)
                        if p.returncode != 0:
                            err_msg = p.stderr.strip() or p.stdout.strip() or f"Exit code {p.returncode}"
                            errors.append(f"Root reset failed: {err_msg}")
                        elif p.stdout:
                            try:
                                result = json.loads(p.stdout)
                                if result.get("reset_count", 0) > 0:
                                    results_text.append(f"Reset {result['reset_count']} system file(s)")
                                errors.extend(result.get("errors", []))
                                needs_reboot = bool(result.get("needs_reboot", False)) or needs_reboot
                            except json.JSONDecodeError as e:
                                errors.append(f"Root reset: invalid response: {e}")
                    except Exception as e:
                        errors.append(f"Root reset failed: {e}")

                return True, {"results_text": results_text, "errors": errors, "needs_reboot": needs_reboot}, ""

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                self.btn_reset.setEnabled(True)
                self.btn_reset.setText("Reset All")

                results_text: list[str] = []
                errors: list[str] = []
                needs_reboot = False
                if isinstance(payload, dict):
                    results_text = payload.get("results_text") or []
                    errors = payload.get("errors") or []
                    needs_reboot = bool(payload.get("needs_reboot", False))
                elif message:
                    errors = [message]

                # Clear all stored txids
                self.state["last_txid"] = None
                self.state["last_user_txid"] = None
                self.state["last_root_txid"] = None
                self._queued_actions = {}
                self.state["queued_actions"] = {}
                save_state(self.state)
                self._update_queue_ui()

                # Refresh the UI to show updated status
                self._refresh_statuses()
                self._populate()

                # Show results
                if errors:
                    _get_gui_logger().error("reset defaults failed error=%s", "; ".join(errors))
                    reboot_note = "\n\nReboot required to finish kernel cmdline resets." if needs_reboot else ""
                    QMessageBox.warning(
                        self,
                        "Reset completed with errors",
                        "\n".join(results_text) + "\n\nErrors:\n" + "\n".join(errors[:5]) + reboot_note
                    )
                else:
                    _get_gui_logger().info("reset defaults done")
                    reboot_note = "\n\nReboot required to finish kernel cmdline resets." if needs_reboot else ""
                    QMessageBox.information(
                        self,
                        "Reset complete",
                        "All audioknob-gui changes have been reset to system defaults.\n\n"
                        + "\n".join(results_text)
                        + reboot_note
                    )

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

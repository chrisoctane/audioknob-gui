from __future__ import annotations

import html as html_lib
import json
import logging
import os
import subprocess
import sys
import shutil
import glob
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        "pipewire_quantum": None,  # int (32..1024) or None
        "pipewire_sample_rate": None,  # int (44100/48000/88200/96000/192000) or None
        "jitter_test_last": None,  # dict payload from last run or None
        "system_profile": None,  # dict from startup scan or None
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
        if "pipewire_quantum" not in data:
            data["pipewire_quantum"] = None
        if "pipewire_sample_rate" not in data:
            data["pipewire_sample_rate"] = None
        if "jitter_test_last" not in data:
            data["jitter_test_last"] = None
        if "system_profile" not in data:
            data["system_profile"] = None
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
        if data.get("system_profile") is not None and not isinstance(data.get("system_profile"), dict):
            data["system_profile"] = None
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
            QGridLayout,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSizePolicy,
            QSlider,
            QSpinBox,
            QTableWidget,
            QTableWidgetItem,
            QTextEdit,
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
        def __init__(self, *, cpu_count: int, selected: set[int], parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Configure CPU cores for JACK")
            self.resize(520, 320)

            self._cpu_count = max(1, int(cpu_count))
            self._checks: list[QCheckBox] = []

            root = QVBoxLayout(self)
            root.addWidget(QLabel("Select CPU cores to pin JACK to (taskset -c)."))
            root.addWidget(QLabel("Tip: cores 0-1 are often busiest (IRQs/system tasks)."))

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

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            from PySide6.QtCore import QTimer
            self.setWindowTitle("audioknob-gui")
            self.resize(980, 640)

            self.state = load_state()
            self.registry = load_registry(_registry_path())
            self._ensure_system_profile()
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
            self.reboot_banner.setVisible(False)
            top.addWidget(self.reboot_banner)

            self.reboot_toggle = QCheckBox("Enable reboot-required changes")
            self.reboot_toggle.setChecked(bool(self.state.get("enable_reboot_knobs", False)))
            self.reboot_toggle.setToolTip("Unlock knobs that require a reboot/log-out to take effect")
            self.reboot_toggle.toggled.connect(self._on_reboot_toggle)

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

            self.btn_logs = QPushButton("Logs")
            self.btn_logs.setToolTip("Open logs for copy/paste")
            self.btn_logs.clicked.connect(self._on_show_logs)
            top.addWidget(self.btn_logs)

            self.btn_reset = QPushButton("Reset All")
            self.btn_reset.setToolTip("Reset all changes to system defaults")
            top.addWidget(self.btn_reset)
            root.addLayout(top)

            self.table = QTableWidget(0, 8)
            self.table.setHorizontalHeaderLabels(["Info", "Knob", "Action", "Config", "Status", "Check", "Category", "Risk"])
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
            # Make every column user-resizable (Interactive). We also set reasonable defaults.
            # NOTE: ResizeToContents does NOT reliably account for cell widgets (buttons/combos),
            # which causes text clipping like "Apply" -> "Annlv".
            for c in range(8):
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
            self._task_threads: list[QThread] = []
            self._install_busy = False
            self._status_busy = False
            self._user_groups: set[str] = set()
            self._refresh_user_groups()
            self._refresh_statuses()
            self._populate()
            QTimer.singleShot(0, self._apply_window_constraints)

            self.btn_reset.clicked.connect(self.on_reset_defaults)
            self.table.cellEntered.connect(self._on_row_hover)
            self.table.viewport().installEventFilter(self)

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
                p = subprocess.run(
                    ["ps", "-e", "-o", "comm="],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                names = set(p.stdout.split())
                if {"gnome-shell", "gnome-session-binary"} & names:
                    return "gnome"
                if {"plasmashell", "ksmserver", "ksplashqml"} & names:
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
            return all(check_command_available(cmd) for cmd in k.requires_commands)

        def _knob_missing_commands(self, k) -> list[str]:
            """Return list of missing commands for this knob."""
            if not k.requires_commands:
                return []
            from audioknob_gui.platform.packages import check_command_available
            return [cmd for cmd in k.requires_commands if not check_command_available(cmd)]

        def _collect_log_text(self) -> str:
            gui_log = _state_path().parent / "logs" / "gui.log"
            user_worker_log = Path(_worker_log_path(is_root=False))
            root_worker_log = Path(_worker_log_path(is_root=True))

            entries: list[tuple[str, Path]] = [
                ("GUI log", gui_log),
                ("Worker log (user)", user_worker_log),
                ("Worker log (root)", root_worker_log),
            ]

            lines: list[str] = []
            for label, path in entries:
                lines.append(f"=== {label} ===")
                lines.append(f"Path: {path}")

                if not path.exists():
                    lines.append("[not found]")
                    lines.append("")
                    continue

                if label.endswith("(root)") and not os.access(path, os.R_OK):
                    lines.append("[not readable: requires root]")
                    lines.append("")
                    continue

                try:
                    content = path.read_text(encoding="utf-8")
                except Exception as exc:
                    lines.append(f"[error reading log: {exc}]")
                    lines.append("")
                    continue

                if content.strip():
                    lines.append(content.rstrip("\n"))
                else:
                    lines.append("[empty]")
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
            clear_btn.clicked.connect(lambda: self._on_clear_logs(text))
            btn_row.addWidget(clear_btn)
            btn_row.addStretch(1)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

            dialog.exec()

        def _on_clear_logs(self, text: QTextEdit | None = None) -> None:
            reply = QMessageBox.question(
                self,
                "Clear Logs",
                "Clear GUI, user worker, and root worker logs?\n\nRoot worker log requires pkexec.",
                QMessageBox.Ok | QMessageBox.Cancel,
            )
            if reply != QMessageBox.Ok:
                return

            gui_log = _state_path().parent / "logs" / "gui.log"
            user_worker_log = Path(_worker_log_path(is_root=False))
            root_worker_log = Path(_worker_log_path(is_root=True))

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

            _log_gui_audit(
                "clear-logs",
                {
                    "cleared": cleared,
                    "errors": errors,
                    "root_log": str(root_worker_log) if root_worker_log.exists() else None,
                },
            )

            if errors:
                details = "\n".join(errors)
                QMessageBox.warning(self, "Logs Cleared (with warnings)", details)
            else:
                QMessageBox.information(self, "Logs Cleared", "Logs cleared successfully.")

            if text is not None:
                text.setPlainText(self._collect_log_text())

        def _ensure_system_profile(self) -> None:
            profile = self.state.get("system_profile")
            schema_ok = isinstance(profile, dict) and profile.get("schema") == 1
            prev_distro = profile.get("distro_id") if schema_ok else None
            knob_paths = profile.get("knob_paths") if schema_ok else None
            expected_ids = {k.id for k in self.registry}
            paths_ok = isinstance(knob_paths, dict) and expected_ids.issubset(knob_paths.keys())
            try:
                from audioknob_gui.worker.ops import detect_distro, scan_system_profile
                current_distro = detect_distro().distro_id
                if not schema_ok or prev_distro != current_distro or not paths_ok:
                    self.state["system_profile"] = scan_system_profile(self.registry)
                    save_state(self.state)
            except Exception as exc:
                _get_gui_logger().warning("System profile scan failed: %s", exc)

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
                if action == "reset" and status in ("not_applied", "not_applicable"):
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
            self.btn_apply_queue.setEnabled(enabled)
            self.btn_apply_queue_reboot.setEnabled(enabled and self._queue_requires_reboot())

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

        def _qjackctl_has_preset(self, path: Path) -> bool:
            from audioknob_gui.core.qjackctl import read_config

            if not path.exists():
                return False
            try:
                cfg = read_config(path)
            except Exception:
                return False
            return bool(cfg.def_preset)

        def _prime_qjackctl_preset(self) -> None:
            logger = _get_gui_logger()
            path = Path("~/.config/rncbc.org/QjackCtl.conf").expanduser()
            if self._qjackctl_has_preset(path):
                return

            exe = shutil.which("qjackctl") or shutil.which("qjackctl6")
            if exe:
                env = os.environ.copy()
                if "QT_QPA_PLATFORM" not in env:
                    env["QT_QPA_PLATFORM"] = "minimal"
                cmd = [exe, "-s"]
                try:
                    p = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=env,
                    )
                except Exception as e:
                    logger.info("qjackctl launch failed error=%s", e)
                else:
                    try:
                        deadline = time.monotonic() + 5.0
                        while time.monotonic() < deadline:
                            if self._qjackctl_has_preset(path):
                                return
                            time.sleep(0.2)
                    finally:
                        try:
                            p.terminate()
                        except Exception:
                            pass
                        try:
                            p.wait(timeout=2)
                        except Exception:
                            try:
                                p.kill()
                            except Exception:
                                pass

                if self._qjackctl_has_preset(path):
                    return

            try:
                from audioknob_gui.core.qjackctl import read_config, write_config_with_server_update

                cfg = read_config(path)
                server_cmd = cfg.server_cmd or "jackd"
                server_prefix = cfg.server_prefix or ""
                write_config_with_server_update(path, "default", server_cmd, server_prefix=server_prefix)
                logger.info("created default qjackctl preset")
            except Exception as e:
                logger.info("failed to create default qjackctl preset error=%s", e)

        def _update_reboot_banner(self) -> None:
            needs_reboot = any(v == "pending_reboot" for v in self._knob_statuses.values())
            self._needs_reboot = needs_reboot
            # Banner text is now shown in the separator row, not the top bar.
            self.reboot_banner.setVisible(False)
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

        def _install_hover_tracking(self, widget: QWidget, row: int) -> None:
            widget.setProperty("hover_row", row)
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

        def _set_action_cell(self, row: int, widget: QWidget) -> None:
            self._install_hover_tracking(widget, row)
            self.table.setCellWidget(row, 2, widget)

        def _status_display(self, status: str) -> tuple[str, str]:
            """Return (display_text, color) for a status."""
            # Handle test results: "result:12 µs" → "12 µs"
            if status.startswith("result:"):
                return (status[7:], "#1976d2")  # Blue
            
            mapping = {
                "applied": ("✓ Applied", "#2e7d32"),      # Green
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
            reboot_gate_enabled = bool(self.state.get("enable_reboot_knobs", False))
            group_pending = self._knob_statuses.get("audio_group_membership") == "pending_reboot"
            desktop_kind = self._detect_desktop()

            reboot_knobs = [k for k in self.registry if k.requires_reboot]
            other_knobs = [k for k in self.registry if not k.requires_reboot]
            ordered: list[object] = []

            def _sort_key(k, col: int) -> tuple:
                status = self._knob_statuses.get(k.id, "unknown")
                status_order = {
                    "applied": 0,
                    "pending_reboot": 1,
                    "partial": 2,
                    "not_applied": 3,
                    "not_applicable": 4,
                    "unknown": 5,
                }
                risk_order = {"low": 0, "medium": 1, "high": 2}

                if col == 4:
                    return (status_order.get(status, 99), k.title.lower())
                if col == 6:
                    return (str(k.category).lower(), k.title.lower())
                if col == 7:
                    return (risk_order.get(str(k.risk_level), 99), k.title.lower())
                if col in (0, 1, 2, 3, 5):
                    return (k.title.lower(),)
                return (status_order.get(status, 99), k.title.lower())

            if self._sort_column is not None:
                col = int(self._sort_column)
                reboot_knobs = sorted(reboot_knobs, key=lambda k: _sort_key(k, col), reverse=self._sort_descending)
                other_knobs = sorted(other_knobs, key=lambda k: _sort_key(k, col), reverse=self._sort_descending)
            REBOOT_HEADER = object()
            SECTION_SEPARATOR = object()
            if reboot_knobs:
                ordered.append(REBOOT_HEADER)
                ordered.extend(reboot_knobs)
            if reboot_knobs and other_knobs:
                ordered.append(SECTION_SEPARATOR)
            ordered.extend(other_knobs)

            self.table.setRowCount(len(ordered))
            self._row_dim = [False] * len(ordered)

            for r, k in enumerate(ordered):
                if k is REBOOT_HEADER:
                    self.table.setSpan(r, 0, 1, 8)
                    header_widget = QWidget()
                    header_layout = QHBoxLayout(header_widget)
                    header_layout.setContentsMargins(8, 2, 8, 2)
                    header_layout.setSpacing(8)
                    header_layout.addWidget(self.reboot_toggle)
                    header_layout.addStretch(1)
                    self.table.setCellWidget(r, 0, header_widget)
                    for c in range(1, 8):
                        self.table.removeCellWidget(r, c)
                        self.table.setItem(r, c, QTableWidgetItem(""))
                    continue
                if k is SECTION_SEPARATOR:
                    sep = QTableWidgetItem("")
                    sep.setFlags(Qt.ItemIsEnabled)
                    sep.setForeground(QColor("#9e9e9e"))
                    sep.setTextAlignment(Qt.AlignCenter)
                    self.table.setSpan(r, 0, 1, 8)
                    self.table.setItem(r, 0, sep)
                    for c in range(1, 8):
                        self.table.removeCellWidget(r, c)
                        self.table.setItem(r, c, QTableWidgetItem(""))
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
                locked_bg = QColor("#2f2f2f")
                locked_fg = QColor("#7a7a7a")
                locked_style = (
                    "QPushButton { background-color: #2f2f2f; color: #7a7a7a; border: 1px solid #3a3a3a; }"
                    "QPushButton:hover { background-color: #2f2f2f; color: #7a7a7a; border: 1px solid #3a3a3a; }"
                    "QPushButton:pressed { background-color: #2f2f2f; color: #7a7a7a; border: 1px solid #3a3a3a; }"
                )

                # Check requirements
                group_ok = self._knob_group_ok(k)
                group_pending_lock = bool(k.requires_groups) and group_pending
                if group_pending_lock:
                    group_ok = False
                commands_ok = self._knob_commands_ok(k)
                missing_cmds = self._knob_missing_commands(k)
                reboot_gate_lock = bool(k.requires_reboot) and not reboot_gate_enabled and status not in ("applied", "pending_reboot")
                reboot_dep_lock = (not reboot_gate_enabled) and bool(k.requires_groups)
                locked = not group_ok or not commands_ok or reboot_gate_lock or reboot_dep_lock
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

                # Column 4: Status (with color)
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
                if row_dim:
                    status_item.setBackground(locked_bg)
                self.table.setItem(r, 4, status_item)

                # Column 6: Category
                cat_item = QTableWidgetItem(str(k.category))
                if row_dim:
                    cat_item.setForeground(locked_fg)
                    cat_item.setBackground(locked_bg)
                self.table.setItem(r, 6, cat_item)

                # Column 7: Risk
                risk_item = QTableWidgetItem(str(k.risk_level))
                if row_dim:
                    risk_item.setForeground(locked_fg)
                    risk_item.setBackground(locked_bg)
                self.table.setItem(r, 7, risk_item)

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
                    cfg_btn.setToolTip("Configure CPU cores for taskset")
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
                if k.id not in ("pipewire_quantum", "pipewire_sample_rate", "qjackctl_server_prefix_rt"):
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

                # Column 5: Status check
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
                self.table.setCellWidget(r, 5, check_btn)
            
            # Keep built-in sorting disabled; we handle per-section sorting.
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
                "⟳ Reboot",
                "◐ Partial",
                "N/A",
                "⏳ Updating",
                "—",
            ]
            status_width = max([_w("Status")] + [_w(t) for t in status_texts])

            category_texts = [str(k.category) for k in self.registry] + ["Category"]
            category_width = max(_w(t) for t in category_texts)

            risk_texts = [str(k.risk_level) for k in self.registry] + ["Risk"]
            risk_width = max(_w(t) for t in risk_texts)

            action_texts = ["Apply", "Reset", "Install", "View", "Test", "Scan", "Join", "Leave", "Action"]
            action_width = max(_w(t, pad=40) for t in action_texts)
            action_width = max(action_width, 80)

            config_texts = ["Config", "Cores", "44100 Hz", "192000 Hz", "512", "1024"]
            config_width = max(_w(t, pad=44) for t in config_texts)
            config_width = max(config_width, 128)

            check_texts = ["Check", "Status"]
            check_width = max(_w(t, pad=40) for t in check_texts)
            check_width = max(check_width, 96)

            self._min_column_widths = {
                0: 32,
                2: action_width,
                3: config_width,
                5: check_width,
            }

            self.table.setColumnWidth(0, 32)  # Info button
            self.table.setColumnWidth(1, knob_width)
            self.table.setColumnWidth(2, action_width)
            self.table.setColumnWidth(3, config_width)
            self.table.setColumnWidth(4, status_width)
            self.table.setColumnWidth(5, check_width)
            self.table.setColumnWidth(6, category_width)
            self.table.setColumnWidth(7, risk_width)
            self._enforce_min_column_widths()

        def _apply_window_constraints(self) -> None:
            """Limit window growth to the content size (bounded by screen)."""
            try:
                from PySide6.QtCore import QTimer
                from PySide6.QtGui import QGuiApplication

                header_w = self.table.horizontalHeader().length()
                header_h = self.table.verticalHeader().length()
                if header_w <= 0 or header_h <= 0:
                    QTimer.singleShot(0, self._apply_window_constraints)
                    return

                table_width = header_w + self.table.verticalHeader().width() + self.table.frameWidth() * 2
                table_height = header_h + self.table.horizontalHeader().height() + self.table.frameWidth() * 2

                layout = self.centralWidget().layout() if self.centralWidget() else None
                margins = layout.contentsMargins() if layout else None
                extra_w = (margins.left() + margins.right()) if margins else 16
                extra_h = (margins.top() + margins.bottom()) if margins else 16
                spacing = layout.spacing() if layout else 8

                header_hint_w = self.header_layout.sizeHint().width() if hasattr(self, "header_layout") else 0
                header_hint_h = self.header_layout.sizeHint().height() if hasattr(self, "header_layout") else 0

                pad = 20
                full_w = max(table_width, header_hint_w) + extra_w + (pad * 2)
                full_h = header_hint_h + spacing + table_height + extra_h + (pad * 2)

                vscroll_w = self.table.verticalScrollBar().sizeHint().width()
                hscroll_h = self.table.horizontalScrollBar().sizeHint().height()
                need_vscroll = self.table.verticalScrollBar().isVisible()
                need_hscroll = self.table.horizontalScrollBar().isVisible()
                if not need_vscroll:
                    need_vscroll = table_height > self.table.viewport().height()
                if not need_hscroll:
                    need_hscroll = table_width > self.table.viewport().width()
                if need_vscroll:
                    full_w += vscroll_w
                if need_hscroll:
                    full_h += hscroll_h

                screen = QGuiApplication.primaryScreen()
                avail = screen.availableGeometry() if screen else None
                max_w = full_w
                max_h = full_h
                # Avoid shrinking the window below its current size.
                max_w = max(max_w, self.width())
                max_h = max(max_h, self.height())
                if avail:
                    max_w = min(max_w, avail.width())
                    max_h = min(max_h, avail.height())

                self.setMaximumSize(max_w, max_h)
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
                    background-color: #2b2b2b;
                    color: #e0e0e0;
                }
                QTableWidget {
                    background-color: #333333;
                    alternate-background-color: #3a3a3a;
                    gridline-color: #444444;
                    border: 1px solid #444444;
                }
                QTableWidget::item {
                    padding: 4px;
                }
                QTableWidget::item:selected {
                    background-color: #46525d;
                    color: #e0e0e0;
                }
                QHeaderView::section {
                    background-color: #404040;
                    color: #e0e0e0;
                    padding: 6px;
                    border: none;
                    border-bottom: 1px solid #555555;
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

        def _on_reboot_now(self) -> None:
            if not getattr(self, "_needs_reboot", False):
                return
            msg = (
                "Restart now to apply pending changes?\n\n"
                "Unsaved work in other apps may be lost."
            )
            if QMessageBox.question(self, "Reboot", msg) != QMessageBox.Yes:
                return
            try:
                _run_pkexec_command(["systemctl", "reboot"])
            except RuntimeError as e:
                if str(e) != _PKEXEC_CANCELLED:
                    QMessageBox.warning(self, "Reboot Failed", str(e))

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
            if obj is self.table.viewport() and event.type() == QEvent.Leave:
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

        def on_configure_knob(self, knob_id: str) -> None:
            if knob_id == "qjackctl_server_prefix_rt":
                from audioknob_gui.platform.detect import get_cpu_count

                cpu_count = get_cpu_count()
                selected = set(self._qjackctl_cpu_cores_from_state() or [])
                d = CpuCoreDialog(cpu_count=cpu_count, selected=selected, parent=self)
                if d.exec() != QDialog.Accepted:
                    return

                chosen = d.selected_cores()
                # Empty selection means "no pinning" (remove taskset prefix).
                # None (unset) means "don't override existing pinning".
                self.state["qjackctl_cpu_cores"] = chosen
                save_state(self.state)
                QMessageBox.information(
                    self,
                    "Saved",
                    "Saved CPU core selection for QjackCtl."
                    + (f" Cores: {','.join(map(str, chosen))}" if chosen else " (no pinning)"),
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
                    # Status column is col 4 (col 1 is knob title).
                    self.table.setItem(r, 4, status_item)
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

            def _shell_single_quote(value: str) -> str:
                return "'" + value.replace("'", "'\"'\"'") + "'"
            
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
                    extra_html += "<hr/><p><b>Last jitter test:</b></p>"
                    if isinstance(max_us, int):
                        extra_html += f"<p>Max: {max_us} µs</p>"
                    else:
                        extra_html += "<p>Result: unavailable</p>"
                    if isinstance(threads, list) and threads:
                        extra_html += "<table>"
                        extra_html += "<tr><td><b>Thread</b></td><td><b>Max (µs)</b></td></tr>"
                        for item in sorted(threads, key=lambda t: t.get("thread", 0)):
                            t = item.get("thread")
                            v = item.get("max_us")
                            if isinstance(t, int) and isinstance(v, int):
                                extra_html += f"<tr><td>{t}</td><td>{v}</td></tr>"
                        extra_html += "</table>"
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
                    "<hr/><p><b>Note:</b> QjackCtl reads its config on launch. "
                    "Quit and reopen QjackCtl to refresh the ServerPrefix in the UI.</p>"
                )

            html = f"""
            <h3>{k.title}</h3>
            <p>{k.description}</p>
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

            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.rejected.connect(dialog.reject)
            layout.addWidget(btns)

            dialog.exec()

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

            def _collect_live_checks() -> list[str]:
                lines: list[str] = []
                lines.append(f"knob_id: {k.id}")
                lines.append(f"title: {k.title}")
                lines.append(f"status: {self._knob_statuses.get(k.id, 'unknown')}")
                lines.append("")

                kind = k.impl.kind if k.impl else ""
                params = dict(k.impl.params) if k.impl else {}
                lines.append(f"kind: {kind}")

                if kind == "qjackctl_server_prefix":
                    path = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
                    lines.append("")
                    lines.append("qjackctl_config:")
                    for line in _read_file(path, max_lines=200):
                        if any(key in line for key in ("DefPreset", "\\Server", "\\ServerPrefix")):
                            lines.append(line)
                elif kind == "systemd_unit_toggle":
                    unit = str(params.get("unit", ""))
                    if unit:
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
                elif kind == "sysfs_glob_kv":
                    pattern = str(params.get("glob", ""))
                    if pattern:
                        for p in sorted(glob.glob(pattern))[:8]:
                            try:
                                val = Path(p).read_text(encoding="utf-8").strip()
                                lines.append(f"{p}: {val}")
                            except Exception as e:
                                lines.append(f"{p}: unreadable: {e}")
                elif kind == "kernel_cmdline":
                    param = str(params.get("param", ""))
                    if param:
                        try:
                            running = Path("/proc/cmdline").read_text(encoding="utf-8").strip()
                            lines.append(f"/proc/cmdline: {running}")
                            tokens = running.split()
                            lines.append(f"/proc/cmdline has {param}: {_param_present(tokens, param)}")
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
                                lines.append(f"{boot_path} has {param}: {in_boot}")
                        except Exception as e:
                            lines.append(f"boot config read error: {e}")
                elif kind == "udev_rule":
                    path = str(params.get("path", ""))
                    if path:
                        lines.extend(_read_file(path))
                elif kind == "pipewire_conf":
                    path = str(params.get("path", "~/.config/pipewire/pipewire.conf.d/99-audioknob.conf"))
                    lines.extend(_read_file(path))
                elif kind == "group_membership":
                    r = subprocess.run(["id"], capture_output=True, text=True)
                    lines.append(f"id: {r.stdout.strip()}")
                elif kind == "pam_limits_audio_group":
                    path = str(params.get("path", ""))
                    if path:
                        lines.extend(_read_file(path))
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
                    if shutil.which(cmd):
                        r = subprocess.run([cmd, "status"], capture_output=True, text=True)
                        lines.append(r.stdout.strip() or r.stderr.strip())
                    else:
                        lines.append("balooctl not found")

                return lines

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
                text.setPlainText("\n".join(checks))

            def _run_checks() -> None:
                refresh_btn.setEnabled(False)
                cli_status_label.setText("CLI status: running...")
                text.setPlainText("Running CLI checks...")

                def _task():
                    return True, {
                        "cli_status": _cli_status(),
                        "live_checks": _collect_live_checks(),
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
            errors = []
            successes = []
            results = []
            
            for group in groups_to_add:
                try:
                    cmd = ["pkexec", usermod, "-aG", group, user]
                    p = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True
                    )
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
            
            # Report results
            msg = []
            if successes:
                msg.append(f"<b style='color: #2e7d32;'>Added to:</b> {', '.join(successes)}")
            if errors:
                msg.append(f"<br/><b style='color: #d32f2f;'>Errors:</b><br/>{'<br/>'.join(errors)}")
            if successes:
                msg.append("<br/><br/><b>Reboot required for changes to take effect.</b>")
            
            QMessageBox.information(self, "Group Membership", "".join(msg))
            logger.info("join groups user=%s added=%s errors=%s", user, ",".join(successes), "; ".join(errors))
            _log_gui_audit(
                "join-groups",
                {
                    "user": user,
                    "groups": groups_to_add,
                    "added": successes,
                    "errors": errors,
                    "results": results,
                },
            )
            
            # Refresh (won't show changes until re-login, but update UI state)
            if successes:
                self._knob_statuses["audio_group_membership"] = "pending_reboot"
                self._update_reboot_banner()

            self._refresh_user_groups()
            self._populate()

        def _on_leave_groups(self) -> None:
            """Remove current user from audio groups."""
            from audioknob_gui.platform.detect import get_available_audio_groups
            from audioknob_gui.platform.packages import which_command

            logger = _get_gui_logger()
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

            errors = []
            successes = []
            results = []

            if gpasswd:
                for group in groups_to_remove:
                    try:
                        cmd = ["pkexec", gpasswd, "-d", user, group]
                        p = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                        )
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
                # Fallback: replace supplementary groups via usermod -G
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
                    p = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                    )
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

            msg = []
            if successes:
                msg.append(f"<b style='color: #2e7d32;'>Removed from:</b> {', '.join(successes)}")
            if errors:
                msg.append(f"<br/><b style='color: #d32f2f;'>Errors:</b><br/>{'<br/>'.join(errors)}")
            if successes:
                msg.append("<br/><br/><b>Reboot required for changes to take effect.</b>")

            QMessageBox.information(self, "Group Membership", "".join(msg))
            logger.info("leave groups user=%s removed=%s errors=%s", user, ",".join(successes), "; ".join(errors))
            _log_gui_audit(
                "leave-groups",
                {
                    "user": user,
                    "groups": groups_to_remove,
                    "removed": successes,
                    "errors": errors,
                    "results": results,
                },
            )

            if successes:
                self._knob_statuses["audio_group_membership"] = "pending_reboot"
                self._update_reboot_banner()

            self._refresh_user_groups()
            self._populate()

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

            def _task():
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

        def _on_apply_queue(self, reboot_after: bool) -> None:
            if not self._queued_actions or self._queue_busy:
                return
            if self._busy_knobs:
                QMessageBox.information(
                    self,
                    "Busy",
                    "Finish current operations before applying queued changes.",
                )
                return
            by_id = {k.id: k for k in self.registry}
            queued = [(kid, action) for kid, action in self._queued_actions.items() if kid in by_id]
            if not queued:
                return
            titles = []
            for kid, action in queued:
                verb = "Apply" if action == "apply" else "Reset"
                titles.append(f"{verb}: {by_id[kid].title}")
            confirm = ConfirmDialog(titles, parent=self)
            confirm.exec()
            if not confirm.ok:
                return

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
                        try:
                            _run_pkexec_command([str(x) for x in cmd])
                        except RuntimeError as e:
                            if str(e) != _PKEXEC_CANCELLED:
                                QMessageBox.warning(self, "Update Failed", str(e))

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
                if knob_id == "qjackctl_server_prefix_rt" and self._is_process_running(["qjackctl", "qjackctl6"]):
                    QMessageBox.information(
                        self,
                        "QjackCtl Restart Needed",
                        "QjackCtl reads its config on launch.\n\n"
                        "Quit and reopen QjackCtl to refresh the ServerPrefix in the UI.",
                    )
                if isinstance(payload, dict):
                    self._handle_apply_followups(payload.get("result", {}))

            if not success:
                if message == _PKEXEC_CANCELLED:
                    self._queue_needs_reboot = False
                    self._refresh_statuses()
                    self._populate()
                    return
                if action == "reset" and _is_no_transaction_error(message):
                    if self._confirm_force_reset(knob_id):
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
                _get_gui_logger().error("apply queue failed error=%s", message)
                QMessageBox.critical(self, "Failed", message or "Unknown error")

            if "qjackctl_server_prefix_rt" in applied_ids and self._is_process_running(["qjackctl", "qjackctl6"]):
                QMessageBox.information(
                    self,
                    "QjackCtl Restart Needed",
                    "QjackCtl reads its config on launch.\n\n"
                    "Quit and reopen QjackCtl to refresh the ServerPrefix in the UI.",
                )

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
                self._on_reboot_now()
            self._populate()

        def _confirm_force_reset(self, knob_id: str) -> bool:
            k = next((k for k in self.registry if k.id == knob_id), None)
            if not k:
                return False
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
            results_text = []
            errors = []

            # Phase 1: User-scope reset (no pkexec needed)
            try:
                argv = [
                    sys.executable,
                    "-m",
                    "audioknob_gui.worker.cli",
                    "reset-defaults",
                    "--scope", "user",
                ]
                p = subprocess.run(argv, text=True, capture_output=True)
                if p.returncode != 0:
                    err_msg = p.stderr.strip() or p.stdout.strip() or f"Exit code {p.returncode}"
                    errors.append(f"User reset failed: {err_msg}")
                elif p.stdout:
                    try:
                        result = json.loads(p.stdout)
                        if result.get("reset_count", 0) > 0:
                            results_text.append(f"Reset {result['reset_count']} user file(s)")
                        errors.extend(result.get("errors", []))
                    except json.JSONDecodeError as e:
                        errors.append(f"User reset: invalid response: {e}")
            except Exception as e:
                errors.append(f"User reset failed: {e}")

            # Phase 2: Root-scope reset (needs pkexec)
            root_files = [f for f in files if f.get("scope") == "root"]
            needs_root = bool(root_files) or has_root_effects
            
            if needs_root:
                try:
                    worker = _pick_root_worker_path()
                    argv = [
                        "pkexec",
                        worker,
                        "reset-defaults",
                        "--scope", "root",
                    ]
                    p = subprocess.run(argv, text=True, capture_output=True)
                    if p.returncode != 0:
                        err_msg = p.stderr.strip() or p.stdout.strip() or f"Exit code {p.returncode}"
                        errors.append(f"Root reset failed: {err_msg}")
                    elif p.stdout:
                        try:
                            result = json.loads(p.stdout)
                            if result.get("reset_count", 0) > 0:
                                results_text.append(f"Reset {result['reset_count']} system file(s)")
                            errors.extend(result.get("errors", []))
                        except json.JSONDecodeError as e:
                            errors.append(f"Root reset: invalid response: {e}")
                except Exception as e:
                    errors.append(f"Root reset failed: {e}")

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
                QMessageBox.warning(
                    self,
                    "Reset completed with errors",
                    "\n".join(results_text) + "\n\nErrors:\n" + "\n".join(errors[:5])
                )
            else:
                QMessageBox.information(
                    self,
                    "Reset complete",
                    "All audioknob-gui changes have been reset to system defaults.\n\n"
                    + "\n".join(results_text)
                )

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

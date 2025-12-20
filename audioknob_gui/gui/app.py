from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def _registry_path() -> str:
    from audioknob_gui.core.paths import get_registry_path
    return get_registry_path()


def _pkexec_available() -> bool:
    from shutil import which

    return which("pkexec") is not None


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
        raise RuntimeError(p.stderr.strip() or "worker apply-user failed")
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
        raise RuntimeError(p.stderr.strip() or "worker apply failed")
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
        raise RuntimeError(p.stderr.strip() or "worker restore failed")
    return json.loads(p.stdout)


def _state_path() -> Path:
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        d = Path(xdg_state) / "audioknob-gui"
    else:
        d = Path.home() / ".local" / "state" / "audioknob-gui"
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.json"


def load_state() -> dict:
    p = _state_path()
    default = {
        "schema": 1,
        "last_txid": None,
        "last_user_txid": None,
        "last_root_txid": None,
        "font_size": 11,
        # Per-knob UI state
        "qjackctl_cpu_cores": None,  # list[int] or None
        "pipewire_quantum": None,  # int (32..1024) or None
        "pipewire_sample_rate": None,  # int (44100/48000/88200/96000/192000) or None
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
        from PySide6.QtCore import Qt
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
        from PySide6.QtGui import QColor
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

    class ConfirmDialog(QDialog):
        def __init__(self, planned_ids: list[str], parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Confirm apply")
            self.resize(520, 150)
            self.ok = False

            root = QVBoxLayout(self)
            root.addWidget(QLabel("<b>Apply these changes?</b>"))
            root.addWidget(QLabel("Knobs: " + ", ".join(planned_ids)))
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
            self.setWindowTitle("audioknob-gui")
            self.resize(980, 640)

            self.state = load_state()
            self.registry = load_registry(_registry_path())
            
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
            top.addWidget(QLabel("Font:"))
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

            self.btn_undo = QPushButton("Undo")
            self.btn_undo.setToolTip("Undo last change")
            self.btn_reset = QPushButton("Reset All")
            self.btn_reset.setToolTip("Reset all changes to system defaults")
            top.addWidget(self.btn_undo)
            top.addWidget(self.btn_reset)
            root.addLayout(top)

            self.table = QTableWidget(0, 7)
            self.table.setHorizontalHeaderLabels(["", "Knob", "Status", "Category", "Risk", "Action", "Config"])
            self.table.horizontalHeader().setStretchLastSection(False)
            self.table.setSortingEnabled(True)
            self.table.setAlternatingRowColors(True)
            self.table.setWordWrap(False)
            self.table.setTextElideMode(Qt.ElideRight)
            self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            self.table.verticalHeader().setVisible(False)
            header = self.table.horizontalHeader()
            header.setMinimumSectionSize(60)
            # Make every column user-resizable (Interactive). We also set reasonable defaults.
            # NOTE: ResizeToContents does NOT reliably account for cell widgets (buttons/combos),
            # which causes text clipping like "Apply" -> "Annlv".
            for c in range(7):
                header.setSectionResizeMode(c, QHeaderView.Interactive)
            self.table.setColumnWidth(0, 32)   # Info button
            self.table.setColumnWidth(1, 420)  # Knob title
            self.table.setColumnWidth(2, 120)  # Status
            self.table.setColumnWidth(3, 110)  # Category
            self.table.setColumnWidth(4, 80)   # Risk
            self.table.setColumnWidth(5, 96)   # Action (fits Apply/Reset)
            self.table.setColumnWidth(6, 160)  # Config (fits 48000 Hz)
            root.addWidget(self.table)

            self._knob_statuses: dict[str, str] = {}
            self._user_groups: set[str] = set()
            self._refresh_user_groups()
            self._refresh_statuses()
            self._populate()

            self.btn_undo.clicked.connect(self.on_undo)
            self.btn_reset.clicked.connect(self.on_reset_defaults)

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

        def _refresh_statuses(self) -> None:
            """Fetch current status of all knobs."""
            try:
                # Clear old values so we don't keep stale states if status probe fails.
                self._knob_statuses = {}
                argv = [
                    sys.executable,
                    "-m",
                    "audioknob_gui.worker.cli",
                    "--registry",
                    _registry_path(),
                    "status",
                ]
                p = subprocess.run(argv, text=True, capture_output=True)
                if p.returncode == 0:
                    data = json.loads(p.stdout)
                    for item in data.get("statuses", []):
                        self._knob_statuses[item["knob_id"]] = item["status"]
            except Exception:
                pass  # Status check failed, leave statuses empty
            self._update_reboot_banner()

        def _update_reboot_banner(self) -> None:
            needs_reboot = any(v == "pending_reboot" for v in self._knob_statuses.values())
            if needs_reboot:
                self.reboot_banner.setText("Reboot required")
                self.reboot_banner.setVisible(True)
            else:
                self.reboot_banner.setVisible(False)

        def _make_apply_button(self, text: str = "Apply") -> QPushButton:
            """Create an Apply button."""
            btn = QPushButton(text)
            # Ensure button labels don't clip at common font sizes and narrow columns.
            btn.setMinimumWidth(80)
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            return btn

        def _make_reset_button(self, text: str = "Reset") -> QPushButton:
            """Create a Reset button."""
            btn = QPushButton(text)
            btn.setMinimumWidth(80)
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            return btn

        def _make_action_button(self, text: str) -> QPushButton:
            """Create an action button."""
            btn = QPushButton(text)
            btn.setMinimumWidth(80)
            btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            return btn

        def _status_display(self, status: str) -> tuple[str, str]:
            """Return (display_text, color) for a status."""
            # Handle test results: "result:12 µs" → "12 µs"
            if status.startswith("result:"):
                return (status[7:], "#1976d2")  # Blue
            
            mapping = {
                "applied": ("✓ Applied", "#2e7d32"),      # Green
                "not_applied": ("—", "#757575"),          # Gray dash
                "partial": ("◐ Partial", "#f57c00"),      # Orange
                "pending_reboot": ("⟳ Reboot", "#f57c00"), # Orange - needs reboot
                "read_only": ("—", "#9e9e9e"),            # Gray dash
                "unknown": ("—", "#9e9e9e"),              # Gray dash
                "running": ("⏳", "#1976d2"),             # Blue spinner
                "done": ("✓", "#2e7d32"),                 # Green check
                "error": ("✗", "#d32f2f"),                # Red X
            }
            return mapping.get(status, ("—", "#9e9e9e"))

        def _populate(self) -> None:
            # Disable sorting during population to avoid issues
            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(self.registry))
            
            for r, k in enumerate(self.registry):
                # Check requirements
                group_ok = self._knob_group_ok(k)
                commands_ok = self._knob_commands_ok(k)
                missing_cmds = self._knob_missing_commands(k)
                locked = not group_ok or not commands_ok
                
                # Determine lock reason
                lock_reason = ""
                if not group_ok:
                    lock_reason = f"Join groups: {', '.join(k.requires_groups)}"
                elif not commands_ok:
                    lock_reason = f"Install: {', '.join(missing_cmds)}"
                
                # Column 0: Info button
                info_btn = QPushButton("?")
                info_btn.setFixedWidth(28)
                info_btn.setToolTip("Show details")
                info_btn.clicked.connect(lambda _, kid=k.id: self._show_knob_info(kid))
                self.table.setCellWidget(r, 0, info_btn)

                # Column 1: Knob title (gray if locked)
                title_item = QTableWidgetItem(k.title)
                title_item.setData(Qt.UserRole, k.id)  # Store ID for lookup
                if locked:
                    title_item.setForeground(QColor("#9e9e9e"))
                    title_item.setToolTip(lock_reason)
                self.table.setItem(r, 1, title_item)

                # Column 2: Status (with color)
                if locked:
                    if not group_ok:
                        status_item = QTableWidgetItem("🔒")
                        status_item.setForeground(QColor("#ff9800"))
                    else:
                        status_item = QTableWidgetItem("📦")
                        status_item.setForeground(QColor("#1976d2"))
                    status_item.setToolTip(lock_reason)
                else:
                    status = self._knob_statuses.get(k.id, "unknown")
                    status_text, status_color = self._status_display(status)
                    status_item = QTableWidgetItem(status_text)
                    status_item.setForeground(QColor(status_color))
                self.table.setItem(r, 2, status_item)

                # Column 3: Category
                cat_item = QTableWidgetItem(str(k.category))
                if locked:
                    cat_item.setForeground(QColor("#9e9e9e"))
                self.table.setItem(r, 3, cat_item)

                # Column 4: Risk
                risk_item = QTableWidgetItem(str(k.risk_level))
                if locked:
                    risk_item.setForeground(QColor("#9e9e9e"))
                self.table.setItem(r, 4, risk_item)

                # Column 5: Action button (context-sensitive)
                if k.id == "audio_group_membership":
                    # Special: group membership knob
                    btn = self._make_apply_button("Join")
                    btn.clicked.connect(self._on_join_groups)
                    self.table.setCellWidget(r, 5, btn)
                elif not group_ok:
                    # Locked: user needs to join groups first
                    btn = QPushButton("🔒")
                    btn.setEnabled(False)
                    btn.setToolTip(lock_reason)
                    self.table.setCellWidget(r, 5, btn)
                elif not commands_ok:
                    # Locked: needs package install
                    btn = self._make_action_button("Install")
                    btn.setToolTip(f"Install: {', '.join(missing_cmds)}")
                    btn.clicked.connect(lambda _, cmds=missing_cmds: self._on_install_packages(cmds))
                    self.table.setCellWidget(r, 5, btn)
                elif k.id == "stack_detect":
                    btn = self._make_action_button("View")
                    btn.clicked.connect(self.on_view_stack)
                    self.table.setCellWidget(r, 5, btn)
                elif k.id == "scheduler_jitter_test":
                    btn = self._make_action_button("Test")
                    btn.clicked.connect(lambda _, kid=k.id: self.on_run_test(kid))
                    self.table.setCellWidget(r, 5, btn)
                elif k.id == "blocker_check":
                    btn = self._make_action_button("Scan")
                    btn.clicked.connect(self.on_check_blockers)
                    self.table.setCellWidget(r, 5, btn)
                elif k.id == "pipewire_quantum" and not locked:
                    # Action column: Apply/Reset button
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id, root=k.requires_root: self._on_reset_knob(kid, root))
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_apply_knob(kid))
                    self.table.setCellWidget(r, 5, btn)

                    # Config column: quantum selector
                    q_combo = QComboBox()
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
                    self.table.setCellWidget(r, 6, q_combo)

                elif k.id == "pipewire_sample_rate" and not locked:
                    # Action column: Apply/Reset button
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id, root=k.requires_root: self._on_reset_knob(kid, root))
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_apply_knob(kid))
                    self.table.setCellWidget(r, 5, btn)

                    # Config column: sample rate selector
                    r_combo = QComboBox()
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
                    self.table.setCellWidget(r, 6, r_combo)
                elif k.impl is None:
                    # Placeholder knob - not implemented yet
                    btn = QPushButton("—")
                    btn.setEnabled(False)
                    btn.setToolTip("Not implemented yet")
                    self.table.setCellWidget(r, 5, btn)
                else:
                    # Normal knob: show Apply or Reset based on current status
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id, root=k.requires_root: self._on_reset_knob(kid, root))
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_apply_knob(kid))
                    self.table.setCellWidget(r, 5, btn)

                # Column 6: Config - clear if no widget was set for this row
                # (PipeWire rows set their own widgets above; other rows need clearing)
                if k.id not in ("pipewire_quantum", "pipewire_sample_rate"):
                    self.table.removeCellWidget(r, 6)
            
            # Re-enable sorting after population
            self.table.setSortingEnabled(True)
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
                self.btn_undo.setFont(font)
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
                self.table.resizeRowsToContents()
                self.table.viewport().update()
            except Exception:
                pass

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
                    background-color: #3a3a3a;
                    color: #666666;
                }
                QComboBox, QSpinBox {
                    background-color: #404040;
                    color: #e0e0e0;
                    border: 1px solid #555555;
                    padding: 4px;
                    border-radius: 3px;
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
            headline, detail = jitter_test_summary(duration_s=5)
            QMessageBox.information(self, headline, detail)

        def on_run_test(self, knob_id: str) -> None:
            """Run a test and update the status column with results."""
            if knob_id == "scheduler_jitter_test":
                # Show a brief "running" indicator
                self._update_knob_status(knob_id, "running", "⏳ Running...")
                QApplication.processEvents()  # Update UI immediately
                
                headline, _ = jitter_test_summary(duration_s=5)
                
                # Update status with result (e.g., "max 12 µs")
                if "max" in headline:
                    # Extract just the number: "Scheduler jitter: max 12 µs" → "12 µs"
                    parts = headline.split("max")
                    if len(parts) > 1:
                        result = parts[1].strip()
                        self._knob_statuses[knob_id] = f"result:{result}"
                    else:
                        self._knob_statuses[knob_id] = "done"
                else:
                    self._knob_statuses[knob_id] = "error"
                
                self._populate()

        def _update_knob_status(self, knob_id: str, status: str, display: str) -> None:
            """Update the status cell for a specific knob."""
            # Keep backing store in sync so subsequent _populate() reflects the new state.
            self._knob_statuses[knob_id] = status
            for r, k in enumerate(self.registry):
                if k.id == knob_id:
                    status_item = QTableWidgetItem(display)
                    status_item.setForeground(QColor("#1976d2"))
                    # Status column is col 2 (col 1 is knob title).
                    self.table.setItem(r, 2, status_item)
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

        def on_check_blockers(self) -> None:
            """Run comprehensive realtime configuration scan."""
            from audioknob_gui.testing.rtcheck import run_full_scan, format_scan_html, CheckStatus
            
            # Run the scan
            result = run_full_scan()
            
            # Filter to actionable checks: show only those with fix_knob
            # (This is what user can actually improve via the knob menu)
            actionable_checks = [c for c in result.checks if c.fix_knob is not None]
            actionable_issues = [c for c in actionable_checks if c.status not in (CheckStatus.PASS, CheckStatus.SKIP)]
            
            # Build focused HTML (actionable items only)
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
            
            # Show full stats
            html.append("<hr/>")
            html.append(f"<p style='color:#666; font-size:0.9em'>Full scan: {result.passed} passed, {result.warnings} warnings, {result.failed} failed (score: {result.score}%)</p>")
            
            # Show in a resizable dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("RT Config Scan")
            dialog.resize(600, 400)
            layout = QVBoxLayout(dialog)
            
            text = QTextEdit()
            text.setReadOnly(True)
            text.setHtml("".join(html))
            layout.addWidget(text)
            
            # Button row with Show Full Scan option
            btn_layout = QHBoxLayout()
            
            def show_full_scan():
                text.setHtml(format_scan_html(result))
                dialog.setWindowTitle(f"RT Config Scan (Full) - Score: {result.score}%")
            
            full_btn = QPushButton("Show Full Scan")
            full_btn.clicked.connect(show_full_scan)
            btn_layout.addWidget(full_btn)
            btn_layout.addStretch()
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)
            
            dialog.exec()

        def _on_join_groups(self) -> None:
            """Add current user to audio groups."""
            from audioknob_gui.platform.detect import get_available_audio_groups, get_missing_groups
            
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
            user = os.environ.get("USER") or getpass.getuser()
            errors = []
            successes = []
            
            for group in groups_to_add:
                try:
                    p = subprocess.run(
                        ["pkexec", "usermod", "-aG", group, user],
                        capture_output=True,
                        text=True
                    )
                    if p.returncode == 0:
                        successes.append(group)
                    else:
                        errors.append(f"{group}: {p.stderr.strip() or 'Failed'}")
                except Exception as e:
                    errors.append(f"{group}: {e}")
            
            # Report results
            msg = []
            if successes:
                msg.append(f"<b style='color: #2e7d32;'>Added to:</b> {', '.join(successes)}")
            if errors:
                msg.append(f"<br/><b style='color: #d32f2f;'>Errors:</b><br/>{'<br/>'.join(errors)}")
            if successes:
                msg.append("<br/><br/><b>Log out and back in for changes to take effect!</b>")
            
            QMessageBox.information(self, "Group Membership", "".join(msg))
            
            # Refresh (won't show changes until re-login, but update UI state)
            self._refresh_user_groups()
            self._populate()

        def _on_install_packages(self, commands: list[str]) -> None:
            """Install packages that provide the given commands."""
            from audioknob_gui.platform.packages import get_package_name, detect_package_manager
            
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
                    return
                
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if p.returncode == 0:
                    QMessageBox.information(
                        self,
                        "Success",
                        f"Installed: {', '.join(packages)}"
                    )
                    self._populate()  # Refresh UI
                else:
                    QMessageBox.critical(
                        self,
                        "Install Failed",
                        f"Failed to install packages:\n\n{p.stderr.strip()}"
                    )
            except subprocess.TimeoutExpired:
                QMessageBox.critical(self, "Timeout", "Package installation timed out")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Install error: {e}")

        def _on_apply_knob(self, knob_id: str) -> None:
            """Apply a single knob optimization."""
            k = next((k for k in self.registry if k.id == knob_id), None)
            if not k:
                return
            
            try:
                if k.requires_root:
                    result = _run_worker_apply_pkexec([knob_id])
                    self.state["last_root_txid"] = result.get("txid")
                else:
                    result = _run_worker_apply_user([knob_id])
                    self.state["last_user_txid"] = result.get("txid")
                save_state(self.state)
            except Exception as e:
                QMessageBox.critical(self, "Failed", str(e))
                return
            
            # Refresh UI
            self._refresh_statuses()
            self._populate()

        def _on_reset_knob(self, knob_id: str, requires_root: bool) -> None:
            """Reset a single knob to original."""
            success, msg = self._restore_knob_internal(knob_id, requires_root)
            if not success:
                QMessageBox.warning(self, "Reset Failed", msg)
            
            # Refresh UI
            self._refresh_statuses()
            self._populate()

        def _restore_knob_internal(self, knob_id: str, requires_root: bool) -> tuple[bool, str]:
            """Restore a single knob to its original state."""
            if requires_root:
                try:
                    worker = _pick_root_worker_path()
                    argv = ["pkexec", worker, "restore-knob", knob_id]
                    p = subprocess.run(argv, text=True, capture_output=True)
                    result = json.loads(p.stdout) if p.stdout else {}
                    if result.get("success"):
                        return True, f"Reset {knob_id}"
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
                    result = json.loads(p.stdout) if p.stdout else {}
                    if result.get("success"):
                        return True, f"Reset {knob_id}"
                    return False, result.get("error", "Unknown error")
                except Exception as e:
                    return False, str(e)
        
        def _restore_knob(self, knob_id: str, requires_root: bool) -> tuple[bool, str]:
            """Legacy wrapper for batch restore."""
            return self._restore_knob_internal(knob_id, requires_root)

        def on_undo(self) -> None:
            # Try to restore most recent transaction (user or root)
            txid = self.state.get("last_user_txid") or self.state.get("last_root_txid") or self.state.get("last_txid")
            if not txid:
                QMessageBox.information(self, "No undo", "No last transaction recorded.")
                return

            is_root = bool(self.state.get("last_root_txid") == txid)

            d = ConfirmDialog([f"restore:{txid}"], self)
            d.exec()
            if not d.ok:
                return

            try:
                if is_root:
                    _run_worker_restore_pkexec(str(txid))
                else:
                    # User restore doesn't need pkexec
                    argv = [
                        sys.executable,
                        "-m",
                        "audioknob_gui.worker.cli",
                        "restore",
                        str(txid),
                    ]
                    p = subprocess.run(argv, text=True, capture_output=True)
                    if p.returncode != 0:
                        raise RuntimeError(p.stderr.strip() or "worker restore failed")
            except Exception as e:
                QMessageBox.critical(self, "Undo failed", str(e))
                return

            # Clear the restored txid
            if is_root:
                self.state["last_root_txid"] = None
            else:
                self.state["last_user_txid"] = None
            self.state["last_txid"] = None
            save_state(self.state)
            
            # Refresh status display
            self._refresh_statuses()
            self._populate()
            
            QMessageBox.information(self, "Restored", "Undo complete.")

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
            save_state(self.state)

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

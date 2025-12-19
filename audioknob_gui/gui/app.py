from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    # app.py is in audioknob_gui/gui/app.py
    # parents[0] = audioknob_gui/gui/
    # parents[1] = audioknob_gui/
    # parents[2] = repo root
    return Path(__file__).resolve().parents[2]


def _registry_path() -> str:
    return str(_repo_root() / "config" / "registry.json")


def _pkexec_available() -> bool:
    from shutil import which

    return which("pkexec") is not None


def _root_worker_path_candidates() -> list[str]:
    # The polkit policy installs a fixed-path wrapper here by default.
    return [
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
            QCheckBox,
            QDialog,
            QDialogButtonBox,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QMessageBox,
            QPushButton,
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

            w = QWidget()
            self.setCentralWidget(w)
            root = QVBoxLayout(w)

            top = QHBoxLayout()
            top.addWidget(QLabel("Pick actions per knob, then Preview and Apply."))
            
            # Font size control
            top.addWidget(QLabel("Font:"))
            self.font_spinner = QSpinBox()
            self.font_spinner.setRange(8, 24)
            self.font_spinner.setValue(self.state.get("font_size", 11))
            self.font_spinner.setToolTip("Adjust font size (8-24)")
            self.font_spinner.valueChanged.connect(self._on_font_change)
            top.addWidget(self.font_spinner)
            
            self.btn_undo = QPushButton("Undo")
            self.btn_undo.setToolTip("Undo last change")
            self.btn_reset = QPushButton("Reset All")
            self.btn_reset.setToolTip("Reset all changes to system defaults")
            top.addStretch(1)
            top.addWidget(self.btn_undo)
            top.addWidget(self.btn_reset)
            root.addLayout(top)

            self.table = QTableWidget(0, 6)
            self.table.setHorizontalHeaderLabels(["Knob", "Status", "Category", "Risk", "Action", ""])
            self.table.horizontalHeader().setStretchLastSection(False)
            self.table.setSortingEnabled(True)
            self.table.setColumnWidth(0, 200)  # Knob
            self.table.setColumnWidth(1, 80)   # Status
            self.table.setColumnWidth(2, 100)  # Category
            self.table.setColumnWidth(3, 60)   # Risk
            self.table.setColumnWidth(4, 80)   # Action
            self.table.setColumnWidth(5, 50)   # Info
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

        def _status_display(self, status: str) -> tuple[str, str]:
            """Return (display_text, color) for a status."""
            # Handle test results: "result:12 µs" → "12 µs"
            if status.startswith("result:"):
                return (status[7:], "#1976d2")  # Blue
            
            mapping = {
                "applied": ("✓ Applied", "#2e7d32"),      # Green
                "not_applied": ("—", "#757575"),          # Gray dash
                "partial": ("◐ Partial", "#f57c00"),      # Orange
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
                
                # Column 0: Knob title (gray if locked)
                title_item = QTableWidgetItem(k.title)
                title_item.setData(Qt.UserRole, k.id)  # Store ID for lookup
                if locked:
                    title_item.setForeground(QColor("#9e9e9e"))
                    title_item.setToolTip(lock_reason)
                self.table.setItem(r, 0, title_item)

                # Column 1: Status (with color)
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
                self.table.setItem(r, 1, status_item)

                # Column 2: Category
                cat_item = QTableWidgetItem(str(k.category))
                if locked:
                    cat_item.setForeground(QColor("#9e9e9e"))
                self.table.setItem(r, 2, cat_item)

                # Column 3: Risk
                risk_item = QTableWidgetItem(str(k.risk_level))
                if locked:
                    risk_item.setForeground(QColor("#9e9e9e"))
                self.table.setItem(r, 3, risk_item)

                # Column 4: Action button (context-sensitive)
                if k.id == "audio_group_membership":
                    # Special: group membership knob
                    btn = QPushButton("Join")
                    btn.clicked.connect(self._on_join_groups)
                    self.table.setCellWidget(r, 4, btn)
                elif not group_ok:
                    # Locked: user needs to join groups first
                    btn = QPushButton("🔒")
                    btn.setEnabled(False)
                    btn.setToolTip(lock_reason)
                    self.table.setCellWidget(r, 4, btn)
                elif not commands_ok:
                    # Locked: needs package install
                    btn = QPushButton("Install")
                    btn.setToolTip(f"Install: {', '.join(missing_cmds)}")
                    btn.clicked.connect(lambda _, cmds=missing_cmds: self._on_install_packages(cmds))
                    self.table.setCellWidget(r, 4, btn)
                elif k.id == "stack_detect":
                    btn = QPushButton("View")
                    btn.clicked.connect(self.on_view_stack)
                    self.table.setCellWidget(r, 4, btn)
                elif k.id == "scheduler_jitter_test":
                    btn = QPushButton("Test")
                    btn.clicked.connect(lambda _, kid=k.id: self.on_run_test(kid))
                    self.table.setCellWidget(r, 4, btn)
                elif k.id == "blocker_check":
                    btn = QPushButton("Scan")
                    btn.clicked.connect(self.on_check_blockers)
                    self.table.setCellWidget(r, 4, btn)
                elif k.impl is None:
                    # Placeholder knob - not implemented yet
                    btn = QPushButton("—")
                    btn.setEnabled(False)
                    btn.setToolTip("Not implemented yet")
                    self.table.setCellWidget(r, 4, btn)
                else:
                    # Normal knob: show Apply or Reset based on current status
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status == "applied":
                        btn = QPushButton("Reset")
                        btn.clicked.connect(lambda _, kid=k.id, root=k.requires_root: self._on_reset_knob(kid, root))
                    else:
                        btn = QPushButton("Apply")
                        btn.clicked.connect(lambda _, kid=k.id: self._on_apply_knob(kid))
                    self.table.setCellWidget(r, 4, btn)

                # Column 5: Info button (shows details popup)
                info_btn = QPushButton("ℹ")
                info_btn.setFixedWidth(30)
                info_btn.clicked.connect(lambda _, kid=k.id: self._show_knob_info(kid))
                self.table.setCellWidget(r, 5, info_btn)
            
            # Re-enable sorting after population
            self.table.setSortingEnabled(True)

        def _apply_font_size(self, size: int) -> None:
            """Apply font size to the application."""
            font = QApplication.instance().font()
            font.setPointSize(size)
            QApplication.instance().setFont(font)

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

        def on_configure_knob(self, knob_id: str) -> None:
            if knob_id != "qjackctl_server_prefix_rt":
                return

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
            for r, k in enumerate(self.registry):
                if k.id == knob_id:
                    status_item = QTableWidgetItem(display)
                    status_item.setForeground(QColor("#1976d2"))
                    self.table.setItem(r, 1, status_item)
                    break

        def on_view_stack(self) -> None:
            """Show detected audio stack information."""
            try:
                from audioknob_gui.platform.detect import detect_stack, list_alsa_playback_devices
                
                stack = detect_stack()
                devices = list_alsa_playback_devices()
                
                info_lines = [
                    "<b>Audio Stack Detection</b>",
                    "",
                    f"<b>PipeWire:</b> {'✓ Active' if stack.pipewire_active else '○ Not active'}",
                    f"<b>WirePlumber:</b> {'✓ Active' if stack.wireplumber_active else '○ Not active'}",
                    f"<b>JACK:</b> {'✓ Active' if stack.jack_active else '○ Not active'}",
                    "",
                    f"<b>ALSA Playback Devices ({len(devices)}):</b>",
                ]
                for dev in devices[:5]:  # Show first 5
                    info_lines.append(f"  • {dev.get('raw', 'Unknown')}")
                if len(devices) > 5:
                    info_lines.append(f"  ... and {len(devices) - 5} more")
                
                QMessageBox.information(self, "Audio Stack", "<br/>".join(info_lines))
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
                for key, val in k.impl.params.items():
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

            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.rejected.connect(dialog.reject)
            layout.addWidget(btns)

            dialog.exec()

        def on_check_blockers(self) -> None:
            """Run comprehensive realtime configuration scan."""
            from audioknob_gui.testing.rtcheck import run_full_scan, format_scan_html
            
            # Run the scan
            result = run_full_scan()
            html = format_scan_html(result)
            
            # Show in a resizable dialog
            dialog = QDialog(self)
            dialog.setWindowTitle(f"RT Config Scan - Score: {result.score}%")
            dialog.resize(600, 500)
            layout = QVBoxLayout(dialog)
            
            text = QTextEdit()
            text.setReadOnly(True)
            text.setHtml(html)
            layout.addWidget(text)
            
            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.rejected.connect(dialog.reject)
            layout.addWidget(btns)
            
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
            user = os.environ.get("USER", os.getlogin())
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
                    "list-changes",
                ]
                p = subprocess.run(argv, text=True, capture_output=True)
                if p.returncode != 0:
                    raise RuntimeError(p.stderr.strip() or "list-changes failed")
                changes = json.loads(p.stdout)
            except Exception as e:
                QMessageBox.critical(self, "Failed", f"Could not list changes: {e}")
                return

            file_count = changes.get("count", 0)
            if file_count == 0:
                QMessageBox.information(
                    self,
                    "Nothing to reset",
                    "No audioknob-gui changes found.\n\n"
                    "Either no changes have been applied, or they've already been reset."
                )
                return

            # Show summary and confirm
            files = changes.get("files", [])
            summary_lines = []
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

            confirm_dialog = QDialog(self)
            confirm_dialog.setWindowTitle("Reset to System Defaults")
            confirm_dialog.resize(600, 350)
            layout = QVBoxLayout(confirm_dialog)
            
            layout.addWidget(QLabel(
                f"<b>Reset {file_count} file(s) to system defaults?</b><br/><br/>"
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

            # Execute reset - first try without root (for user files)
            results_text = []
            errors = []

            # Run user-scope reset first
            try:
                argv = [
                    sys.executable,
                    "-m",
                    "audioknob_gui.worker.cli",
                    "reset-defaults",
                ]
                p = subprocess.run(argv, text=True, capture_output=True)
                result = json.loads(p.stdout) if p.stdout else {}
                if result.get("reset_count", 0) > 0:
                    results_text.append(f"Reset {result['reset_count']} user file(s)")
                errors.extend(result.get("errors", []))
            except Exception as e:
                errors.append(f"User reset failed: {e}")

            # Check if we need root for remaining files
            package_files = [f for f in files if f.get("reset_strategy") == "package"]
            if package_files:
                try:
                    worker = _pick_root_worker_path()
                    argv = [
                        "pkexec",
                        worker,
                        "reset-defaults",
                    ]
                    p = subprocess.run(argv, text=True, capture_output=True)
                    result = json.loads(p.stdout) if p.stdout else {}
                    if result.get("reset_count", 0) > 0:
                        results_text.append(f"Reset {result['reset_count']} system file(s)")
                    errors.extend(result.get("errors", []))
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

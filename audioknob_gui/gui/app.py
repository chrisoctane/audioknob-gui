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


@dataclass
class PlannedAction:
    knob_id: str
    action: str  # keep|apply|restore


def _run_worker_preview(knob_ids: list[str], *, action: str = "apply") -> dict:
    argv = [
        sys.executable,
        "-m",
        "audioknob_gui.worker.cli",
        "--registry",
        _registry_path(),
        "preview",
        "--action",
        action,
        *knob_ids,
    ]
    p = subprocess.run(argv, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "worker preview failed")
    return json.loads(p.stdout)


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
            QComboBox,
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
        from PySide6.QtGui import QFont
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

    class PreviewDialog(QDialog):
        def __init__(self, payload: dict, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Preview")
            self.resize(900, 600)

            root = QVBoxLayout(self)
            root.addWidget(QLabel("Preview of planned changes (nothing applied yet)."))

            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(json.dumps(payload, indent=2, sort_keys=True))
            root.addWidget(text)

            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.rejected.connect(self.reject)
            btns.accepted.connect(self.accept)
            root.addWidget(btns)

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
            
            self.btn_preview = QPushButton("Preview")
            self.btn_apply = QPushButton("Apply")
            self.btn_undo = QPushButton("Undo last")
            self.btn_reset = QPushButton("Reset to Defaults")
            self.btn_reset.setToolTip(
                "Reset ALL audioknob-gui changes to system defaults.\n"
                "Uses the best strategy per file:\n"
                "• Files we created: delete them\n"
                "• Package-owned files: restore from package manager\n"
                "• User configs: restore from backup"
            )
            self.btn_tests = QPushButton("Run jitter test")
            top.addStretch(1)
            top.addWidget(self.btn_tests)
            top.addWidget(self.btn_preview)
            top.addWidget(self.btn_apply)
            top.addWidget(self.btn_undo)
            top.addWidget(self.btn_reset)
            root.addLayout(top)

            self.table = QTableWidget(0, 6)
            self.table.setHorizontalHeaderLabels(["Knob", "Description", "Category", "Risk", "Planned action", "Configure"])
            self.table.horizontalHeader().setStretchLastSection(True)
            root.addWidget(self.table)

            self._populate()

            self.btn_tests.clicked.connect(self.on_tests)
            self.btn_preview.clicked.connect(self.on_preview)
            self.btn_apply.clicked.connect(self.on_apply)
            self.btn_undo.clicked.connect(self.on_undo)
            self.btn_reset.clicked.connect(self.on_reset_defaults)

        def _populate(self) -> None:
            self.table.setRowCount(len(self.registry))
            for r, k in enumerate(self.registry):
                # Build a rich tooltip with multiple lines
                tooltip = (
                    f"<b>{k.title}</b><br/><br/>"
                    f"{k.description}<br/><br/>"
                    f"<b>ID:</b> {k.id}<br/>"
                    f"<b>Category:</b> {k.category}<br/>"
                    f"<b>Risk:</b> {k.risk_level}<br/>"
                    f"<b>Requires root:</b> {'Yes' if k.requires_root else 'No'}<br/>"
                    f"<b>Requires reboot:</b> {'Yes' if k.requires_reboot else 'No'}"
                )
                
                title_item = QTableWidgetItem(k.title)
                title_item.setToolTip(tooltip)
                self.table.setItem(r, 0, title_item)
                
                desc_item = QTableWidgetItem(k.description)
                desc_item.setToolTip(tooltip)
                self.table.setItem(r, 1, desc_item)
                
                cat_item = QTableWidgetItem(str(k.category))
                cat_item.setToolTip(tooltip)
                self.table.setItem(r, 2, cat_item)
                
                risk_item = QTableWidgetItem(str(k.risk_level))
                risk_item.setToolTip(tooltip)
                self.table.setItem(r, 3, risk_item)

                combo = QComboBox()
                combo.addItem("Keep current", userData="keep")
                if k.capabilities.apply:
                    combo.addItem("Apply optimization", userData="apply")
                if k.capabilities.restore:
                    combo.addItem("Restore original", userData="restore")
                combo.setToolTip(tooltip)
                self.table.setCellWidget(r, 4, combo)

                # Per-knob configuration (only for QjackCtl knob for now)
                if k.id == "qjackctl_server_prefix_rt":
                    btn = QPushButton("Configure…")
                    btn.setToolTip(tooltip)
                    btn.clicked.connect(lambda _=False, kid=k.id: self.on_configure_knob(kid))
                    self.table.setCellWidget(r, 5, btn)
                else:
                    self.table.setCellWidget(r, 5, QWidget())

        def _planned(self) -> list[PlannedAction]:
            out: list[PlannedAction] = []
            for r, k in enumerate(self.registry):
                combo = self.table.cellWidget(r, 4)
                assert isinstance(combo, QComboBox)
                action = str(combo.currentData())
                out.append(PlannedAction(knob_id=k.id, action=action))
            return out

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

        def on_preview(self) -> None:
            planned = [p for p in self._planned() if p.action in ("apply", "restore")]
            if not planned:
                QMessageBox.information(self, "Nothing planned", "No knobs are set to Apply or Restore.")
                return

            apply_ids = [p.knob_id for p in planned if p.action == "apply"]
            if not apply_ids:
                QMessageBox.information(self, "Nothing to apply", "Only Restore is selected; use Undo/History.")
                return

            try:
                payload = _run_worker_preview(apply_ids, action="apply")
            except Exception as e:
                QMessageBox.critical(self, "Preview failed", str(e))
                return

            PreviewDialog(payload, self).exec()

        def on_apply(self) -> None:
            planned = [p for p in self._planned() if p.action == "apply"]
            if not planned:
                QMessageBox.information(self, "Nothing planned", "No knobs are set to Apply.")
                return

            # Split into root vs non-root
            root_knobs: list[str] = []
            user_knobs: list[str] = []
            for p in planned:
                k = next((k for k in self.registry if k.id == p.knob_id), None)
                if k and k.requires_root:
                    root_knobs.append(p.knob_id)
                else:
                    user_knobs.append(p.knob_id)

            all_ids = root_knobs + user_knobs

            try:
                payload = _run_worker_preview(all_ids, action="apply")
            except Exception as e:
                QMessageBox.critical(self, "Preview failed", str(e))
                return

            PreviewDialog(payload, self).exec()

            d = ConfirmDialog(all_ids, self)
            d.exec()
            if not d.ok:
                return

            # Apply non-root knobs first (no pkexec)
            if user_knobs:
                try:
                    result_user = _run_worker_apply_user(user_knobs)
                    self.state["last_user_txid"] = result_user.get("txid")
                except Exception as e:
                    QMessageBox.critical(self, "Apply failed (user)", str(e))
                    return

            # Apply root knobs (with pkexec)
            if root_knobs:
                try:
                    result_root = _run_worker_apply_pkexec(root_knobs)
                    self.state["last_root_txid"] = result_root.get("txid")
                except Exception as e:
                    QMessageBox.critical(self, "Apply failed (root)", str(e))
                    return

            # Legacy field for backward compat
            self.state["last_txid"] = self.state.get("last_root_txid") or self.state.get("last_user_txid")
            save_state(self.state)

            msg = "Applied."
            if user_knobs:
                msg += f" User tx: {self.state.get('last_user_txid')}"
            if root_knobs:
                msg += f" Root tx: {self.state.get('last_root_txid')}"
            QMessageBox.information(self, "Applied", msg)

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

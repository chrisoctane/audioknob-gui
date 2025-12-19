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
    if not p.exists():
        return {"schema": 1, "last_txid": None, "last_user_txid": None, "last_root_txid": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # Migrate old state format
        if "last_txid" in data and "last_user_txid" not in data:
            data["last_root_txid"] = data.get("last_txid")
            data["last_user_txid"] = None
        return data
    except Exception:
        return {"schema": 1, "last_txid": None, "last_user_txid": None, "last_root_txid": None}


def save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
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
            self.resize(520, 180)
            self.ok = False

            root = QVBoxLayout(self)
            root.addWidget(QLabel("This will apply system changes as root. Type YES to continue."))
            root.addWidget(QLabel("Planned knobs: " + ", ".join(planned_ids)))

            from PySide6.QtWidgets import QLineEdit

            self.input = QLineEdit()
            self.input.setPlaceholderText("Type YES")
            root.addWidget(self.input)

            btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            btns.accepted.connect(self._on_ok)
            btns.rejected.connect(self.reject)
            root.addWidget(btns)

        def _on_ok(self) -> None:
            if self.input.text().strip() == "YES":
                self.ok = True
                self.accept()
            else:
                QMessageBox.warning(self, "Not confirmed", "Please type YES to apply.")

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("audioknob-gui")
            self.resize(980, 640)

            self.state = load_state()
            self.registry = load_registry(_registry_path())

            w = QWidget()
            self.setCentralWidget(w)
            root = QVBoxLayout(w)

            top = QHBoxLayout()
            top.addWidget(QLabel("Pick actions per knob, then Preview and Apply."))
            self.btn_preview = QPushButton("Preview")
            self.btn_apply = QPushButton("Apply")
            self.btn_undo = QPushButton("Undo last")
            self.btn_tests = QPushButton("Run jitter test")
            top.addStretch(1)
            top.addWidget(self.btn_tests)
            top.addWidget(self.btn_preview)
            top.addWidget(self.btn_apply)
            top.addWidget(self.btn_undo)
            root.addLayout(top)

            self.table = QTableWidget(0, 5)
            self.table.setHorizontalHeaderLabels(["Knob", "Description", "Category", "Risk", "Planned action"])
            self.table.horizontalHeader().setStretchLastSection(True)
            root.addWidget(self.table)

            self._populate()

            self.btn_tests.clicked.connect(self.on_tests)
            self.btn_preview.clicked.connect(self.on_preview)
            self.btn_apply.clicked.connect(self.on_apply)
            self.btn_undo.clicked.connect(self.on_undo)

        def _populate(self) -> None:
            self.table.setRowCount(len(self.registry))
            for r, k in enumerate(self.registry):
                self.table.setItem(r, 0, QTableWidgetItem(k.title))
                self.table.setItem(r, 1, QTableWidgetItem(k.description))
                self.table.setItem(r, 2, QTableWidgetItem(str(k.category)))
                self.table.setItem(r, 3, QTableWidgetItem(str(k.risk_level)))

                combo = QComboBox()
                combo.addItem("Keep current", userData="keep")
                if k.capabilities.apply:
                    combo.addItem("Apply optimization", userData="apply")
                if k.capabilities.restore:
                    combo.addItem("Restore original", userData="restore")
                self.table.setCellWidget(r, 4, combo)

        def _planned(self) -> list[PlannedAction]:
            out: list[PlannedAction] = []
            for r, k in enumerate(self.registry):
                combo = self.table.cellWidget(r, 4)
                assert isinstance(combo, QComboBox)
                action = str(combo.currentData())
                out.append(PlannedAction(knob_id=k.id, action=action))
            return out

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

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


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

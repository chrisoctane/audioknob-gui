from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QWidget

from audioknob_gui.gui.chrome import build_dialog_root, set_label_tone, style_dialog_button_box, style_panel_surface


class ConfirmDialog(QDialog):
    def __init__(self, planned_ids: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm queued changes")
        self.resize(540, 240)
        self.ok = False

        root = build_dialog_root(self, parent=parent, compact=True)
        title = QLabel("<b>Apply these queued changes?</b>")
        set_label_tone(title, "lead")
        root.addWidget(title)

        items = QTextEdit()
        items.setReadOnly(True)
        items.setPlainText("\n".join(f"- {item}" for item in planned_ids))
        items.setMaximumHeight(140)
        style_panel_surface(items)
        root.addWidget(items)

        hint = QLabel("<i>You'll be prompted for your password if root access is needed.</i>")
        set_label_tone(hint, "muted")
        root.addWidget(hint)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        style_dialog_button_box(btns)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_ok(self) -> None:
        self.ok = True
        self.accept()

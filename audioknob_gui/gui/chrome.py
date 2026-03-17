from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLayout, QPushButton, QVBoxLayout, QWidget


_PRIMARY_BUTTONS = (
    QDialogButtonBox.Ok,
    QDialogButtonBox.Open,
    QDialogButtonBox.Save,
    QDialogButtonBox.SaveAll,
    QDialogButtonBox.Apply,
    QDialogButtonBox.Yes,
)
_SUBTLE_BUTTONS = (
    QDialogButtonBox.Cancel,
    QDialogButtonBox.Close,
    QDialogButtonBox.No,
    QDialogButtonBox.Help,
)
_WARNING_BUTTONS = (
    QDialogButtonBox.Discard,
    QDialogButtonBox.Reset,
    QDialogButtonBox.Abort,
)


def _find_style_source(widget: QWidget | None) -> QWidget | None:
    current = widget
    while current is not None:
        try:
            if current.styleSheet():
                return current
        except Exception:
            pass
        current = current.parentWidget()
    return None


def apply_dialog_chrome(dialog: QDialog, parent: QWidget | None = None) -> None:
    source = _find_style_source(parent if parent is not None else dialog.parentWidget())
    if source is None:
        return
    try:
        dialog.setStyleSheet(source.styleSheet())
    except Exception:
        pass


def configure_dialog_layout(layout: QLayout, *, compact: bool = False) -> None:
    if compact:
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        return
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)


def build_dialog_root(
    dialog: QDialog,
    *,
    parent: QWidget | None = None,
    compact: bool = False,
) -> QVBoxLayout:
    apply_dialog_chrome(dialog, parent=parent)
    root = QVBoxLayout(dialog)
    configure_dialog_layout(root, compact=compact)
    return root


def set_button_role(button: QPushButton | None, role: str) -> None:
    if button is None:
        return
    button.setProperty("role", role)


def style_dialog_button_box(buttons: QDialogButtonBox) -> None:
    for standard in _PRIMARY_BUTTONS:
        set_button_role(buttons.button(standard), "primary")
    for standard in _SUBTLE_BUTTONS:
        set_button_role(buttons.button(standard), "subtle")
    for standard in _WARNING_BUTTONS:
        set_button_role(buttons.button(standard), "warning")


def set_label_tone(label: QLabel, tone: str, *, wrap: bool = True) -> None:
    label.setProperty("tone", tone)
    if wrap:
        label.setWordWrap(True)


def style_panel_surface(widget: QWidget) -> None:
    widget.setProperty("surface", "panel")


def style_section_box(widget: QWidget) -> None:
    widget.setProperty("card", True)

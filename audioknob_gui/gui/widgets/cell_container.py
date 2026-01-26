from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget


class CellContainer(QWidget):
    def __init__(self, bg: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bg = QColor(bg)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.set_bg(self._bg)

    def set_bg(self, bg: QColor) -> None:
        self._bg = QColor(bg)
        self.setStyleSheet(f"background-color: {self._bg.name()};")

    def content_widget(self) -> QWidget | None:
        layout = self.layout()
        if layout is None or layout.count() == 0:
            return None
        item = layout.itemAt(0)
        if item is None:
            return None
        return item.widget()

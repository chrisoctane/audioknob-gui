from __future__ import annotations

import sys


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
            QMenu,
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
        from PySide6.QtGui import QColor, QCursor, QPainter, QPalette
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

    from audioknob_gui.gui.main_window import run_app

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
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

    app = QApplication(sys.argv)

    win = QMainWindow()
    win.setWindowTitle("audioknob-gui (skeleton)")
    win.setCentralWidget(QLabel("Skeleton app. Next: knobs, preview, apply."))
    win.resize(700, 400)
    win.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

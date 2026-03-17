from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from audioknob_gui.gui.chrome import (
    build_dialog_root,
    set_button_role,
    set_label_tone,
    style_dialog_button_box,
    style_section_box,
)


class CpuCoreDialog(QDialog):
    def __init__(
        self,
        *,
        cpu_count: int,
        selected: set[int],
        allow_auto: bool = False,
        auto_enabled: bool = False,
        auto_label: str | None = None,
        auto_hint: str | None = None,
        title: str | None = None,
        lines: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "Configure CPU cores for JACK")
        self.resize(520, 320)

        self._cpu_count = max(1, int(cpu_count))
        self._checks: list[QCheckBox] = []
        self._auto_cb: QCheckBox | None = None
        self._auto_hint: QLabel | None = None

        root = build_dialog_root(self, parent=parent)
        if lines is None:
            lines = [
                "Select CPU cores to pin JACK to (taskset -c).",
                "Tip: cores 0-1 are often busiest (IRQs/system tasks).",
            ]
        for line in lines:
            label = QLabel(line)
            set_label_tone(label, "muted")
            root.addWidget(label)

        if allow_auto:
            label = auto_label or "Auto"
            hint = auto_hint or "Auto uses all cores except selected audio cores."
            self._auto_cb = QCheckBox(label)
            self._auto_cb.setChecked(bool(auto_enabled))
            root.addWidget(self._auto_cb)
            self._auto_hint = QLabel(hint)
            set_label_tone(self._auto_hint, "muted")
            root.addWidget(self._auto_hint)

        selection_box = QGroupBox("CPU cores")
        style_section_box(selection_box)
        selection_layout = QVBoxLayout(selection_box)
        selection_layout.setContentsMargins(14, 18, 14, 14)
        selection_layout.setSpacing(10)

        grid_wrap = QWidget()
        grid = QGridLayout(grid_wrap)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        cols = 4
        for core in range(self._cpu_count):
            cb = QCheckBox(f"Core {core}")
            cb.setChecked(core in selected)
            self._checks.append(cb)
            grid.addWidget(cb, core // cols, core % cols)

        selection_layout.addWidget(grid_wrap)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("Select all")
        btn_none = QPushButton("Clear all")
        set_button_role(btn_all, "subtle")
        set_button_role(btn_none, "subtle")
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch(1)
        selection_layout.addLayout(btn_row)
        root.addWidget(selection_box)

        def _set_all(v: bool) -> None:
            for cb in self._checks:
                cb.setChecked(v)

        btn_all.clicked.connect(lambda: _set_all(True))
        btn_none.clicked.connect(lambda: _set_all(False))

        if self._auto_cb is not None:
            def _apply_auto(enabled: bool) -> None:
                for cb in self._checks:
                    cb.setEnabled(not enabled)
                btn_all.setEnabled(not enabled)
                btn_none.setEnabled(not enabled)

            self._auto_cb.toggled.connect(_apply_auto)
            _apply_auto(self._auto_cb.isChecked())

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        style_dialog_button_box(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def selected_cores(self) -> list[int]:
        out: list[int] = []
        for i, cb in enumerate(self._checks):
            if cb.isChecked():
                out.append(i)
        return out

    def auto_enabled(self) -> bool:
        if self._auto_cb is None:
            return False
        return self._auto_cb.isChecked()

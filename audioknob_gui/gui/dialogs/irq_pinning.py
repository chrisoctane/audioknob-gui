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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from audioknob_gui.gui.chrome import (
    build_dialog_root,
    set_button_role,
    set_label_tone,
    style_dialog_button_box,
    style_panel_surface,
    style_section_box,
)


class IrqPinningDialog(QDialog):
    def __init__(
        self,
        *,
        cpu_count: int,
        selected_cores: set[int],
        devices: list[dict[str, object]],
        selected_devices: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure IRQ pinning")
        self.resize(620, 520)

        self._cpu_count = max(1, int(cpu_count))
        self._core_checks: list[QCheckBox] = []
        self._device_checks: dict[str, QCheckBox] = {}

        root = build_dialog_root(self, parent=parent)
        intro = QLabel("Select audio devices to pin their IRQs.")
        set_label_tone(intro, "muted")
        root.addWidget(intro)
        usb_hint = QLabel("USB devices pin the host controller IRQs, which may be shared.")
        set_label_tone(usb_hint, "muted")
        root.addWidget(usb_hint)
        try:
            from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups

            groups = read_thread_sibling_groups()
            if any(len(g) > 1 for g in groups):
                logical = len(read_cpu_present() or [])
                physical = len(groups)
                smt_hint = QLabel(
                    f"SMT detected: {physical} physical / {logical} logical. "
                    "Select both siblings for best isolation."
                )
                set_label_tone(smt_hint, "muted")
                root.addWidget(smt_hint)
        except Exception:
            pass

        device_box = QGroupBox("Devices")
        style_section_box(device_box)
        device_layout = QVBoxLayout(device_box)
        device_layout.setContentsMargins(14, 18, 14, 14)
        device_layout.setSpacing(10)
        device_scroll = QScrollArea()
        device_scroll.setWidgetResizable(True)
        style_panel_surface(device_scroll)
        device_container = QWidget()
        device_container_layout = QVBoxLayout(device_container)
        device_container_layout.setContentsMargins(12, 12, 12, 12)
        device_container_layout.setSpacing(10)

        for device in devices:
            key = str(device.get("key"))
            label = str(device.get("label") or key)
            bus = str(device.get("bus") or "unknown")
            irqs = device.get("irqs") or []
            warning = device.get("warning")
            controller = device.get("controller_pci_id")
            driver = device.get("controller_driver")
            extra: list[str] = []
            if controller:
                ctrl = f"controller {controller}"
                if driver:
                    ctrl += f" ({driver})"
                extra.append(ctrl)
            if irqs:
                extra.append("IRQs: " + ",".join(str(x) for x in irqs))
            if warning:
                extra.append(f"WARNING: {warning}")

            text = f"{label} [{bus}]"
            if extra:
                text += " - " + "; ".join(extra)

            cb = QCheckBox(text)
            cb.setChecked(key in selected_devices)
            if not irqs:
                cb.setEnabled(False)
                cb.setToolTip("No IRQs detected for this device.")
            self._device_checks[key] = cb
            device_container_layout.addWidget(cb)

        device_container_layout.addStretch(1)
        device_scroll.setWidget(device_container)
        device_layout.addWidget(device_scroll)
        root.addWidget(device_box)

        core_box = QGroupBox("CPU cores")
        style_section_box(core_box)
        core_layout = QVBoxLayout(core_box)
        core_layout.setContentsMargins(14, 18, 14, 14)
        core_layout.setSpacing(10)
        core_hint = QLabel("Select CPU cores to pin IRQs to.")
        set_label_tone(core_hint, "muted")
        core_layout.addWidget(core_hint)

        grid_wrap = QWidget()
        grid = QGridLayout(grid_wrap)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        cols = 4
        for core in range(self._cpu_count):
            cb = QCheckBox(f"Core {core}")
            cb.setChecked(core in selected_cores)
            self._core_checks.append(cb)
            grid.addWidget(cb, core // cols, core % cols)

        core_layout.addWidget(grid_wrap)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("Select all")
        btn_none = QPushButton("Clear all")
        set_button_role(btn_all, "subtle")
        set_button_role(btn_none, "subtle")
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch(1)
        core_layout.addLayout(btn_row)

        def _set_all(v: bool) -> None:
            for cb in self._core_checks:
                cb.setChecked(v)

        btn_all.clicked.connect(lambda: _set_all(True))
        btn_none.clicked.connect(lambda: _set_all(False))
        root.addWidget(core_box)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        style_dialog_button_box(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def selected_core_list(self) -> list[int]:
        out: list[int] = []
        for i, cb in enumerate(self._core_checks):
            if cb.isChecked():
                out.append(i)
        return out

    def selected_device_keys(self) -> list[str]:
        out: list[str] = []
        for key, cb in self._device_checks.items():
            if cb.isChecked():
                out.append(key)
        return out

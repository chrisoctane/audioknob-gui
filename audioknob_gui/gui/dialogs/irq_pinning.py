from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
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
        if parent is not None:
            self.setStyleSheet(parent.styleSheet())
        self.setWindowTitle("Configure IRQ pinning")
        self.resize(620, 520)

        self._cpu_count = max(1, int(cpu_count))
        self._core_checks: list[QCheckBox] = []
        self._device_checks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Select audio devices to pin their IRQs."))
        root.addWidget(QLabel("USB devices pin the host controller IRQs (shared)."))
        try:
            from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups

            groups = read_thread_sibling_groups()
            if any(len(g) > 1 for g in groups):
                logical = len(read_cpu_present() or [])
                physical = len(groups)
                root.addWidget(
                    QLabel(
                        f"SMT detected: {physical} physical / {logical} logical. "
                        "Select both siblings for best isolation."
                    )
                )
        except Exception:
            pass

        device_box = QGroupBox("Devices")
        device_layout = QVBoxLayout(device_box)
        device_scroll = QScrollArea()
        device_scroll.setWidgetResizable(True)
        device_container = QWidget()
        device_container.setAutoFillBackground(True)
        device_palette = device_container.palette()
        device_palette.setColor(QPalette.Window, QColor("#1f1f1f"))
        device_container.setPalette(device_palette)
        device_container_layout = QVBoxLayout(device_container)

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
        core_layout = QVBoxLayout(core_box)
        core_layout.addWidget(QLabel("Select CPU cores to pin IRQs to."))

        grid_wrap = QWidget()
        grid = QGridLayout(grid_wrap)

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

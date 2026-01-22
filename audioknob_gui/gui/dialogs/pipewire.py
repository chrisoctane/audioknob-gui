from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


class PipeWireQuantumDialog(QDialog):
    def __init__(self, current: int | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure PipeWire buffer (quantum)")
        self.resize(420, 160)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Select PipeWire buffer size (quantum)."))
        root.addWidget(QLabel("Recommended: 128 or 256. Smaller can underrun; larger adds latency."))

        self.combo = QComboBox()
        self._values = [32, 64, 128, 256, 512, 1024]
        for v in self._values:
            self.combo.addItem(str(v), v)
        if current in self._values:
            self.combo.setCurrentIndex(self._values.index(current))
        root.addWidget(self.combo)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def selected_value(self) -> int:
        return int(self.combo.currentData())


class PipeWireSampleRateDialog(QDialog):
    def __init__(self, current: int | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure PipeWire sample rate")
        self.resize(420, 160)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Select PipeWire default sample rate."))
        root.addWidget(QLabel("Common: 48000 Hz. Higher rates for high-res audio."))

        self.combo = QComboBox()
        self._values = [44100, 48000, 88200, 96000, 192000]
        for v in self._values:
            self.combo.addItem(f"{v} Hz", v)
        if current in self._values:
            self.combo.setCurrentIndex(self._values.index(current))
        root.addWidget(self.combo)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def selected_value(self) -> int:
        return int(self.combo.currentData())

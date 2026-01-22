from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QMessageBox, QPushButton, QSizePolicy, QWidget

from audioknob_gui.gui.dialogs.pipewire import PipeWireQuantumDialog, PipeWireSampleRateDialog
from audioknob_gui.gui.state import save_state


def build_quantum_combo(ui, knob, ctx) -> QComboBox | None:
    if ctx.locked:
        return None
    combo = QComboBox()
    combo.setMinimumWidth(0)
    combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
    values = [32, 64, 128, 256, 512, 1024]
    for v in values:
        combo.addItem(str(v), v)

    current = ui._pipewire_quantum_from_state()
    if current is None and knob.impl:
        try:
            current = int(knob.impl.params.get("quantum")) if knob.impl.params.get("quantum") is not None else None
        except Exception:
            current = None
    combo.blockSignals(True)
    if current in values:
        combo.setCurrentIndex(values.index(int(current)))
    combo.blockSignals(False)

    def _on_change(_: int, *, _combo: QComboBox = combo) -> None:
        # Capture the correct combo; otherwise a later reassignment can cause late-binding bugs.
        ui.state["pipewire_quantum"] = int(_combo.currentData())
        save_state(ui.state)
        # Optimistic UI: config changed, so action should become Apply until proven otherwise.
        ui._knob_statuses["pipewire_quantum"] = "not_applied"
        ui._refresh_statuses()
        ui._populate()

    combo.currentIndexChanged.connect(_on_change)
    return combo


def build_sample_rate_combo(ui, knob, ctx) -> QComboBox | None:
    if ctx.locked:
        return None
    combo = QComboBox()
    combo.setMinimumWidth(0)
    combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
    values = [44100, 48000, 88200, 96000, 192000]
    for v in values:
        combo.addItem(f"{v} Hz", v)

    current = ui._pipewire_sample_rate_from_state()
    if current is None and knob.impl:
        try:
            current = int(knob.impl.params.get("rate")) if knob.impl.params.get("rate") is not None else None
        except Exception:
            current = None
    combo.blockSignals(True)
    if current in values:
        combo.setCurrentIndex(values.index(int(current)))
    combo.blockSignals(False)

    def _on_change(_: int, *, _combo: QComboBox = combo) -> None:
        ui.state["pipewire_sample_rate"] = int(_combo.currentData())
        save_state(ui.state)
        ui._knob_statuses["pipewire_sample_rate"] = "not_applied"
        ui._refresh_statuses()
        ui._populate()

    combo.currentIndexChanged.connect(_on_change)
    return combo


def configure_quantum_dialog(ui) -> None:
    current = ui._pipewire_quantum_from_state() or 256
    dialog = PipeWireQuantumDialog(current=current, parent=ui)
    if dialog.exec() != dialog.Accepted:
        return
    chosen = dialog.selected_value()
    ui.state["pipewire_quantum"] = chosen
    save_state(ui.state)
    QMessageBox.information(
        ui,
        "Saved",
        f"Saved PipeWire quantum = {chosen}. Apply the PipeWire knob to take effect.",
    )


def configure_sample_rate_dialog(ui) -> None:
    current = ui._pipewire_sample_rate_from_state() or 48000
    dialog = PipeWireSampleRateDialog(current=current, parent=ui)
    if dialog.exec() != dialog.Accepted:
        return
    chosen = dialog.selected_value()
    ui.state["pipewire_sample_rate"] = chosen
    save_state(ui.state)
    QMessageBox.information(
        ui,
        "Saved",
        f"Saved PipeWire sample rate = {chosen} Hz. Apply the PipeWire knob to take effect.",
    )


def apply_param_overrides(ui, knob, params: dict) -> None:
    if knob.id == "pipewire_quantum":
        quantum = ui._pipewire_quantum_from_state()
        if quantum is not None:
            params["quantum"] = quantum
    if knob.id == "pipewire_sample_rate":
        rate = ui._pipewire_sample_rate_from_state()
        if rate is not None:
            params["rate"] = rate


def add_info_buttons(ui, knob, dialog: QWidget, layout) -> None:
    if knob.id == "pipewire_quantum":
        config_btn = QPushButton("Configure Buffer Size...")
        config_btn.clicked.connect(lambda: (dialog.accept(), ui.on_configure_knob(knob.id)))
        layout.addWidget(config_btn)
    if knob.id == "pipewire_sample_rate":
        config_btn = QPushButton("Configure Sample Rate...")
        config_btn.clicked.connect(lambda: (dialog.accept(), ui.on_configure_knob(knob.id)))
        layout.addWidget(config_btn)

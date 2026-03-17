"""GUI helpers for the ALSA XRUN Monitor knob."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QPushButton, QSizePolicy

from audioknob_gui.gui.dialogs.alsa_xrun import list_alsa_cards


def build_alsa_xrun_action(ui, knob, ctx):
    """Build the 'Monitor' action button for the ALSA XRUN Monitor knob."""
    btn = ui._make_action_button("Monitor")
    if ctx.busy:
        btn.setEnabled(False)
    else:
        btn.clicked.connect(ui.on_open_alsa_xrun_monitor)
    ui._apply_busy_state(btn, busy=ctx.busy)
    return btn


def build_alsa_xrun_config(ui, knob, ctx):
    """Build a card-selector combo for the config column."""
    combo = QComboBox()
    combo.setMinimumWidth(0)
    combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
    combo.setMinimumContentsLength(12)
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    for card in list_alsa_cards():
        label = f"card{card['index']}: {card['id']}"
        combo.addItem(label, card["index"])
    # Restore previous selection from state.
    saved = ui.state.get("alsa_xrun_card_index")
    if saved is not None:
        for i in range(combo.count()):
            if combo.itemData(i) == int(saved):
                combo.setCurrentIndex(i)
                break
    combo.currentIndexChanged.connect(
        lambda _: _on_card_changed(ui, combo)
    )
    return combo


def _on_card_changed(ui, combo: QComboBox) -> None:
    idx = combo.currentIndex()
    if idx >= 0:
        ui.state["alsa_xrun_card_index"] = int(combo.itemData(idx))
        ui._save_state()

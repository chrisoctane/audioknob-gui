from __future__ import annotations

import re
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QWidget,
)

from audioknob_gui.gui.dialogs.keep_above import configure_on_top_checkbox
from audioknob_gui.gui.chrome import (
    build_dialog_root,
    set_button_role,
    set_label_tone,
    style_dialog_button_box,
    style_panel_surface,
)


def list_alsa_cards() -> list[dict[str, object]]:
    """Enumerate ALSA cards from /proc/asound/cards."""
    cards_path = Path("/proc/asound/cards")
    if not cards_path.exists():
        return []
    cards: list[dict[str, object]] = []
    for line in cards_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\d+)\s+\[(\S+)\s*\]:\s*(.*)", line)
        if m:
            cards.append({
                "index": int(m.group(1)),
                "id": m.group(2),
                "description": m.group(3).strip(),
            })
    return cards


def _read_pcm_status(pcm_dir: Path) -> dict[str, str]:
    """Read status fields from a PCM subdevice."""
    status_file = pcm_dir / "sub0" / "status"
    result: dict[str, str] = {}
    if not status_file.exists():
        return result
    try:
        for line in status_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("---"):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                result[key.strip()] = val.strip()
    except Exception:
        pass
    return result


def _read_hw_params(pcm_dir: Path) -> dict[str, str]:
    """Read hw_params from a PCM subdevice."""
    hw_file = pcm_dir / "sub0" / "hw_params"
    result: dict[str, str] = {}
    if not hw_file.exists():
        return result
    try:
        text = hw_file.read_text(encoding="utf-8").strip()
        if text == "closed":
            result["state"] = "closed"
            return result
        for line in text.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                result[key.strip()] = val.strip()
    except Exception:
        pass
    return result


def _find_pcm_devices(card_index: int) -> list[dict[str, object]]:
    """Find all PCM devices for a card with their current data."""
    card_dir = Path(f"/proc/asound/card{card_index}")
    if not card_dir.exists():
        return []
    devices: list[dict[str, object]] = []
    for pcm_dir in sorted(card_dir.glob("pcm*")):
        name = pcm_dir.name
        direction = "playback" if name.endswith("p") else "capture" if name.endswith("c") else "unknown"
        status = _read_pcm_status(pcm_dir)
        hw = _read_hw_params(pcm_dir)
        state = status.get("state", hw.get("state", "unknown"))
        xrun_count = 0
        if "xrun_counter" in status:
            try:
                xrun_count = int(status["xrun_counter"])
            except ValueError:
                pass
        rate = hw.get("rate", "")
        if rate and " " in rate:
            rate = rate.split()[0]
        devices.append({
            "name": name,
            "direction": direction,
            "state": state,
            "xrun_count": xrun_count,
            "rate": rate,
            "period_size": hw.get("period_size", ""),
            "buffer_size": hw.get("buffer_size", ""),
            "delay": status.get("delay", ""),
            "avail": status.get("avail", ""),
            "avail_max": status.get("avail_max", ""),
            "format": hw.get("format", ""),
            "channels": hw.get("channels", ""),
        })
    return devices


class AlsaXrunMonitorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ALSA XRUN Monitor")
        self.resize(420, 260)

        root = build_dialog_root(self, parent=parent)

        intro = QLabel("Track ALSA XRUN counters and live PCM device state.")
        set_label_tone(intro, "muted")
        root.addWidget(intro)

        # Device selector
        card_row = QHBoxLayout()
        card_row.setSpacing(8)
        card_row.addWidget(QLabel("Card:"))
        self.card_combo = QComboBox()
        self.card_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        card_row.addWidget(self.card_combo, 1)
        root.addLayout(card_row)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.status_label = QLabel("Status: idle | Last update: —")
        set_label_tone(self.status_label, "muted")
        root.addWidget(self.status_label)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QTextEdit.NoWrap)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        style_panel_surface(self.output)
        root.addWidget(self.output)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.refresh_btn = QPushButton("Refresh")
        self.reset_btn = QPushButton("Reset Count")
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        set_button_role(self.refresh_btn, "subtle")
        set_button_role(self.reset_btn, "subtle")
        set_button_role(self.start_btn, "primary")
        set_button_role(self.stop_btn, "warning")
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.reset_btn)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        self.on_top_toggle = QCheckBox("Always on top")
        btn_row.addWidget(self.on_top_toggle)
        configure_on_top_checkbox(self, self.on_top_toggle)
        self.expand_btn = QPushButton("Full View")
        set_button_role(self.expand_btn, "subtle")
        self.expand_btn.setToolTip("Show more device details")
        self.expand_btn.clicked.connect(self._toggle_view)
        btn_row.addWidget(self.expand_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        style_dialog_button_box(btns)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)

        self.refresh_btn.clicked.connect(self._refresh)
        self.reset_btn.clicked.connect(self._reset_count)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.card_combo.currentIndexChanged.connect(self._on_card_changed)

        self._running = False
        self._compact = True
        self._last_update: float | None = None
        self._baseline_totals: dict[str, int] = {}

        self._update_expand_button()
        self._populate_cards()
        self._refresh()

    def _populate_cards(self) -> None:
        self.card_combo.blockSignals(True)
        self.card_combo.clear()
        for card in list_alsa_cards():
            label = f"{card['description']} (card{card['index']})"
            self.card_combo.addItem(label, card["index"])
        self.card_combo.blockSignals(False)

    def _selected_card_index(self) -> int | None:
        idx = self.card_combo.currentIndex()
        if idx < 0:
            return None
        return int(self.card_combo.itemData(idx))

    def _toggle_view(self) -> None:
        self._compact = not self._compact
        if self._compact:
            self.resize(420, 260)
        else:
            self.resize(700, 400)
        self._update_expand_button()
        self._refresh()

    def _update_expand_button(self) -> None:
        if self._compact:
            self.expand_btn.setText("Full View")
            self.expand_btn.setToolTip("Show more device details")
        else:
            self.expand_btn.setText("Compact View")
            self.expand_btn.setToolTip("Return to the compact monitor")

    def _update_status(self) -> None:
        state = "running" if self._running else "idle"
        if self._last_update is None:
            last = "\u2014"
        else:
            last = time.strftime("%H:%M:%S", time.localtime(self._last_update))
        self.status_label.setText(f"Status: {state} | Last update: {last}")

    def _start(self) -> None:
        self._timer.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._running = True
        self._update_status()

    def _stop(self) -> None:
        self._timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._running = False
        self._update_status()

    def _on_card_changed(self) -> None:
        self._baseline_totals.clear()
        self._refresh()

    def _refresh(self) -> None:
        card_index = self._selected_card_index()
        if card_index is None:
            self.summary.setText("No ALSA cards found.")
            self.output.setPlainText("")
            self._last_update = time.time()
            self._update_status()
            return

        devices = _find_pcm_devices(card_index)
        if not devices:
            self.summary.setText(f"No PCM devices found for card{card_index}.")
            self.output.setPlainText("")
            self._last_update = time.time()
            self._update_status()
            return

        # Compute totals
        total_xruns = sum(int(d["xrun_count"]) for d in devices)
        active = [d for d in devices if d["state"] not in ("closed", "unknown")]
        baseline = sum(self._baseline_totals.get(str(d["name"]), 0) for d in devices)
        display_total = total_xruns - baseline

        label = "Total xruns (since reset):" if baseline else "Total xruns:"
        active_count = len(active)
        self.summary.setText(f"{label} {display_total} | Active streams: {active_count}")

        if self._compact:
            self._render_compact(devices)
        else:
            self._render_full(devices)

        self._last_update = time.time()
        self._update_status()

    def _render_compact(self, devices: list[dict[str, object]]) -> None:
        lines: list[str] = []
        for d in devices:
            if str(d["state"]) == "closed":
                continue
            direction = "Play" if d["direction"] == "playback" else "Cap "
            xruns = int(d["xrun_count"]) - self._baseline_totals.get(str(d["name"]), 0)
            rate = d["rate"] or "-"
            period = d["period_size"] or "-"
            buf = d["buffer_size"] or "-"
            lines.append(
                f"  {direction}: {d['state']:<9}  Xruns: {xruns:<5}  "
                f"Rate: {rate}  Period: {period}  Buffer: {buf}"
            )
        if not lines:
            lines.append("  No active streams")
        self.output.setPlainText("\n".join(lines))

    def _render_full(self, devices: list[dict[str, object]]) -> None:
        header = f"{'PCM':<8} {'DIR':<5} {'STATE':<10} {'XRUNS':>6} {'RATE':>6} {'PERIOD':>7} {'BUFFER':>7} {'DELAY':>6} {'AVAIL':>6}"
        lines = [header]
        for d in devices:
            xruns = int(d["xrun_count"]) - self._baseline_totals.get(str(d["name"]), 0)
            rate = str(d["rate"]) or "-"
            period = str(d["period_size"]) or "-"
            buf = str(d["buffer_size"]) or "-"
            delay = str(d["delay"]) or "-"
            avail = str(d["avail"]) or "-"
            state = str(d["state"])
            direction = "play" if d["direction"] == "playback" else "cap" if d["direction"] == "capture" else "?"
            lines.append(
                f"{d['name']:<8} {direction:<5} {state:<10} {xruns:>6} {rate:>6} {period:>7} {buf:>7} {delay:>6} {avail:>6}"
            )
        self.output.setPlainText("\n".join(lines))

    def _reset_count(self) -> None:
        card_index = self._selected_card_index()
        if card_index is None:
            return
        devices = _find_pcm_devices(card_index)
        for d in devices:
            self._baseline_totals[str(d["name"])] = int(d["xrun_count"])
        self._refresh()

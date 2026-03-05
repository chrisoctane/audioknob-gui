from __future__ import annotations

import json
import subprocess
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)


class XrunMonitorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire XRUN Monitor")
        self.resize(700, 480)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Live XRUN/ERR counter via pw-top (batch mode)."))

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.status = QLabel("Status: idle | Last update: —")
        root.addWidget(self.status)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QTextEdit.NoWrap)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        root.addWidget(self.output)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.reset_btn = QPushButton("Reset Count")
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.reset_btn)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        self.on_top_toggle = QCheckBox("Always on top")
        self.on_top_toggle.toggled.connect(self._set_always_on_top)
        btn_row.addWidget(self.on_top_toggle)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        root.addWidget(btns)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)

        self.refresh_btn.clicked.connect(self._refresh)
        self.reset_btn.clicked.connect(self._reset_count)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

        self._running = False
        self._last_total: int | None = None
        self._last_ts: float | None = None
        self._last_update: float | None = None
        self._baseline_total: int | None = None
        self._current_total: int | None = None
        self._refresh()

    def _set_always_on_top(self, enabled: bool) -> None:
        flags = self.windowFlags()
        if enabled:
            # Qt.Window promotes to a true top-level window so the hint
            # applies above all desktop windows, not just the parent app.
            flags |= Qt.Window | Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        # Re-show to apply window flag changes on all WMs.
        self.show()
        self.raise_()
        self.activateWindow()

    def _update_status(self) -> None:
        state = "running" if self._running else "idle"
        if self._last_update is None:
            last = "—"
        else:
            last = time.strftime("%H:%M:%S", time.localtime(self._last_update))
        self.status.setText(f"Status: {state} | Last update: {last}")

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

    def _refresh(self) -> None:
        try:
            result = subprocess.run(
                ["pw-top", "-b", "-n", "2"],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception as exc:
            self.summary.setText(f"pw-top failed: {exc}")
            self._last_update = time.time()
            self._update_status()
            return
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or "pw-top failed"
            self.summary.setText(err)
            self._last_update = time.time()
            self._update_status()
            return

        output = _last_pw_top_table(result.stdout or "")
        total, rows, qr_note, quant_nonzero = _parse_pw_top(output)
        self._current_total = total
        patched = False
        if not quant_nonzero:
            patched_output, did_patch = _patch_pw_top_quant_rate(output)
            if did_patch:
                output = patched_output
                patched = True
                total, rows, qr_note, _ = _parse_pw_top(output)
                self._current_total = total
        now = time.time()
        rate = ""
        if total is not None:
            if (
                self._baseline_total is not None
                and total < self._baseline_total
            ):
                self._baseline_total = total
            if self._last_total is not None and self._last_ts is not None:
                delta = total - self._last_total
                dt = max(0.001, now - self._last_ts)
                rate = f" (Δ {delta} / {dt:.1f}s)"
            self._last_total = total
            self._last_ts = now
        if total is None:
            self.summary.setText("ERR column not detected in pw-top output.")
        else:
            extra = f" {qr_note}" if qr_note else ""
            if patched:
                extra += " (QUANT/RATE filled from pw-dump)"
            display_total = (
                total - self._baseline_total
                if self._baseline_total is not None
                else total
            )
            label = (
                "Total ERR (since reset):"
                if self._baseline_total is not None
                else "Total ERR:"
            )
            self.summary.setText(f"{label} {display_total}{rate}{extra}")
        if rows:
            summary_lines = ["ERR > 0:", f"{'ERR':>4}  {'ID':>4}  NAME"]
            for err_val, node_id, name in rows[:12]:
                summary_lines.append(f"{err_val:>4}  {node_id:>4}  {name}")
            self.output.setPlainText("\n".join(summary_lines) + "\n\n" + output)
        else:
            self.output.setPlainText(output)
        self._last_update = now
        self._update_status()

    def _reset_count(self) -> None:
        if self._current_total is None:
            return
        self._baseline_total = self._current_total
        self._refresh()


def _parse_pw_top(
    output: str,
) -> tuple[int | None, list[tuple[int, int, str]], str | None, bool]:
    lines = output.splitlines()
    header_idx = None
    for idx, line in enumerate(lines):
        if "ERR" in line and "ID" in line:
            header_idx = idx
            break
    if header_idx is None:
        return None, [], None, False
    header = lines[header_idx]
    err_pos = header.find("ERR")
    if err_pos < 0:
        return None, [], None, False
    quant_rate_nonzero = False
    # Find next column start after ERR for slicing.
    col_positions = []
    for token in header.split():
        pos = header.find(token)
        if pos >= 0:
            col_positions.append(pos)
    col_positions = sorted(set(col_positions))
    err_end = len(header)
    for pos in col_positions:
        if pos > err_pos:
            err_end = pos
            break
    name_pos = header.find("NAME")
    if name_pos < 0:
        name_pos = None
    total = 0
    rows: list[tuple[int, int, str]] = []
    for line in lines[header_idx + 1 :]:
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith("+"):
            continue
        parts = line.split()
        if len(parts) >= 4:
            try:
                quant_val = int(parts[2])
                rate_val = int(parts[3])
                if quant_val > 0 or rate_val > 0:
                    quant_rate_nonzero = True
            except Exception:
                pass
        if err_pos >= len(line):
            continue
        err_raw = line[err_pos:err_end].strip()
        try:
            err_val = int(err_raw)
        except Exception:
            continue
        total += err_val
        if err_val > 0:
            node_id = -1
            if len(parts) > 1:
                try:
                    node_id = int(parts[1])
                except Exception:
                    node_id = -1
            if name_pos is not None and name_pos < len(line):
                name = line[name_pos:].strip()
            else:
                name = parts[-1] if parts else ""
            rows.append((err_val, node_id, name))
    note = None
    if not quant_rate_nonzero and total is not None:
        note = "(QUANT/RATE are 0; start audio to see live values)"
    return total, rows, note, quant_rate_nonzero


def _last_pw_top_table(output: str) -> str:
    lines = output.splitlines()
    header_indices = [
        idx for idx, line in enumerate(lines) if "ERR" in line and "ID" in line
    ]
    if not header_indices:
        return output
    start = header_indices[-1]
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if "ERR" in line and "ID" in line:
            end = idx
            break
    return "\n".join(lines[start:end])


def _patch_pw_top_quant_rate(output: str) -> tuple[str, bool]:
    lines = output.splitlines()
    header_idx = None
    for idx, line in enumerate(lines):
        if "ERR" in line and "ID" in line and "QUANT" in line and "RATE" in line:
            header_idx = idx
            break
    if header_idx is None:
        return output, False
    header = lines[header_idx]
    positions = _column_positions(header)
    quant_pos = positions.get("QUANT")
    rate_pos = positions.get("RATE")
    wait_pos = positions.get("WAIT")
    if quant_pos is None or rate_pos is None or wait_pos is None:
        return output, False
    quant_width = max(1, rate_pos - quant_pos)
    rate_width = max(1, wait_pos - rate_pos)
    latency_map = _pw_dump_latency_map()
    if not latency_map:
        return output, False
    patched_lines = list(lines)
    did_patch = False
    for idx in range(header_idx + 1, len(lines)):
        line = lines[idx]
        raw = line.strip()
        if not raw or raw.startswith("+"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        state = parts[0]
        if not state.isalpha() or len(state) != 1:
            continue
        try:
            node_id = int(parts[1])
        except Exception:
            continue
        mapped = latency_map.get(node_id)
        if not mapped:
            continue
        quant_val, rate_val = mapped
        if quant_val <= 0 or rate_val <= 0:
            continue
        line_chars = list(line)
        needed_len = wait_pos + 1
        if len(line_chars) < needed_len:
            line_chars.extend([" "] * (needed_len - len(line_chars)))
        quant_text = f"{quant_val:>{quant_width}}"
        rate_text = f"{rate_val:>{rate_width}}"
        line_chars[quant_pos : quant_pos + quant_width] = list(quant_text)
        line_chars[rate_pos : rate_pos + rate_width] = list(rate_text)
        patched_lines[idx] = "".join(line_chars)
        did_patch = True
    if not did_patch:
        return output, False
    return "\n".join(patched_lines), True


def _column_positions(header: str) -> dict[str, int]:
    positions: dict[str, int] = {}
    cursor = 0
    for token in header.split():
        pos = header.find(token, cursor)
        if pos >= 0:
            positions[token] = pos
            cursor = pos + len(token)
    return positions


def _pw_dump_latency_map() -> dict[int, tuple[int, int]]:
    try:
        raw = subprocess.check_output(["pw-dump"], text=True, timeout=3)
        data = json.loads(raw)
    except Exception:
        return {}
    latency_map: dict[int, tuple[int, int]] = {}
    for obj in data:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        node_id = obj.get("id")
        if not isinstance(node_id, int):
            continue
        props = (obj.get("info") or {}).get("props") or {}
        latency = props.get("node.latency")
        if not isinstance(latency, str) or "/" not in latency:
            continue
        try:
            quant_s, rate_s = latency.split("/", 1)
            quant_val = int(quant_s.strip())
            rate_val = int(rate_s.strip())
        except Exception:
            continue
        latency_map[node_id] = (quant_val, rate_val)
    return latency_map

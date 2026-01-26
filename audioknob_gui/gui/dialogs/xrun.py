from __future__ import annotations

import subprocess
import time
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
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

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
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
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

        self._last_total: int | None = None
        self._last_ts: float | None = None
        self._refresh()

    def _start(self) -> None:
        self._timer.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _stop(self) -> None:
        self._timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _refresh(self) -> None:
        try:
            result = subprocess.run(
                ["pw-top", "-b", "-n", "1"],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception as exc:
            self.summary.setText(f"pw-top failed: {exc}")
            return
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or "pw-top failed"
            self.summary.setText(err)
            return

        output = result.stdout or ""
        total, rows = _parse_pw_top(output)
        now = time.time()
        rate = ""
        if total is not None:
            if self._last_total is not None and self._last_ts is not None:
                delta = total - self._last_total
                dt = max(0.001, now - self._last_ts)
                rate = f" (Δ {delta} / {dt:.1f}s)"
            self._last_total = total
            self._last_ts = now
        if total is None:
            self.summary.setText("ERR column not detected in pw-top output.")
        else:
            self.summary.setText(f"Total ERR: {total}{rate}")
        if rows:
            summary_lines = ["ERR > 0:"]
            summary_lines.extend(rows[:12])
            self.output.setPlainText("\n".join(summary_lines) + "\n\n" + output)
        else:
            self.output.setPlainText(output)


def _parse_pw_top(output: str) -> tuple[int | None, list[str]]:
    lines = output.splitlines()
    header_idx = None
    for idx, line in enumerate(lines):
        if "ERR" in line and "ID" in line:
            header_idx = idx
            break
    if header_idx is None:
        return None, []
    header = lines[header_idx]
    err_pos = header.find("ERR")
    if err_pos < 0:
        return None, []
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
    total = 0
    rows: list[str] = []
    for line in lines[header_idx + 1 :]:
        raw = line.strip()
        if not raw:
            continue
        if not raw[:1].isdigit():
            continue
        if err_pos >= len(line):
            continue
        err_raw = line[err_pos:err_end].strip()
        try:
            err_val = int(err_raw)
        except Exception:
            continue
        total += err_val
        if err_val > 0:
            rows.append(f"{err_val} | {raw}")
    return total, rows

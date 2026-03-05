from __future__ import annotations

import re
import statistics
import time
from collections import deque

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from audioknob_gui.testing.cyclictest import run_cyclictest, to_json


class JitterWorker(QThread):
    finished = Signal(dict)

    def __init__(self, duration_s: int = 1) -> None:
        super().__init__()
        self._duration_s = duration_s

    def run(self) -> None:
        result = run_cyclictest(duration_s=self._duration_s, use_pkexec=False)
        payload = to_json(result, include_samples=False)
        payload["stdout"] = result.stdout
        payload["stderr"] = result.stderr
        self.finished.emit(payload)


class JitterMonitorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scheduler Jitter Monitor")
        self.resize(720, 520)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Live scheduler jitter via cyclictest (short runs)."))

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
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.refresh_btn)
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
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)

        self.refresh_btn.clicked.connect(self._refresh)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

        self._running = False
        self._busy = False
        self._closing = False
        self._last_update: float | None = None
        self._last_max: int | None = None
        self._history: list[str] = []
        self._worker: JitterWorker | None = None
        self._act_history: dict[str, deque[int]] = {}
        self._refresh()

    def _set_always_on_top(self, enabled: bool) -> None:
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.Window | Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
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
        if self._closing:
            return
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
        if self._busy or self._closing:
            return
        self._busy = True
        worker = JitterWorker(duration_s=1)
        self._worker = worker
        worker.finished.connect(self._on_result)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _append_history(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._history.append(f"{ts} {line}")
        self._history = self._history[-20:]

    def _update_act_history(self, rows: list[dict[str, str]]) -> None:
        for row in rows:
            thread = row.get("thread")
            act_raw = row.get("act")
            if not thread or not isinstance(act_raw, str):
                continue
            try:
                act_val = int(act_raw)
            except Exception:
                continue
            history = self._act_history.get(thread)
            if history is None:
                history = deque(maxlen=120)
                self._act_history[thread] = history
            history.append(act_val)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self._running = False
        if self._busy:
            self._closing = True
            self.summary.setText("Waiting for current jitter test to finish...")
            self._update_status()
            event.ignore()
            return
        event.accept()

    def _on_result(self, payload: dict) -> None:
        # Keep content visible even if parsing fails.
        fallback_raw = (payload.get("stdout") or payload.get("stderr") or "").strip()
        self._busy = False
        self._worker = None
        self._last_update = time.time()
        self._update_status()

        if payload.get("returncode") == 127:
            self.summary.setText("cyclictest is not installed.")
            self._append_history("cyclictest not installed")
            return

        max_us = payload.get("max_us")
        note = payload.get("note")
        threads = payload.get("threads") or []
        thread_count = 0
        for item in threads:
            if isinstance(item, dict) and isinstance(item.get("thread"), int):
                thread_count += 1
        p95 = None
        try:
            p95_vals = [t.get("p95_us") for t in threads if isinstance(t.get("p95_us"), int)]
            if p95_vals:
                p95 = max(p95_vals)
        except Exception:
            p95 = None

        raw = fallback_raw
        live_rows = _parse_live_rows(raw) if raw else []
        self._update_act_history(live_rows)
        combined_table = _format_live_summary_table(live_rows, self._act_history)
        if live_rows:
            thread_count = len(live_rows)

        all_samples: list[int] = []
        for samples in self._act_history.values():
            all_samples.extend(list(samples))
        live_stats = _summarize_samples(all_samples)

        max_live = live_stats.get("max_us")
        p95_live = live_stats.get("p95_us")
        delta = ""
        if isinstance(max_live, int):
            if isinstance(self._last_max, int):
                diff = max_live - self._last_max
                delta = f" (Δ {diff:+d} µs)"
            self._last_max = max_live
            p95_label = f", p95 {p95_live} µs" if isinstance(p95_live, int) else ""
            threads_label = f" | Threads: {thread_count}" if thread_count else ""
            self.summary.setText(f"Max: {max_live} µs{p95_label}{delta}{threads_label}")
            self._append_history(f"max={max_live} µs" + (f" p95={p95_live} µs" if isinstance(p95_live, int) else ""))
        elif isinstance(max_us, int):
            p95_label = f", p95 {p95} µs" if isinstance(p95, int) else ""
            threads_label = f" | Threads: {thread_count}" if thread_count else ""
            self.summary.setText(f"Max: {max_us} µs{p95_label}{delta}{threads_label}")
            self._append_history(f"max={max_us} µs" + (f" p95={p95} µs" if isinstance(p95, int) else ""))
        else:
            msg = note or "cyclictest failed"
            self.summary.setText(msg)
            self._append_history(f"failed: {msg}")

        lines: list[str] = []
        lines.append("Live per-thread jitter (rolling Act samples):")
        if combined_table:
            lines.append(combined_table)
        else:
            lines.append("Live data unavailable.")

        if note:
            lines.append(f"\nNote: {note}")
        if self._history:
            lines.append("\nRecent maxima:")
            lines.extend(self._history)
        if raw and not combined_table:
            lines.append("\nRaw cyclictest output:")
            lines.append(raw)
        v_scroll = self.output.verticalScrollBar().value()
        h_scroll = self.output.horizontalScrollBar().value()
        self.output.setPlainText("\n".join(lines))
        self.output.verticalScrollBar().setValue(v_scroll)
        self.output.horizontalScrollBar().setValue(h_scroll)
        if self._closing:
            self.close()


def _format_us(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    if isinstance(value, int):
        return str(value)
    return "—"


def _parse_live_rows(raw: str) -> list[dict[str, str]]:
    rows_by_thread: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        r"^T:\s*(\d+).*?Min:\s*([0-9]+)\s+Act:\s*([0-9]+)\s+Avg:\s*([0-9]+)\s+Max:\s*([0-9]+)"
    )
    for line in raw.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        thread_id = match.group(1)
        rows_by_thread[thread_id] = (
            {
                "thread": f"T{thread_id}",
                "act": match.group(3),
            }
        )
    rows: list[dict[str, str]] = []
    for thread_id in sorted(rows_by_thread, key=lambda v: int(v)):
        rows.append(rows_by_thread[thread_id])
    return rows


def _format_live_summary_table(
    live_rows: list[dict[str, str]], history: dict[str, deque[int]]
) -> str:
    if not live_rows:
        return ""
    live_map = {row.get("thread"): row for row in live_rows if row.get("thread")}
    rows = []
    for thread in sorted(live_map.keys(), key=lambda v: int(v[1:])):
        act = live_map.get(thread, {}).get("act", "—")
        samples = list(history.get(thread, []))
        stats = _summarize_samples(samples)
        rows.append(
            {
                "thread": thread,
                "act": str(act),
                "samples": _format_us(stats.get("samples")),
                "min": _format_us(stats.get("min_us")),
                "median": _format_us(stats.get("median_us")),
                "avg": _format_us(stats.get("avg_us")),
                "p95": _format_us(stats.get("p95_us")),
                "max": _format_us(stats.get("max_us")),
            }
        )
    headers = [
        ("Thread", "thread"),
        ("Act", "act"),
        ("Samples", "samples"),
        ("Min", "min"),
        ("Median", "median"),
        ("Avg", "avg"),
        ("P95", "p95"),
        ("Max", "max"),
    ]
    widths: dict[str, int] = {}
    for title, key in headers:
        widths[key] = len(title)
    for row in rows:
        for _, key in headers:
            widths[key] = max(widths[key], len(str(row.get(key, ""))))
    lines: list[str] = []
    header_line = "  ".join(
        f"{title:{widths[key]}}" if key == "thread" else f"{title:>{widths[key]}}"
        for title, key in headers
    )
    lines.append(header_line)
    for row in rows:
        line = "  ".join(
            f"{row.get(key, ''):{widths[key]}}" if key == "thread" else f"{row.get(key, ''):>{widths[key]}}"
            for _, key in headers
        )
        lines.append(line)
    return "\n".join(lines)


def _summarize_samples(values: list[int]) -> dict[str, int | float]:
    clean = [v for v in values if isinstance(v, int)]
    if not clean:
        return {}
    ordered = sorted(clean)
    count = len(ordered)
    avg = sum(ordered) / count
    med = statistics.median(ordered)
    p95 = _percentile(ordered, 0.95)
    return {
        "samples": count,
        "min_us": ordered[0],
        "median_us": int(round(med)),
        "avg_us": round(avg, 1),
        "p95_us": p95 if p95 is not None else ordered[-1],
        "max_us": ordered[-1],
    }


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    idx = max(0, min(idx, len(ordered) - 1))
    return ordered[idx]

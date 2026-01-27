from __future__ import annotations

import html as html_lib

from PySide6.QtWidgets import QPushButton


def build_test_action(ui, knob, ctx):
    btn = ui._make_action_button("Monitor")
    if ctx.busy:
        btn.setText("Working...")
        btn.setEnabled(False)
    else:
        btn.clicked.connect(ui.on_open_jitter_monitor)
    return btn


def info_extra_html(ui, helpers) -> str:
    extra = ""
    last = ui.state.get("jitter_test_last")
    if isinstance(last, dict):
        max_us = last.get("max_us")
        returncode = last.get("returncode")
        note = last.get("note")
        threads = last.get("threads")
        thread_samples = last.get("thread_samples")
        extra += "<hr/><p><b>Last jitter test:</b></p>"
        if isinstance(max_us, int):
            extra += f"<p>Max: {max_us} µs</p>"
        else:
            extra += "<p>Result: unavailable</p>"
        if isinstance(threads, list) and threads:
            extra += "<table>"
            extra += (
                "<tr>"
                "<td><b>Thread</b></td>"
                "<td><b>Samples</b></td>"
                "<td><b>Min</b></td>"
                "<td><b>Median</b></td>"
                "<td><b>Avg</b></td>"
                "<td><b>P95</b></td>"
                "<td><b>Max</b></td>"
                "</tr>"
            )
            for item in sorted(threads, key=lambda t: t.get("thread", 0)):
                thread_id = item.get("thread")
                if not isinstance(thread_id, int):
                    continue
                extra += (
                    "<tr>"
                    f"<td>{thread_id}</td>"
                    f"<td>{helpers.fmt_jitter_value(item.get('samples'))}</td>"
                    f"<td>{helpers.fmt_jitter_value(item.get('min_us'))}</td>"
                    f"<td>{helpers.fmt_jitter_value(item.get('median_us'))}</td>"
                    f"<td>{helpers.fmt_jitter_value(item.get('avg_us'))}</td>"
                    f"<td>{helpers.fmt_jitter_value(item.get('p95_us'))}</td>"
                    f"<td>{helpers.fmt_jitter_value(item.get('max_us'))}</td>"
                    "</tr>"
                )
            extra += "</table>"
            if isinstance(thread_samples, list) and thread_samples:
                extra += "<p>Tip: use \"Show Sample List\" to view raw values.</p>"
        else:
            extra += "<p>No per-thread results captured yet.</p>"
        if note:
            extra += f"<p><b>Note:</b> {html_lib.escape(str(note))}</p>"
        if returncode is not None:
            extra += f"<p><b>Return code:</b> {returncode}</p>"
    else:
        extra += "<hr/><p><b>Last jitter test:</b> not run yet.</p>"
    return extra


def add_info_buttons(ui, knob, dialog, layout) -> None:
    if knob.id == "scheduler_jitter_test":
        snapshot_btn = QPushButton("Refresh Snapshot...")
        snapshot_btn.clicked.connect(lambda: ui.on_run_test(knob.id, refresh_dialog=dialog))
        layout.addWidget(snapshot_btn)
    last = ui.state.get("jitter_test_last")
    samples = last.get("thread_samples") if isinstance(last, dict) else None
    if isinstance(samples, list) and samples:
        samples_btn = QPushButton("Show Sample List...")
        samples_btn.clicked.connect(lambda: ui._show_jitter_samples(samples))
        layout.addWidget(samples_btn)

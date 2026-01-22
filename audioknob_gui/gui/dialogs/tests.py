from __future__ import annotations

import json

from audioknob_gui.testing.cyclictest import run_cyclictest, to_json


def _format_us(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    if isinstance(value, int):
        return str(value)
    return "—"


def _format_thread_summary(threads: list[dict]) -> str:
    lines: list[str] = []
    for item in sorted(threads, key=lambda t: t.get("thread", 0)):
        thread_id = item.get("thread")
        if not isinstance(thread_id, int):
            continue
        samples = item.get("samples")
        min_us = item.get("min_us")
        median_us = item.get("median_us")
        avg_us = item.get("avg_us")
        p95_us = item.get("p95_us")
        max_us = item.get("max_us")
        count = samples if isinstance(samples, int) else None
        count_label = str(count) if count is not None else "?"
        lines.append(
            "T{tid}: n={count} min={min} med={med} avg={avg} p95={p95} max={max}".format(
                tid=thread_id,
                count=count_label,
                min=_format_us(min_us),
                med=_format_us(median_us),
                avg=_format_us(avg_us),
                p95=_format_us(p95_us),
                max=_format_us(max_us),
            )
        )
    return "\n".join(lines)


def jitter_test_summary(duration_s: int = 5, *, use_pkexec: bool = False) -> tuple[str, str, dict]:
    r = run_cyclictest(duration_s=duration_s, use_pkexec=use_pkexec)
    if (not r.ok or r.max_us is None) and not use_pkexec and r.returncode != 127:
        r = run_cyclictest(duration_s=duration_s, use_pkexec=True)
    payload = to_json(r, include_samples=True)
    display_payload = to_json(r, include_samples=False)

    if r.returncode == 127:
        headline = "cyclictest is not installed"
        detail = "Install the 'cyclictest' package, then re-run the test.\n\n"
        if r.note and r.note != "cyclictest not installed":
            detail += f"{r.note}\n\n"
        detail += json.dumps(payload, indent=2)
        return (headline, detail, payload)

    if r.max_us is not None:
        headline = f"Scheduler jitter: max {r.max_us} µs"
    else:
        headline = "Scheduler jitter: failed"

    detail = headline + "\n\n"
    detail += "Note: cyclictest measures scheduler latency jitter, not audio input/RTL latency.\n"
    summary = _format_thread_summary(display_payload.get("threads", []))
    if summary:
        detail += "\nPer-thread summary:\n" + summary + "\n"
    if r.note:
        detail += "\n" + r.note + "\n"
    detail += "\n" + json.dumps(display_payload, indent=2)
    return (headline, detail, payload)

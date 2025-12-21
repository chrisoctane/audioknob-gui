from __future__ import annotations

import json

from audioknob_gui.testing.cyclictest import run_cyclictest, to_json


def jitter_test_summary(duration_s: int = 5, *, use_pkexec: bool = False) -> tuple[str, str, dict]:
    r = run_cyclictest(duration_s=duration_s, use_pkexec=use_pkexec)
    if (not r.ok or r.max_us is None) and not use_pkexec and r.returncode != 127:
        r = run_cyclictest(duration_s=duration_s, use_pkexec=True)
    payload = to_json(r)

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

    detail = (
        headline
        + "\n\n"
        + "Note: cyclictest measures scheduler latency jitter, not audio input/RTL latency.\n"
        + ((r.note + "\n\n") if r.note else "")
        + json.dumps(payload, indent=2)
    )
    return (headline, detail, payload)

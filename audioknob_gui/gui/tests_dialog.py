from __future__ import annotations

import json

from audioknob_gui.testing.cyclictest import run_cyclictest, to_json


def jitter_test_summary(duration_s: int = 5) -> tuple[str, str]:
    r = run_cyclictest(duration_s=duration_s)
    payload = to_json(r)

    if r.returncode == 127:
        return (
            "cyclictest is not installed",
            "Install the 'cyclictest' package, then re-run the test.\n\n" + json.dumps(payload, indent=2),
        )

    if r.max_us is not None:
        headline = f"Scheduler jitter: max {r.max_us} µs"
    else:
        headline = "Scheduler jitter: (could not parse max_us)"

    detail = (
        headline
        + "\n\n"
        + "Note: cyclictest measures scheduler latency jitter, not audio input/RTL latency.\n"
        + json.dumps(payload, indent=2)
    )
    return (headline, detail)

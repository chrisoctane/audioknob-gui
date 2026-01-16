from __future__ import annotations

import json
import re
import shutil
import statistics
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass

from audioknob_gui.platform.packages import which_command


@dataclass(frozen=True)
class CyclicTestResult:
    ok: bool
    returncode: int
    max_us: int | None
    threads: list[dict[str, int | float]]
    thread_samples: list[dict[str, int | list[int]]]
    note: str | None
    stdout: str
    stderr: str


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    idx = max(0, min(idx, len(ordered) - 1))
    return ordered[idx]


def _summarize_samples(samples: Iterable[int]) -> dict[str, int | float]:
    values = [v for v in samples if isinstance(v, int)]
    if not values:
        return {}
    ordered = sorted(values)
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


def run_cyclictest(duration_s: int = 5, *, use_pkexec: bool = False) -> CyclicTestResult:
    cyclictest_path = which_command("cyclictest") or shutil.which("cyclictest")
    if cyclictest_path is None:
        return CyclicTestResult(
            ok=False,
            returncode=127,
            max_us=None,
            threads=[],
            thread_samples=[],
            note="cyclictest not installed",
            stdout="",
            stderr="",
        )

    argv = [
        cyclictest_path,
        "-D",
        str(int(duration_s)),
        "-m",        # Lock memory
        "-Sp90",     # SCHED_FIFO priority 90
        "-i200",     # 200µs interval
        # Note: removed -q and -h400 to get readable summary output
    ]
    if use_pkexec:
        if shutil.which("pkexec") is None:
            return CyclicTestResult(
                ok=False,
                returncode=127,
                max_us=None,
                threads=[],
                thread_samples=[],
                note="pkexec not installed",
                stdout="",
                stderr="",
            )
        argv = ["pkexec", *argv]

    p = subprocess.run(argv, text=True, capture_output=True)

    max_us: int | None = None
    all_max_values: list[int] = []
    thread_samples: dict[int, list[int]] = {}
    threads: list[dict[str, int | float]] = []
    thread_re = re.compile(r"^T:\s*(\d+).*?Max:\s*([0-9]+)")
    
    # cyclictest output format:
    # "T: 0 (  1234) P:90 I:200 C:  2500 Min:      4 Act:    5 Avg:    6 Max:    12"
    for ln in (p.stdout + "\n" + p.stderr).splitlines():
        ln = ln.strip()
        if "Max:" in ln:
            m = thread_re.search(ln)
            if m:
                try:
                    thread_id = int(m.group(1))
                    max_val = int(m.group(2))
                    thread_samples.setdefault(thread_id, []).append(max_val)
                except Exception:
                    pass
            parts = ln.replace("Max:", "Max: ").split()
            for i, tok in enumerate(parts):
                if tok == "Max:" and i + 1 < len(parts):
                    try:
                        val = int(parts[i + 1])
                        all_max_values.append(val)
                    except (ValueError, IndexError):
                        pass
                    break
    
    # Return the highest max across all threads
    if all_max_values:
        max_us = max(all_max_values)

    if thread_samples:
        for tid in sorted(thread_samples):
            summary = _summarize_samples(thread_samples[tid])
            if summary:
                summary["thread"] = tid
                threads.append(summary)

    note = None
    if p.returncode != 0:
        note = p.stderr.strip() or p.stdout.strip() or f"cyclictest failed (rc {p.returncode})"

    return CyclicTestResult(
        ok=p.returncode == 0,
        returncode=p.returncode,
        max_us=max_us,
        threads=threads,
        thread_samples=[
            {"thread": tid, "samples": samples} for tid, samples in sorted(thread_samples.items())
        ],
        note=note,
        stdout=p.stdout,
        stderr=p.stderr,
    )


def to_json(r: CyclicTestResult, *, include_samples: bool = True) -> dict:
    payload = {
        "schema": 1,
        "ok": r.ok,
        "returncode": r.returncode,
        "max_us": r.max_us,
        "threads": r.threads,
        "note": r.note,
    }
    if include_samples:
        payload["thread_samples"] = r.thread_samples
    return payload


def main() -> int:
    r = run_cyclictest()
    print(json.dumps(to_json(r, include_samples=True), indent=2, sort_keys=True))
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

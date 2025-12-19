from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CyclicTestResult:
    ok: bool
    returncode: int
    max_us: int | None
    note: str | None
    stdout: str
    stderr: str


def run_cyclictest(duration_s: int = 5) -> CyclicTestResult:
    if shutil.which("cyclictest") is None:
        return CyclicTestResult(
            ok=False,
            returncode=127,
            max_us=None,
            note="cyclictest not installed",
            stdout="",
            stderr="",
        )

    argv = [
        "cyclictest",
        "-D",
        str(int(duration_s)),
        "-m",        # Lock memory
        "-Sp90",     # SCHED_FIFO priority 90
        "-i200",     # 200µs interval
        # Note: removed -q and -h400 to get readable summary output
    ]
    p = subprocess.run(argv, text=True, capture_output=True)

    max_us: int | None = None
    all_max_values: list[int] = []
    
    # cyclictest output format:
    # "T: 0 (  1234) P:90 I:200 C:  2500 Min:      4 Act:    5 Avg:    6 Max:    12"
    for ln in (p.stdout + "\n" + p.stderr).splitlines():
        ln = ln.strip()
        if "Max:" in ln:
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

    return CyclicTestResult(
        ok=p.returncode == 0,
        returncode=p.returncode,
        max_us=max_us,
        note=None,
        stdout=p.stdout,
        stderr=p.stderr,
    )


def to_json(r: CyclicTestResult) -> dict:
    return {
        "schema": 1,
        "ok": r.ok,
        "returncode": r.returncode,
        "max_us": r.max_us,
        "note": r.note,
    }


def main() -> int:
    r = run_cyclictest()
    print(json.dumps(to_json(r), indent=2, sort_keys=True))
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

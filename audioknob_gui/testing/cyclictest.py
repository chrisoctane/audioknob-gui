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
        "-q",
        "-D",
        str(int(duration_s)),
        "-m",
        "-Sp90",
        "-i200",
        "-h400",
    ]
    p = subprocess.run(argv, text=True, capture_output=True)

    max_us: int | None = None
    # cyclictest output varies; try a simple parse for the "Max:" field.
    for ln in (p.stdout + "\n" + p.stderr).splitlines():
        ln = ln.strip()
        if "Max:" in ln:
            # example: "T: 0 (  1234) P:90 I:200 C:  2500 Min:      4 Act:    5 Avg:    6 Max:    12"
            parts = ln.replace("Max:", "Max: ").split()
            for i, tok in enumerate(parts):
                if tok == "Max:" and i + 1 < len(parts):
                    try:
                        max_us = int(parts[i + 1])
                    except Exception:
                        max_us = None
                    break

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

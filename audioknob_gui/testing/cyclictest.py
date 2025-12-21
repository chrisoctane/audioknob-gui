from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from audioknob_gui.platform.packages import which_command


@dataclass(frozen=True)
class CyclicTestResult:
    ok: bool
    returncode: int
    max_us: int | None
    threads: list[dict[str, int]]
    note: str | None
    stdout: str
    stderr: str


def run_cyclictest(duration_s: int = 5, *, use_pkexec: bool = False) -> CyclicTestResult:
    cyclictest_path = which_command("cyclictest") or shutil.which("cyclictest")
    if cyclictest_path is None:
        return CyclicTestResult(
            ok=False,
            returncode=127,
            max_us=None,
            threads=[],
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
                note="pkexec not installed",
                stdout="",
                stderr="",
            )
        argv = ["pkexec", *argv]

    p = subprocess.run(argv, text=True, capture_output=True)

    max_us: int | None = None
    all_max_values: list[int] = []
    threads: list[dict[str, int]] = []
    thread_re = re.compile(r"^T:\s*(\d+).*?Max:\s*([0-9]+)")
    
    # cyclictest output format:
    # "T: 0 (  1234) P:90 I:200 C:  2500 Min:      4 Act:    5 Avg:    6 Max:    12"
    for ln in (p.stdout + "\n" + p.stderr).splitlines():
        ln = ln.strip()
        if "Max:" in ln:
            m = thread_re.search(ln)
            if m:
                try:
                    threads.append({"thread": int(m.group(1)), "max_us": int(m.group(2))})
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

    note = None
    if p.returncode != 0:
        note = p.stderr.strip() or p.stdout.strip() or f"cyclictest failed (rc {p.returncode})"

    return CyclicTestResult(
        ok=p.returncode == 0,
        returncode=p.returncode,
        max_us=max_us,
        threads=threads,
        note=note,
        stdout=p.stdout,
        stderr=p.stderr,
    )


def to_json(r: CyclicTestResult) -> dict:
    return {
        "schema": 1,
        "ok": r.ok,
        "returncode": r.returncode,
        "max_us": r.max_us,
        "threads": r.threads,
        "note": r.note,
    }


def main() -> int:
    r = run_cyclictest()
    print(json.dumps(to_json(r), indent=2, sort_keys=True))
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

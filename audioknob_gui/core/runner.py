from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class RunResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def run(argv: list[str], *, check: bool = False) -> RunResult:
    p = subprocess.run(argv, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {argv}\n{p.stderr}")
    return RunResult(argv=argv, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)

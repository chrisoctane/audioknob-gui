#!/usr/bin/env python3
"""Run repository quality gates for change/parity/release workflows."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_step(repo: Path, label: str, cmd: list[str]) -> bool:
    print(f"[quality-gate] {label}")
    print(f"[quality-gate] cmd: {' '.join(cmd)}")
    rc = subprocess.run(cmd, cwd=repo, check=False).returncode
    if rc != 0:
        print(f"[quality-gate] FAIL: {label} (exit {rc})")
        return False
    print(f"[quality-gate] PASS: {label}")
    return True


def _python_for_pytest(repo: Path) -> str:
    venv_python = repo / ".venv" / "bin" / "python"
    if venv_python.exists():
        try:
            rc = subprocess.run(
                [str(venv_python), "-m", "pytest", "--version"],
                cwd=repo,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            if rc == 0:
                return str(venv_python)
        except Exception:
            pass
    return sys.executable


def _normalize_release_version(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise ValueError("release version cannot be empty")
    return text[1:] if text.startswith("v") else text


def _project_state_release_version(repo: Path) -> str | None:
    path = repo / "PROJECT_STATE.md"
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return None
    match = re.search(r"^\s*-\s+\*\*Release version\*\*:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", content, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _changelog_has_version(repo: Path, version: str) -> bool:
    path = repo / "CHANGELOG.md"
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return False
    pat = rf"^\s*##\s+\[{re.escape(version)}\]\s+-\s+"
    return re.search(pat, content, re.MULTILINE) is not None


def _release_checklist_path(repo: Path, version: str) -> Path:
    return repo / "docs" / "internal" / "audit" / "releases" / f"v{version}" / "CHECKLIST.md"


def _release_checklist_passes(path: Path, version: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing release checklist artifact: {path}"
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        return False, f"failed reading release checklist {path}: {exc}"
    if f"Release version: {version}" not in content:
        return False, f"release checklist missing exact version line: Release version: {version}"
    if re.search(r"^\s*Final status:\s*PASS\s*$", content, re.MULTILINE) is None:
        return False, f"release checklist missing final pass marker in {path}"
    return True, "release checklist artifact is present and marked PASS"


def _run_release_checks(repo: Path, release_version_arg: str | None) -> bool:
    version = _normalize_release_version(release_version_arg) if release_version_arg else _project_state_release_version(repo)
    if not version:
        print("[quality-gate] FAIL: unable to determine release version (use --release-version)")
        return False
    print(f"[quality-gate] release version: {version}")

    if not _changelog_has_version(repo, version):
        print(f"[quality-gate] FAIL: CHANGELOG.md does not contain a heading for [{version}]")
        return False
    print(f"[quality-gate] PASS: changelog contains [{version}]")

    checklist = _release_checklist_path(repo, version)
    ok, note = _release_checklist_passes(checklist, version)
    if not ok:
        print(f"[quality-gate] FAIL: {note}")
        return False
    print(f"[quality-gate] PASS: {note}")
    return True


def run_quality_gate(gate: str, release_version: str | None) -> int:
    repo = _repo_root()
    ok = True

    # G1 baseline checks apply to all gate levels.
    ok &= _run_step(repo, "consistency", [sys.executable, "scripts/check_repo_consistency.py"])
    ok &= _run_step(repo, "compile", [sys.executable, "-m", "compileall", "-q", "audioknob_gui", "tests"])

    # G2/G3/CI include tests (CI uses full tests as a strict superset).
    if gate in {"g2", "g3", "ci"}:
        pytest_python = _python_for_pytest(repo)
        ok &= _run_step(repo, "pytest", [pytest_python, "-m", "pytest", "-q"])

    # G3 adds release artifact and changelog checks.
    if gate == "g3":
        ok &= _run_release_checks(repo, release_version)

    if not ok:
        print("[quality-gate] RESULT: FAIL")
        return 1
    print("[quality-gate] RESULT: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repository quality gates")
    parser.add_argument(
        "--gate",
        choices=("g1", "g2", "g3", "ci"),
        default="ci",
        help="Gate level to run (default: ci)",
    )
    parser.add_argument(
        "--release-version",
        default=None,
        help="Release version for g3 checks (accepts 1.2.3 or v1.2.3)",
    )
    args = parser.parse_args()
    return run_quality_gate(args.gate, args.release_version)


if __name__ == "__main__":
    raise SystemExit(main())

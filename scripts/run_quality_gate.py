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


def _run_pytest_step(repo: Path, pytest_python: str, selectors: list[str], *, label: str) -> bool:
    cmd = [pytest_python, "-m", "pytest", "-q", *selectors]
    return _run_step(repo, label, cmd)


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


def _latest_audit_cycle_dir(repo: Path) -> Path | None:
    root = repo / "docs" / "internal" / "audit"
    if not root.exists():
        return None
    date_dirs = [
        p for p in root.iterdir() if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", p.name)
    ]
    if not date_dirs:
        return None
    return sorted(date_dirs, key=lambda p: p.name)[-1]


def _release_findings_pass(repo: Path) -> tuple[bool, str]:
    cycle = _latest_audit_cycle_dir(repo)
    if cycle is None:
        return False, "no dated audit cycle found under docs/internal/audit"

    findings = cycle / "FINDINGS_LEDGER.md"
    if not findings.exists():
        return False, f"missing findings ledger: {findings}"
    try:
        content = findings.read_text(encoding="utf-8")
    except Exception as exc:
        return False, f"failed reading findings ledger {findings}: {exc}"

    unresolved: list[str] = []
    for line in content.splitlines():
        row = line.strip()
        if not row.startswith("|"):
            continue
        if "---" in row:
            continue
        parts = [col.strip() for col in row.split("|")[1:-1]]
        if len(parts) < 8:
            continue
        finding_id = parts[0]
        severity = parts[1].lower()
        status = parts[7].lower()
        if severity in ("blocker", "critical") and "resolved" not in status:
            unresolved.append(f"{finding_id} ({parts[1]}: {parts[7]})")

    if unresolved:
        return False, "unresolved blocker/critical findings: " + ", ".join(unresolved)
    return True, f"no unresolved blocker/critical findings in {findings}"


def _release_alignment_tracker_pass(repo: Path) -> tuple[bool, str]:
    cycle = _latest_audit_cycle_dir(repo)
    if cycle is None:
        return False, "no dated audit cycle found under docs/internal/audit"

    tracker = cycle / "ALIGNMENT_GAP_TRACKER.md"
    if not tracker.exists():
        return False, f"missing alignment tracker: {tracker}"
    try:
        content = tracker.read_text(encoding="utf-8")
    except Exception as exc:
        return False, f"failed reading alignment tracker {tracker}: {exc}"

    lines = content.splitlines()
    for idx, raw in enumerate(lines):
        if not raw.strip().lower().startswith("tracker status:"):
            continue

        status_parts: list[str] = []
        inline = raw.split(":", 1)[1].strip()
        if inline:
            status_parts.append(inline)

        for extra in lines[idx + 1: idx + 4]:
            s = extra.strip()
            if not s:
                continue
            if s.startswith("#"):
                break
            status_parts.append(s.lstrip("- ").strip())

        status_text = " ".join(status_parts)
        status_text = re.sub(r"[`*_]", "", status_text).lower()
        if "not closed" not in status_text and re.search(r"\bclosed\b", status_text):
            return True, f"alignment tracker is closed: {tracker}"
        break

    # Allow explicit deferred scope with rationale per quality gate policy.
    lowered = content.lower()
    if "deferred" in lowered and "rationale" in lowered:
        return True, f"alignment tracker has explicit deferred scope with rationale: {tracker}"
    return False, f"alignment tracker is not closed and has no explicit deferred+rationale contract: {tracker}"


def _run_release_audit_checks(repo: Path) -> bool:
    checks = (
        _release_findings_pass(repo),
        _release_alignment_tracker_pass(repo),
    )
    ok = True
    for passed, note in checks:
        if passed:
            print(f"[quality-gate] PASS: {note}")
            continue
        print(f"[quality-gate] FAIL: {note}")
        ok = False
    return ok


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
    if not _run_release_audit_checks(repo):
        return False
    return True


def run_quality_gate(gate: str, release_version: str | None, tests: list[str] | None = None) -> int:
    repo = _repo_root()
    ok = True
    selectors = [str(x) for x in (tests or []) if str(x).strip()]

    # G1 baseline checks apply to all gate levels.
    ok &= _run_step(repo, "consistency", [sys.executable, "scripts/check_repo_consistency.py"])
    ok &= _run_step(repo, "compile", [sys.executable, "-m", "compileall", "-q", "audioknob_gui", "tests"])

    pytest_python = _python_for_pytest(repo)

    # G2 requires targeted pytest selectors.
    if gate == "g2":
        if not selectors:
            print("[quality-gate] FAIL: g2 requires targeted tests via --tests <path_or_node> [...]")
            ok = False
        else:
            ok &= _run_pytest_step(repo, pytest_python, selectors, label="pytest-targeted")

    # G3/CI run the full suite.
    if gate in {"g3", "ci"}:
        ok &= _run_pytest_step(repo, pytest_python, [], label="pytest")

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
    parser.add_argument(
        "--tests",
        nargs="*",
        default=None,
        help="Targeted pytest selectors for g2 (paths, files, or node ids)",
    )
    args = parser.parse_args()
    return run_quality_gate(args.gate, args.release_version, tests=args.tests)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
check_repo_consistency.py

Enforces docs ↔ code consistency for audioknob-gui.
Run this as a pre-commit hook or in CI to catch drift before merge.

Exit codes:
  0 = all checks pass
  1 = one or more checks failed (actionable error message printed)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def get_repo_root() -> Path:
    """Return the repo root (where .git lives)."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def check_registry_sync(repo: Path) -> list[str]:
    """Check that config/registry*.json are synced to audioknob_gui/data/."""
    errors = []
    
    pairs = [
        ("config/registry.json", "audioknob_gui/data/registry.json"),
        ("config/registry.schema.json", "audioknob_gui/data/registry.schema.json"),
    ]
    
    for canonical, packaged in pairs:
        canonical_path = repo / canonical
        packaged_path = repo / packaged
        
        if not canonical_path.exists():
            errors.append(f"Missing canonical file: {canonical}")
            continue
        if not packaged_path.exists():
            errors.append(f"Missing packaged file: {packaged} (run: cp {canonical} {packaged})")
            continue
        
        result = subprocess.run(
            ["diff", "-q", str(canonical_path), str(packaged_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            errors.append(
                f"Registry out of sync: {canonical} ≠ {packaged}\n"
                f"  Fix: cp {canonical} {packaged}"
            )
    
    return errors


def check_docs_exist(repo: Path) -> list[str]:
    """Check that required documentation files exist."""
    errors = []
    
    required = ["PLAN.md", "PROJECT_STATE.md"]
    for doc in required:
        if not (repo / doc).exists():
            errors.append(f"Missing required doc: {doc}")
    
    return errors


def check_docs_sections(repo: Path) -> list[str]:
    """Check that required sections exist in docs."""
    errors = []
    
    # PLAN.md required sections
    plan_path = repo / "PLAN.md"
    if plan_path.exists():
        plan_content = plan_path.read_text(encoding="utf-8")
        required_sections = ["Registry Sync Policy", "Scope / Non-goals"]
        for section in required_sections:
            if section not in plan_content:
                errors.append(f"PLAN.md missing required section: '{section}'")
    
    # PROJECT_STATE.md required sections
    state_path = repo / "PROJECT_STATE.md"
    if state_path.exists():
        state_content = state_path.read_text(encoding="utf-8")
        required_sections = ["Operator Contract (anti-drift, for AI agents)"]
        for section in required_sections:
            if section not in state_content:
                errors.append(f"PROJECT_STATE.md missing required section: '{section}'")
    
    return errors


def check_compile(repo: Path) -> list[str]:
    """Check that Python code compiles without errors."""
    errors = []
    
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(repo / "audioknob_gui")],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        errors.append(f"Python compile failed:\n{result.stderr or result.stdout}")
    
    return errors


def check_docs_updated_for_code_changes(repo: Path) -> list[str]:
    """
    Check that if code paths are modified, docs are also modified.
    
    This is a diff-based check for CI. It compares against the merge base.
    For pre-commit, we check staged files.
    """
    errors = []
    
    # Paths that require doc updates when changed
    code_paths = [
        "audioknob_gui/worker/",
        "audioknob_gui/gui/",
        "audioknob_gui/platform/",
        "config/registry",
        "pyproject.toml",
        "bin/",
        "packaging/",
    ]
    
    doc_paths = ["PLAN.md", "PROJECT_STATE.md"]
    
    # Get list of changed files (staged for pre-commit, or all in CI)
    # First try staged files (pre-commit)
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    changed_files = result.stdout.strip().split("\n") if result.stdout.strip() else []
    
    # If no staged files, try diff against origin/master (CI mode)
    if not changed_files:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/master...HEAD"],
            capture_output=True,
            text=True,
            cwd=repo,
        )
        changed_files = result.stdout.strip().split("\n") if result.stdout.strip() else []
    
    if not changed_files:
        return []  # No changes to check
    
    # Check if any code paths were touched
    code_touched = False
    for f in changed_files:
        for code_path in code_paths:
            if f.startswith(code_path) or code_path in f:
                code_touched = True
                break
        if code_touched:
            break
    
    if not code_touched:
        return []  # No code changes, no doc requirement
    
    # Check if any doc was also touched
    doc_touched = any(f in doc_paths for f in changed_files)
    
    if not doc_touched:
        # Check for exception tag in commit message
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            capture_output=True,
            text=True,
            cwd=repo,
        )
        commit_msg = result.stdout.lower()
        if "docs-not-needed:" in commit_msg:
            return []  # Explicitly waived
        
        errors.append(
            "Code changes detected without doc updates.\n"
            "  Modified code paths require PLAN.md or PROJECT_STATE.md to also be updated.\n"
            "  If this is a pure refactor with no behavior change, add 'docs-not-needed:' to commit message."
        )
    
    return errors


def main() -> int:
    """Run all consistency checks."""
    try:
        repo = get_repo_root()
    except subprocess.CalledProcessError:
        print("ERROR: Not in a git repository", file=sys.stderr)
        return 1
    
    all_errors: list[str] = []
    
    print("Checking repository consistency...")
    
    # Run all checks
    checks = [
        ("Registry sync", check_registry_sync),
        ("Docs exist", check_docs_exist),
        ("Docs sections", check_docs_sections),
        ("Python compile", check_compile),
        ("Docs updated for code changes", check_docs_updated_for_code_changes),
    ]
    
    for name, check_fn in checks:
        errors = check_fn(repo)
        if errors:
            print(f"\n❌ {name}:")
            for e in errors:
                print(f"   {e}")
            all_errors.extend(errors)
        else:
            print(f"✅ {name}")
    
    if all_errors:
        print(f"\n{'='*60}")
        print(f"FAILED: {len(all_errors)} error(s) found")
        print(f"{'='*60}")
        return 1
    
    print(f"\n{'='*60}")
    print("All checks passed!")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

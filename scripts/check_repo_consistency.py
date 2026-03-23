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

import ast
import json
import os
import re
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
    
    required = [
        "AGENTS.md",
        "CLAUDE.md",
        "PLAN.md",
        "PROJECT_STATE.md",
        "docs/internal/audit/STABILIZATION_STATE.md",
    ]
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


def _read_pyproject_version(repo: Path) -> str | None:
    path = repo / "pyproject.toml"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    return m.group(1).strip() if m else None


def _read_project_state_release_version(repo: Path) -> str | None:
    path = repo / "PROJECT_STATE.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^\s*-\s+\*\*Release version\*\*:\s*([^\n]+?)\s*$", text, flags=re.MULTILINE)
    return m.group(1).strip() if m else None


def _read_package_init_version(repo: Path) -> str | None:
    path = repo / "audioknob_gui" / "__init__.py"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^\s*__version__\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    return m.group(1).strip() if m else None


def _read_registry_knob_count(repo: Path) -> int | None:
    path = repo / "config" / "registry.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    knobs = payload.get("knobs")
    if not isinstance(knobs, list):
        return None
    return len(knobs)


def _read_project_state_knob_claim(repo: Path) -> tuple[int, int] | None:
    path = repo / "PROJECT_STATE.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(
        r"^\s*-\s+\*\*(\d+)\s+knobs defined\*\*\s+\(ALL\s+(\d+)\s+IMPLEMENTED",
        text,
        flags=re.MULTILINE,
    )
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _extract_table_status_keys(repo: Path) -> set[str]:
    table_path = repo / "audioknob_gui" / "gui" / "table.py"
    if not table_path.exists():
        return set()
    try:
        tree = ast.parse(table_path.read_text(encoding="utf-8"))
    except Exception:
        return set()

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "TableMixin":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "_status_display":
                continue
            for sub in ast.walk(item):
                if not isinstance(sub, ast.Assign):
                    continue
                if not any(isinstance(t, ast.Name) and t.id == "mapping" for t in sub.targets):
                    continue
                if not isinstance(sub.value, ast.Dict):
                    continue
                keys: set[str] = set()
                for key in sub.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
                return keys
    return set()


def _read_plan_operational_status_labels(repo: Path) -> list[str] | None:
    plan_path = repo / "PLAN.md"
    if not plan_path.exists():
        return None
    text = plan_path.read_text(encoding="utf-8")
    m = re.search(r"^.*Status column is operational only.*$", text, flags=re.MULTILINE)
    if not m:
        return None
    return [part.strip() for part in re.findall(r"`([^`]+)`", m.group(0))]


def check_semantic_doc_contracts(repo: Path) -> list[str]:
    """Check semantic contracts that are prone to silent doc drift."""
    errors: list[str] = []

    pyproject_version = _read_pyproject_version(repo)
    project_state_version = _read_project_state_release_version(repo)
    package_init_version = _read_package_init_version(repo)
    if not pyproject_version:
        errors.append("Cannot parse project version from pyproject.toml")
    if not project_state_version:
        errors.append("Cannot parse '**Release version**' from PROJECT_STATE.md")
    if not package_init_version:
        errors.append("Cannot parse package __version__ from audioknob_gui/__init__.py")
    if pyproject_version and project_state_version and pyproject_version != project_state_version:
        errors.append(
            "Release version mismatch:\n"
            f"  pyproject.toml: {pyproject_version}\n"
            f"  PROJECT_STATE.md: {project_state_version}"
        )
    if pyproject_version and package_init_version and pyproject_version != package_init_version:
        errors.append(
            "Package version mismatch:\n"
            f"  pyproject.toml: {pyproject_version}\n"
            f"  audioknob_gui/__init__.py: {package_init_version}"
        )
    if project_state_version and package_init_version and project_state_version != package_init_version:
        errors.append(
            "Release version mismatch:\n"
            f"  PROJECT_STATE.md: {project_state_version}\n"
            f"  audioknob_gui/__init__.py: {package_init_version}"
        )

    registry_knob_count = _read_registry_knob_count(repo)
    project_state_knob_claim = _read_project_state_knob_claim(repo)
    if registry_knob_count is None:
        errors.append("Cannot parse knob count from config/registry.json")
    if project_state_knob_claim is None:
        errors.append(
            "Cannot parse knob-count claim from PROJECT_STATE.md "
            "(expected '**N knobs defined** (ALL N IMPLEMENTED...)')."
        )
    if registry_knob_count is not None and project_state_knob_claim is not None:
        claimed_defined, claimed_implemented = project_state_knob_claim
        if claimed_defined != registry_knob_count:
            errors.append(
                "Knob count mismatch:\n"
                f"  config/registry.json: {registry_knob_count}\n"
                f"  PROJECT_STATE.md defined claim: {claimed_defined}"
            )
        if claimed_implemented != registry_knob_count:
            errors.append(
                "Knob implementation claim mismatch:\n"
                f"  config/registry.json: {registry_knob_count}\n"
                f"  PROJECT_STATE.md implemented claim: {claimed_implemented}"
            )

    # Runtime status vocabulary contract: these are the user-facing operational states.
    required_status_keys = {
        "applied",
        "not_applied",
        "partial",
        "pending_reboot",
        "unknown",
        "not_applicable",
    }
    status_keys = _extract_table_status_keys(repo)
    missing_status_keys = sorted(required_status_keys - status_keys)
    if missing_status_keys:
        errors.append(
            "Status vocabulary mismatch: table status mapping is missing required keys: "
            + ", ".join(missing_status_keys)
        )

    expected_plan_labels = [
        "Applied",
        "Configured",
        "External",
        "Not applied",
        "Partial",
        "Reboot",
        "Unknown",
        "N/A",
    ]
    plan_labels = _read_plan_operational_status_labels(repo)
    if plan_labels is None:
        errors.append(
            "Cannot parse PLAN.md operational status labels "
            "(expected 'Status column is operational only (...)')."
        )
    elif plan_labels != expected_plan_labels:
        errors.append(
            "PLAN.md operational status labels mismatch:\n"
            f"  expected: {', '.join(expected_plan_labels)}\n"
            f"  found: {', '.join(plan_labels)}"
        )

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


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=repo,
    )


def _parse_changed_files(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def _parse_status_porcelain(output: str) -> list[str]:
    files: list[str] = []
    for raw in output.splitlines():
        line = raw.rstrip()
        if len(line) < 4:
            continue
        # porcelain v1 format: XY<space>PATH (or PATH1 -> PATH2 for renames)
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip()
        if path:
            files.append(path)
    return files


def _resolve_changed_files(repo: Path) -> tuple[list[str], str, list[str]]:
    """Resolve changed files for docs-update gating with CI-safe fallbacks."""
    notes: list[str] = []

    # Pre-commit / local staged changes.
    staged = _run_git(repo, "diff", "--cached", "--name-only")
    if staged.returncode == 0:
        files = _parse_changed_files(staged.stdout)
        if files:
            return files, "staged", notes
    else:
        notes.append(f"staged diff failed: {staged.stderr.strip() or staged.stdout.strip()}")

    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip().lower()
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    before_sha = os.environ.get("GITHUB_EVENT_BEFORE", "").strip()
    is_ci = os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"

    # Pull requests: compare from merge-base with origin/<base>.
    if base_ref:
        base_name = f"origin/{base_ref}"
        base_check = _run_git(repo, "rev-parse", "--verify", base_name)
        if base_check.returncode == 0:
            merge_base = _run_git(repo, "merge-base", "HEAD", base_name)
            if merge_base.returncode == 0:
                mb = merge_base.stdout.strip()
                if mb:
                    diff = _run_git(repo, "diff", "--name-only", f"{mb}..HEAD")
                    if diff.returncode == 0:
                        files = _parse_changed_files(diff.stdout)
                        if files:
                            return files, f"merge-base:{base_name}", notes
                        notes.append(f"merge-base diff empty ({base_name})")
                    else:
                        notes.append(
                            f"merge-base diff failed ({base_name}): {diff.stderr.strip() or diff.stdout.strip()}"
                        )
                else:
                    notes.append(f"merge-base empty for {base_name}")
            else:
                notes.append(f"merge-base failed for {base_name}: {merge_base.stderr.strip() or merge_base.stdout.strip()}")
        else:
            notes.append(f"base ref not found: {base_name}")

    # Push events: compare against the previous SHA from event payload.
    if before_sha and set(before_sha) != {"0"}:
        before_check = _run_git(repo, "rev-parse", "--verify", before_sha)
        if before_check.returncode == 0:
            diff = _run_git(repo, "diff", "--name-only", f"{before_sha}..HEAD")
            if diff.returncode == 0:
                files = _parse_changed_files(diff.stdout)
                if files:
                    return files, f"push-before:{before_sha[:12]}", notes
                notes.append(f"push-before diff empty ({before_sha[:12]})")
            else:
                notes.append(f"before-sha diff failed: {diff.stderr.strip() or diff.stdout.strip()}")
        else:
            notes.append(f"before sha not found: {before_sha[:12]}")

    # Legacy fallback for local workflows.
    for base in ("origin/master", "origin/main"):
        base_check = _run_git(repo, "rev-parse", "--verify", base)
        if base_check.returncode != 0:
            continue
        diff = _run_git(repo, "diff", "--name-only", f"{base}...HEAD")
        if diff.returncode == 0:
            files = _parse_changed_files(diff.stdout)
            if files:
                return files, f"triple-dot:{base}", notes
            notes.append(f"triple-dot diff empty ({base})")
        else:
            notes.append(f"triple-dot diff failed ({base}): {diff.stderr.strip() or diff.stdout.strip()}")

    # Working tree fallback.
    wt = _run_git(repo, "diff", "--name-only")
    if wt.returncode == 0:
        files = _parse_changed_files(wt.stdout)
        if files:
            return files, "working-tree", notes
    else:
        notes.append(f"working-tree diff failed: {wt.stderr.strip() or wt.stdout.strip()}")

    # Include untracked files for local/manual runs.
    status = _run_git(repo, "status", "--porcelain")
    if status.returncode == 0:
        files = _parse_status_porcelain(status.stdout)
        if files:
            return files, "status-porcelain", notes
    else:
        notes.append(f"status porcelain failed: {status.stderr.strip() or status.stdout.strip()}")

    # Final fallback: last commit delta (best effort for CI/local ad-hoc runs).
    head_prev = _run_git(repo, "rev-parse", "--verify", "HEAD~1")
    if head_prev.returncode == 0:
        diff = _run_git(repo, "diff", "--name-only", "HEAD~1..HEAD")
        if diff.returncode == 0:
            files = _parse_changed_files(diff.stdout)
            if files:
                return files, "head-prev", notes
            notes.append("HEAD~1 diff empty")
        else:
            notes.append(f"HEAD~1 diff failed: {diff.stderr.strip() or diff.stdout.strip()}")

    # CI must never silently skip because base resolution failed.
    if is_ci and event_name in ("pull_request", "push"):
        return [], "ci-unresolved", notes
    return [], "none", notes


def _matches_path_prefix(path: str, prefixes: list[str]) -> bool:
    return any(path == p or path.startswith(p) for p in prefixes)


def _merge_with_local_diffs(repo: Path, files: list[str]) -> list[str]:
    """
    Merge discovered change-set with current local diffs.

    This keeps local/manual runs actionable when git-base heuristics resolve to a
    branch-range diff, while CI/pre-commit behavior remains strict.
    """
    merged: list[str] = list(dict.fromkeys(files))
    local_cmds = (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
    )
    for cmd in local_cmds:
        result = _run_git(repo, *cmd)
        if result.returncode != 0:
            continue
        for path in _parse_changed_files(result.stdout):
            if path not in merged:
                merged.append(path)
    return merged


def check_docs_updated_for_code_changes(repo: Path) -> list[str]:
    """
    Check that if code paths are modified, docs are also modified.

    This is a diff-based check for CI and pre-commit workflows.
    """
    errors = []

    # Paths that require doc updates when changed.
    code_path_prefixes = [
        "audioknob_gui/worker/",
        "audioknob_gui/gui/",
        "audioknob_gui/platform/",
        "config/registry.json",
        "config/registry.schema.json",
        "pyproject.toml",
        "bin/",
        "packaging/",
        "scripts/check_repo_consistency.py",
        "scripts/run_quality_gate.py",
        ".github/workflows/",
    ]

    doc_paths = {"PLAN.md", "PROJECT_STATE.md"}

    changed_files, source, notes = _resolve_changed_files(repo)
    if source == "ci-unresolved":
        detail = "; ".join(notes) if notes else "no diff base could be resolved"
        errors.append(
            "Unable to determine changed files in CI; refusing to skip docs-update gate.\n"
            f"  Diagnostics: {detail}"
        )
        return errors

    changed_files = _merge_with_local_diffs(repo, changed_files)

    if not changed_files:
        return []

    code_touched = any(_matches_path_prefix(path, code_path_prefixes) for path in changed_files)
    if not code_touched:
        return []

    doc_touched = any(path in doc_paths for path in changed_files)
    if doc_touched:
        return []

    result = _run_git(repo, "log", "-1", "--format=%B")
    commit_msg = (result.stdout or "").lower()
    if "docs-not-needed:" in commit_msg:
        return []

    extra = f"\n  Diff source: {source}" if source not in ("none", "") else ""
    errors.append(
        "Code changes detected without doc updates.\n"
        "  Modified code paths require PLAN.md or PROJECT_STATE.md to also be updated.\n"
        "  If this is a pure refactor with no behavior change, add 'docs-not-needed:' to commit message."
        + extra
    )
    return errors


def check_knob_interactions_updated_for_behavior_changes(repo: Path) -> list[str]:
    """
    Check that conflict/knob behavior changes update docs/KNOB_INTERACTIONS.md.

    This is a diff-based check for CI and pre-commit workflows.
    """
    errors: list[str] = []

    behavior_path_prefixes = [
        "config/registry.json",
        "audioknob_gui/worker/",
        "audioknob_gui/gui/conflicts.py",
        "audioknob_gui/gui/simple_mode.py",
        "audioknob_gui/gui/actions.py",
    ]
    interactions_doc = "docs/KNOB_INTERACTIONS.md"

    changed_files, source, notes = _resolve_changed_files(repo)
    if source == "ci-unresolved":
        detail = "; ".join(notes) if notes else "no diff base could be resolved"
        errors.append(
            "Unable to determine changed files in CI; refusing to skip KNOB_INTERACTIONS gate.\n"
            f"  Diagnostics: {detail}"
        )
        return errors

    changed_files = _merge_with_local_diffs(repo, changed_files)

    if not changed_files:
        return []

    behavior_touched = any(_matches_path_prefix(path, behavior_path_prefixes) for path in changed_files)
    if not behavior_touched:
        return []

    if interactions_doc in changed_files:
        return []

    result = _run_git(repo, "log", "-1", "--format=%B")
    commit_msg = (result.stdout or "").lower()
    if "docs-not-needed:" in commit_msg:
        return []

    extra = f"\n  Diff source: {source}" if source not in ("none", "") else ""
    errors.append(
        "Conflict/knob behavior changes detected without docs/KNOB_INTERACTIONS.md update.\n"
        "  Modified behavior paths require docs/KNOB_INTERACTIONS.md to also be updated.\n"
        "  If this is a pure refactor with no conflict/dependency/behavior change, add 'docs-not-needed:' to commit message."
        + extra
    )
    return errors


def _read_stabilization_state(repo: Path) -> tuple[str | None, int | None, list[str], str | None]:
    rel_path = "docs/internal/audit/STABILIZATION_STATE.md"
    path = repo / rel_path
    if not path.exists():
        return None, None, [], None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None, None, [], f"failed reading {rel_path}"

    mode_match = re.search(r"^\s*Mode:\s*(ON|OFF)\s*$", text, flags=re.MULTILINE)
    mode = mode_match.group(1) if mode_match else None
    if mode is None:
        return None, None, [], f"{rel_path} missing required line: 'Mode: ON' or 'Mode: OFF'"

    max_files_match = re.search(r"^\s*Max changed files:\s*(\d+)\s*$", text, flags=re.MULTILINE)
    max_files = int(max_files_match.group(1)) if max_files_match else None

    allowed: list[str] = []
    in_allowed = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped == "Allowed paths:":
            in_allowed = True
            continue
        if not in_allowed:
            continue
        if stripped.startswith("## "):
            break
        if not stripped:
            continue
        if not stripped.startswith("- "):
            continue
        val = stripped[2:].strip()
        if val.startswith("`") and val.endswith("`") and len(val) >= 2:
            val = val[1:-1]
        if val:
            allowed.append(val)

    dedup_allowed = list(dict.fromkeys(allowed + [rel_path]))
    return mode, max_files, dedup_allowed, None


def check_stabilization_constraints(repo: Path) -> list[str]:
    """
    Enforce stabilization-mode scope constraints when enabled.

    This gate is driven by docs/internal/audit/STABILIZATION_STATE.md.
    """
    errors: list[str] = []
    mode, max_files, allowed_paths, state_error = _read_stabilization_state(repo)
    if state_error:
        errors.append(f"Invalid stabilization state: {state_error}")
        return errors
    if mode is None:
        return []
    if mode != "ON":
        return []

    changed_files, source, notes = _resolve_changed_files(repo)
    if source == "ci-unresolved":
        detail = "; ".join(notes) if notes else "no diff base could be resolved"
        errors.append(
            "Unable to determine changed files in CI; refusing to skip stabilization gate.\n"
            f"  Diagnostics: {detail}"
        )
        return errors

    is_ci = os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
    if is_ci:
        changed_files = _merge_with_local_diffs(repo, changed_files)
    else:
        # Local stabilization should enforce the active in-progress batch only,
        # not historical branch deltas against origin/*.
        changed_files = _merge_with_local_diffs(repo, [])
    if not changed_files:
        return []

    result = _run_git(repo, "log", "-1", "--format=%B")
    commit_msg = (result.stdout or "").lower()
    if "stabilization-waiver:" in commit_msg:
        return []

    if max_files is not None and len(changed_files) > max_files:
        errors.append(
            "Stabilization gate exceeded max changed files.\n"
            f"  Max changed files: {max_files}\n"
            f"  Found: {len(changed_files)}"
        )

    if not allowed_paths:
        errors.append(
            "Stabilization mode is ON but no allowlist is defined.\n"
            "  Add entries under 'Allowed paths:' in docs/internal/audit/STABILIZATION_STATE.md."
        )
        return errors

    out_of_scope = [p for p in changed_files if not _matches_path_prefix(p, allowed_paths)]
    if out_of_scope:
        preview = ", ".join(out_of_scope[:10])
        extra = "" if len(out_of_scope) <= 10 else f" (+{len(out_of_scope) - 10} more)"
        errors.append(
            "Stabilization gate found out-of-scope file changes.\n"
            "  Update docs/internal/audit/STABILIZATION_STATE.md allowlist or reduce scope.\n"
            f"  Files: {preview}{extra}"
        )
    return errors


def _literal_sequence_starts_with_pkexec(node: ast.AST) -> bool:
    if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
        return False
    first = node.elts[0]
    return isinstance(first, ast.Constant) and first.value == "pkexec"


def _collect_pkexec_sequence_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        value: ast.AST | None = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        if value is None or not _literal_sequence_starts_with_pkexec(value):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _iter_subprocess_run_calls(tree: ast.AST) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        if fn.attr != "run":
            continue
        if not isinstance(fn.value, ast.Name) or fn.value.id != "subprocess":
            continue
        calls.append(node)
    return calls


def _subprocess_run_args_node(call: ast.Call) -> ast.AST | None:
    if call.args:
        return call.args[0]
    for kw in call.keywords:
        if kw.arg == "args":
            return kw.value
    return None


def check_privilege_model_guards(repo: Path) -> list[str]:
    """Enforce privileged command guardrails in GUI code paths."""
    errors: list[str] = []

    gui_root = repo / "audioknob_gui" / "gui"
    for path in sorted(gui_root.rglob("*.py")):
        rel = path.relative_to(repo).as_posix()
        if rel == "audioknob_gui/gui/worker_api.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"Failed reading {rel}: {exc}")
            continue
        try:
            tree = ast.parse(text)
        except Exception as exc:
            errors.append(f"Failed parsing {rel}: {exc}")
            continue

        pkexec_names = _collect_pkexec_sequence_names(tree)
        for call in _iter_subprocess_run_calls(tree):
            args_node = _subprocess_run_args_node(call)
            if args_node is None:
                continue
            is_pkexec = _literal_sequence_starts_with_pkexec(args_node) or (
                isinstance(args_node, ast.Name) and args_node.id in pkexec_names
            )
            if not is_pkexec:
                continue
            line = getattr(call, "lineno", 1)
            errors.append(
                f"Direct pkexec subprocess.run outside worker_api: {rel}:{line}\n"
                "  Route privileged GUI commands through worker_api helpers."
            )

    worker_api_path = repo / "audioknob_gui" / "gui" / "worker_api.py"
    try:
        worker_api_text = worker_api_path.read_text(encoding="utf-8")
    except Exception as exc:
        errors.append(f"Failed reading audioknob_gui/gui/worker_api.py: {exc}")
        return errors

    if "/usr/libexec/audioknob-gui-worker" not in worker_api_text:
        errors.append(
            "worker_api must include fixed worker path /usr/libexec/audioknob-gui-worker"
        )
    legacy_paths = (
        "/usr/local/libexec/audioknob-gui-worker",
        "/usr/local/bin/audioknob-worker",
        "/usr/bin/audioknob-worker",
    )
    for legacy in legacy_paths:
        if legacy in worker_api_text:
            errors.append(
                f"Legacy worker fallback path detected in worker_api: {legacy}\n"
                "  Root knob operations must use fixed worker wrapper path."
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
        ("Semantic doc contracts", check_semantic_doc_contracts),
        ("Stabilization constraints", check_stabilization_constraints),
        ("KNOB_INTERACTIONS docs updates", check_knob_interactions_updated_for_behavior_changes),
        ("Privilege model guards", check_privilege_model_guards),
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

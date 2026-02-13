"""Tests for repository gate/enforcement scripts."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


def _load_script(name: str):
    repo = Path(__file__).resolve().parents[1]
    path = repo / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_g2_requires_targeted_tests(monkeypatch, tmp_path: Path) -> None:
    gate = _load_script("run_quality_gate")

    monkeypatch.setattr(gate, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(gate, "_run_step", lambda repo, label, cmd: True)

    rc = gate.run_quality_gate("g2", None, tests=[])
    assert rc == 1


def test_release_audit_checks_fail_on_open_critical(tmp_path: Path) -> None:
    gate = _load_script("run_quality_gate")

    cycle = tmp_path / "docs" / "internal" / "audit" / "2026-02-13"
    cycle.mkdir(parents=True)
    (cycle / "FINDINGS_LEDGER.md").write_text(
        """
# Findings Ledger

| ID | Severity | Confidence | Scope | Finding | Evidence | Proposed fix class | Status |
|---|---|---|---|---|---|---|---|
| F-001 | Critical | High | test | x | x | code | Planned |
""",
        encoding="utf-8",
    )
    (cycle / "ALIGNMENT_GAP_TRACKER.md").write_text(
        "Tracker status:\n- Closed\n",
        encoding="utf-8",
    )

    assert gate._run_release_audit_checks(tmp_path) is False


def test_release_audit_checks_pass_when_closed_and_resolved(tmp_path: Path) -> None:
    gate = _load_script("run_quality_gate")

    cycle = tmp_path / "docs" / "internal" / "audit" / "2026-02-13"
    cycle.mkdir(parents=True)
    (cycle / "FINDINGS_LEDGER.md").write_text(
        """
# Findings Ledger

| ID | Severity | Confidence | Scope | Finding | Evidence | Proposed fix class | Status |
|---|---|---|---|---|---|---|---|
| F-001 | Critical | High | test | x | x | code | Resolved |
""",
        encoding="utf-8",
    )
    (cycle / "ALIGNMENT_GAP_TRACKER.md").write_text(
        "Tracker status:\n- `Closed` (2026-02-13)\n",
        encoding="utf-8",
    )

    assert gate._run_release_audit_checks(tmp_path) is True


def test_privilege_guard_detects_direct_pkexec_outside_worker_api(tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    gui = tmp_path / "audioknob_gui" / "gui"
    gui.mkdir(parents=True)
    (gui / "worker_api.py").write_text(
        'def x():\n    return \"/usr/libexec/audioknob-gui-worker\"\n',
        encoding="utf-8",
    )
    (gui / "bad.py").write_text(
        'import subprocess\nsubprocess.run(["pkexec", "id"], check=False)\n',
        encoding="utf-8",
    )

    errors = consistency.check_privilege_model_guards(tmp_path)
    assert any("Direct pkexec subprocess.run outside worker_api" in e for e in errors)


def test_docs_gate_fails_when_ci_diff_base_unresolved(monkeypatch, tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: ([], "ci-unresolved", ["base resolution failed"]),
    )

    errors = consistency.check_docs_updated_for_code_changes(tmp_path)
    assert errors
    assert "Unable to determine changed files in CI" in errors[0]


def test_resolve_changed_files_falls_back_to_working_tree_when_triple_dot_is_empty(
    monkeypatch, tmp_path: Path
) -> None:
    consistency = _load_script("check_repo_consistency")

    def _cp(args: tuple[str, ...], *, rc: int = 0, stdout: str = "", stderr: str = ""):
        return subprocess.CompletedProcess(["git", *args], rc, stdout=stdout, stderr=stderr)

    def fake_run_git(repo: Path, *args: str):
        if args == ("diff", "--cached", "--name-only"):
            return _cp(args)
        if args == ("rev-parse", "--verify", "origin/master"):
            return _cp(args, stdout="abc123\n")
        if args == ("diff", "--name-only", "origin/master...HEAD"):
            return _cp(args)
        if args == ("rev-parse", "--verify", "origin/main"):
            return _cp(args, rc=1, stderr="unknown revision")
        if args == ("rev-parse", "--verify", "HEAD~1"):
            return _cp(args, rc=1, stderr="unknown revision")
        if args == ("diff", "--name-only"):
            return _cp(args, stdout="audioknob_gui/gui/status.py\n")
        if args == ("status", "--porcelain"):
            return _cp(args)
        raise AssertionError(f"Unexpected git call: {args}")

    monkeypatch.setattr(consistency, "_run_git", fake_run_git)
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_BEFORE", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    files, source, _notes = consistency._resolve_changed_files(tmp_path)
    assert source == "working-tree"
    assert files == ["audioknob_gui/gui/status.py"]


def test_privilege_guard_detects_variable_pkexec_args_outside_worker_api(tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    gui = tmp_path / "audioknob_gui" / "gui"
    gui.mkdir(parents=True)
    (gui / "worker_api.py").write_text(
        'def x():\n    return "/usr/libexec/audioknob-gui-worker"\n',
        encoding="utf-8",
    )
    (gui / "bad.py").write_text(
        "import subprocess\n"
        "cmd = ['pkexec', 'id']\n"
        "subprocess.run(cmd, check=False)\n",
        encoding="utf-8",
    )

    errors = consistency.check_privilege_model_guards(tmp_path)
    assert any("Direct pkexec subprocess.run outside worker_api" in e for e in errors)


def test_interactions_gate_fails_without_interactions_doc_update(
    monkeypatch, tmp_path: Path
) -> None:
    consistency = _load_script("check_repo_consistency")

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (["audioknob_gui/worker/ops.py"], "working-tree", []),
    )
    monkeypatch.setattr(
        consistency,
        "_run_git",
        lambda repo, *args: subprocess.CompletedProcess(["git", *args], 0, stdout="feat: worker tweak\n"),
    )

    errors = consistency.check_knob_interactions_updated_for_behavior_changes(tmp_path)
    assert errors
    assert "docs/KNOB_INTERACTIONS.md" in errors[0]


def test_interactions_gate_passes_when_interactions_doc_is_touched(
    monkeypatch, tmp_path: Path
) -> None:
    consistency = _load_script("check_repo_consistency")

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (
            ["audioknob_gui/gui/conflicts.py", "docs/KNOB_INTERACTIONS.md"],
            "working-tree",
            [],
        ),
    )

    errors = consistency.check_knob_interactions_updated_for_behavior_changes(tmp_path)
    assert errors == []


def test_interactions_gate_honors_docs_not_needed_commit_tag(
    monkeypatch, tmp_path: Path
) -> None:
    consistency = _load_script("check_repo_consistency")

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (["config/registry.json"], "working-tree", []),
    )
    monkeypatch.setattr(
        consistency,
        "_run_git",
        lambda repo, *args: subprocess.CompletedProcess(
            ["git", *args], 0, stdout="refactor: normalize code\n\ndocs-not-needed: no behavior drift\n"
        ),
    )

    errors = consistency.check_knob_interactions_updated_for_behavior_changes(tmp_path)
    assert errors == []


def test_interactions_gate_fails_when_ci_diff_base_unresolved(
    monkeypatch, tmp_path: Path
) -> None:
    consistency = _load_script("check_repo_consistency")

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: ([], "ci-unresolved", ["base resolution failed"]),
    )

    errors = consistency.check_knob_interactions_updated_for_behavior_changes(tmp_path)
    assert errors
    assert "Unable to determine changed files in CI" in errors[0]


def test_stabilization_gate_off_allows_changes(monkeypatch, tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    state = tmp_path / "docs" / "internal" / "audit" / "STABILIZATION_STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(
        "Mode: OFF\n"
        "Max changed files: 2\n"
        "Allowed paths:\n"
        "- `scripts/check_repo_consistency.py`\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (["audioknob_gui/worker/ops.py"], "working-tree", []),
    )
    monkeypatch.setattr(consistency, "_merge_with_local_diffs", lambda repo, files: files)

    errors = consistency.check_stabilization_constraints(tmp_path)
    assert errors == []


def test_stabilization_gate_enforces_max_changed_files(monkeypatch, tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    state = tmp_path / "docs" / "internal" / "audit" / "STABILIZATION_STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(
        "Mode: ON\n"
        "Max changed files: 1\n"
        "Allowed paths:\n"
        "- `scripts/check_repo_consistency.py`\n"
        "- `tests/test_gate_scripts.py`\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (
            ["scripts/check_repo_consistency.py", "tests/test_gate_scripts.py"],
            "working-tree",
            [],
        ),
    )
    monkeypatch.setattr(consistency, "_merge_with_local_diffs", lambda repo, files: files)
    monkeypatch.setattr(
        consistency,
        "_run_git",
        lambda repo, *args: subprocess.CompletedProcess(["git", *args], 0, stdout="feat: stabilization\n"),
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    errors = consistency.check_stabilization_constraints(tmp_path)
    assert errors
    assert "max changed files" in errors[0].lower()


def test_stabilization_gate_enforces_allowlist(monkeypatch, tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    state = tmp_path / "docs" / "internal" / "audit" / "STABILIZATION_STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(
        "Mode: ON\n"
        "Max changed files: 5\n"
        "Allowed paths:\n"
        "- `scripts/check_repo_consistency.py`\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (["audioknob_gui/worker/ops.py"], "working-tree", []),
    )
    monkeypatch.setattr(consistency, "_merge_with_local_diffs", lambda repo, files: files)
    monkeypatch.setattr(
        consistency,
        "_run_git",
        lambda repo, *args: subprocess.CompletedProcess(["git", *args], 0, stdout="feat: stabilization\n"),
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    errors = consistency.check_stabilization_constraints(tmp_path)
    assert errors
    assert "out-of-scope" in errors[0].lower()


def test_stabilization_gate_passes_when_scope_matches(monkeypatch, tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    state = tmp_path / "docs" / "internal" / "audit" / "STABILIZATION_STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(
        "Mode: ON\n"
        "Max changed files: 3\n"
        "Allowed paths:\n"
        "- `scripts/check_repo_consistency.py`\n"
        "- `docs/internal/audit/STABILIZATION_STATE.md`\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (
            ["scripts/check_repo_consistency.py", "docs/internal/audit/STABILIZATION_STATE.md"],
            "working-tree",
            [],
        ),
    )
    monkeypatch.setattr(consistency, "_merge_with_local_diffs", lambda repo, files: files)
    monkeypatch.setattr(
        consistency,
        "_run_git",
        lambda repo, *args: subprocess.CompletedProcess(["git", *args], 0, stdout="feat: stabilization\n"),
    )

    errors = consistency.check_stabilization_constraints(tmp_path)
    assert errors == []


def test_stabilization_gate_honors_commit_waiver(monkeypatch, tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    state = tmp_path / "docs" / "internal" / "audit" / "STABILIZATION_STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(
        "Mode: ON\n"
        "Max changed files: 1\n"
        "Allowed paths:\n"
        "- `scripts/check_repo_consistency.py`\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (["audioknob_gui/worker/ops.py"], "working-tree", []),
    )
    monkeypatch.setattr(consistency, "_merge_with_local_diffs", lambda repo, files: files)
    monkeypatch.setattr(
        consistency,
        "_run_git",
        lambda repo, *args: subprocess.CompletedProcess(
            ["git", *args], 0, stdout="refactor: emergency change\n\nstabilization-waiver: approved\n"
        ),
    )

    errors = consistency.check_stabilization_constraints(tmp_path)
    assert errors == []


def test_stabilization_gate_fails_on_invalid_state_file(tmp_path: Path) -> None:
    consistency = _load_script("check_repo_consistency")

    state = tmp_path / "docs" / "internal" / "audit" / "STABILIZATION_STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(
        "Max changed files: 5\n"
        "Allowed paths:\n"
        "- `scripts/check_repo_consistency.py`\n",
        encoding="utf-8",
    )

    errors = consistency.check_stabilization_constraints(tmp_path)
    assert errors
    assert "Invalid stabilization state" in errors[0]


def test_stabilization_gate_uses_local_diff_scope_outside_ci(
    monkeypatch, tmp_path: Path
) -> None:
    consistency = _load_script("check_repo_consistency")

    state = tmp_path / "docs" / "internal" / "audit" / "STABILIZATION_STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(
        "Mode: ON\n"
        "Max changed files: 2\n"
        "Allowed paths:\n"
        "- `scripts/check_repo_consistency.py`\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        consistency,
        "_resolve_changed_files",
        lambda repo: (["audioknob_gui/worker/ops.py"], "triple-dot:origin/master", []),
    )
    seen: list[list[str]] = []

    def fake_merge(repo: Path, files: list[str]) -> list[str]:
        seen.append(list(files))
        return ["scripts/check_repo_consistency.py"]

    monkeypatch.setattr(consistency, "_merge_with_local_diffs", fake_merge)
    monkeypatch.setattr(
        consistency,
        "_run_git",
        lambda repo, *args: subprocess.CompletedProcess(["git", *args], 0, stdout="feat: stabilization\n"),
    )
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    errors = consistency.check_stabilization_constraints(tmp_path)
    assert errors == []
    assert seen and seen[0] == []

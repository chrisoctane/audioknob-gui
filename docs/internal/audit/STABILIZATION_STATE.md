# Stabilization State

Purpose:
- Keep remediation work bounded, reproducible, and non-expansive.
- Prevent open-ended audit/fix loops and uncontrolled file churn.

Mode: ON
Batch ID: STAB-006
Objective: Prepare and publish release v0.7.4 (code/docs sync + changelog + checklist + tag).
Max changed files: 16

Allowed paths:
- `AGENTS.md`
- `PLAN.md`
- `PROJECT_STATE.md`
- `docs/KNOB_INTERACTIONS.md`
- `docs/internal/audit/QUALITY_GATE.md`
- `docs/internal/audit/STABILIZATION_STATE.md`
- `docs/internal/audit/MULTI_AGENT_CONTROL_SYSTEM.md`
- `docs/internal/audit/releases/`
- `CHANGELOG.md`
- `pyproject.toml`
- `audioknob_gui/gui/main_window.py`
- `audioknob_gui/gui/simple_mode.py`
- `audioknob_gui/gui/app_info.py`
- `audioknob_gui/__init__.py`
- `scripts/check_repo_consistency.py`
- `tests/test_gate_scripts.py`
- `tests/test_simple_mode.py`

Batch protocol:
1. Use read-only audit -> approved-fix batch -> read-only verification (no mixed passes).
2. Fix only approved finding IDs for the active batch.
3. If a new issue is discovered mid-batch, log it and defer unless it blocks current batch exit criteria.
4. Keep edits within allowlisted paths and file-count cap.
5. Waive only with explicit commit tag `stabilization-waiver:` and user approval.

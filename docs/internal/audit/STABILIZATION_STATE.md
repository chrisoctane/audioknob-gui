# Stabilization State

Purpose:
- Keep remediation work bounded, reproducible, and non-expansive.
- Prevent open-ended audit/fix loops and uncontrolled file churn.

Mode: ON
Batch ID: STAB-001
Objective: Bootstrap stabilization guardrails and enforce bounded scope.
Max changed files: 12

Allowed paths:
- `AGENTS.md`
- `PLAN.md`
- `PROJECT_STATE.md`
- `docs/KNOB_INTERACTIONS.md`
- `docs/internal/audit/QUALITY_GATE.md`
- `docs/internal/audit/STABILIZATION_STATE.md`
- `scripts/check_repo_consistency.py`
- `tests/test_gate_scripts.py`

Batch protocol:
1. Use read-only audit -> approved-fix batch -> read-only verification (no mixed passes).
2. Fix only approved finding IDs for the active batch.
3. If a new issue is discovered mid-batch, log it and defer unless it blocks current batch exit criteria.
4. Keep edits within allowlisted paths and file-count cap.
5. Waive only with explicit commit tag `stabilization-waiver:` and user approval.

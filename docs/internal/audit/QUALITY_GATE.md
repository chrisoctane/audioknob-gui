# Quality Gate (Agent + Maintainer)

Purpose:
- Provide a strict, repeatable quality gate for implementation, parity work,
  and release readiness.
- Prevent drift between runtime code, contracts, and audit artifacts.

Scope:
- Code under `audioknob_gui/**`
- Contracts and docs (`PLAN.md`, `PROJECT_STATE.md`, audit docs)
- Registry/schema and packaged copies

Execution helper:
- Use `scripts/run_quality_gate.py` as the canonical wrapper:
  - `--gate g1` for change gate
  - `--gate g2` for parity gate
  - `--gate ci` for CI baseline (`G1` + tests)
  - `--gate g3 --release-version vX.Y.Z` for release gate

Status model:
- `PASS`: gate satisfied with evidence
- `FAIL`: gate not satisfied; stop and remediate
- `WAIVED`: only by explicit user approval in-thread, with rationale recorded

## Gate levels

### G0 - Session start gate (required before edits)
1. Read required docs for the task (`AGENTS.md` + task-specific docs).
2. Confirm no unexpected local changes.
3. Locate existing code path/helpers before introducing new logic.

Exit criteria:
- All three checks complete.

### G1 - Change gate (required for any change)
Required checks:
1. `python3 scripts/check_repo_consistency.py`
2. `python3 -m compileall -q audioknob_gui`

Doc sync requirements:
1. Behavior/architecture changes -> update `PROJECT_STATE.md`
2. User workflow changes -> update `PLAN.md`
3. Registry/schema changes -> sync:
   - `config/registry.json` -> `audioknob_gui/data/registry.json`
   - `config/registry.schema.json` -> `audioknob_gui/data/registry.schema.json`
4. Knob behavior/conflict/dependency changes -> update `docs/KNOB_INTERACTIONS.md`

Exit criteria:
- Both required checks `PASS`
- Required doc sync items completed

### G2 - Parity gate (required when touching knobs/systems/audit)
Trigger conditions (any):
1. Worker kind behavior changed (preview/apply/reset/status/force-reset)
2. GUI queue/lock/conflict/status behavior changed
3. Knob metadata, dependencies, or conflicts changed
4. Audit findings or parity docs updated

Required checks:
1. Targeted pytest for touched behavior (must include affected paths)
2. Re-run G1 checks
3. Ensure intentional exceptions remain explicitly documented:
   - `group_membership` special-case immediate workflow
   - `read_only` diagnostic kinds
   - `wpctl_profile` safe-decline force-reset behavior

Recommended checks:
1. Full test suite: `.venv/bin/python -m pytest -q`

Exit criteria:
- Targeted tests `PASS`
- G1 checks `PASS`
- Exception contracts still accurate

### G3 - Release gate (required for release/tag/build uploads)
Required checks:
1. Full test suite `PASS`:
   - `.venv/bin/python -m pytest -q`
2. G1 checks `PASS`
3. Release docs updated:
   - `CHANGELOG.md`
   - release/version references in `PLAN.md` and `PROJECT_STATE.md` (if changed)
4. Audit status reviewed:
   - No unresolved Blocker/Critical findings
   - Alignment tracker closed, or explicit deferred scope with rationale
5. Release checklist artifact present:
   - `docs/internal/audit/releases/v<version>/CHECKLIST.md`
   - Must include exact lines:
     - `Release version: <version>`
     - `Final status: PASS`

Exit criteria:
- All required checks `PASS`
- No release-blocking findings remain

## Feature-complete definition

A feature/workstream is "complete" only when:
1. Runtime behavior is implemented and tested.
2. Contracts are aligned (`PLAN.md`, `PROJECT_STATE.md`, and interaction docs).
3. Audit artifacts reflect final disposition (no stale "current state" drift).
4. G1 + applicable G2/G3 gates are `PASS`.

## Evidence format (required in final report)

For each gate run, include:
1. Commands executed
2. Result (`PASS`/`FAIL`)
3. Any waivers and rationale
4. Remaining risks or explicit "none"

## Failure policy

If any required gate fails:
1. Stop further feature work.
2. Fix failing gate first.
3. Re-run failed and dependent gates.
4. Report failure + remediation in the session summary.

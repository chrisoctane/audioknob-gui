# Remediation Batches

## 2026-02-12 - Phase 5 planning disposition

Planning scope:
- Open findings entering Phase 5: `AK-AUD-001`, `AK-AUD-002`
- Already resolved in Phase 4: `AK-AUD-003`

Planning outcome:
1. `AK-AUD-002` is assigned to an implementation batch (`RB-001`) for parity remediation.
2. `AK-AUD-001` is explicitly deferred (`RB-002`) with rationale/milestone.
3. All findings now have a release disposition (planned/deferred/resolved).

---

## `RB-001` - Force-reset parity expansion

- Findings covered: `AK-AUD-002`
- Priority: `P1` (highest open severity in this cycle)
- Severity target: `Medium -> resolved`
- Fix class: `cross-system parity batch`
- Status: `Planned`

### Objective
Add explicit `force-reset-knob` support for full-parity kinds that currently rely on transaction-only fallback:
- `irq_affinity`
- `power_profile`
- `qjackctl_server_prefix`
- `wpctl_profile`

### Scope (planned files)
- `audioknob_gui/worker/cli.py`
- `audioknob_gui/worker/ops.py` (if helper reuse is needed)
- `tests/*` (new/updated worker parity tests for added kinds)
- `PROJECT_STATE.md` (force-reset support matrix/status line updates)

### Constraints
- Preserve guardrails: no silent/automatic reset behavior.
- Force reset remains explicit and user-confirmed.
- Keep surgical reset semantics for shared files/resources.
- Do not change normal transaction restore flow.

### Implementation plan
1. Add dedicated force-reset handler branches for the four kinds in `cmd_force_reset_knob`.
2. Reuse existing helper paths where behavior is already deterministic.
3. For kinds that cannot be safely reset without context, return explicit unsupported details rather than generic failure.
4. Add/extend tests for each new kind branch.
5. Re-run repo consistency + compile gates.

### Verification plan
1. `python3 scripts/check_repo_consistency.py`
2. `python3 -m compileall -q audioknob_gui`
3. `python3 -m audioknob_gui.worker.cli force-reset-knob <id>` for representative knobs per kind.
4. If pytest is available in environment: targeted worker CLI parity tests for force-reset branches.

### Exit criteria
- `AK-AUD-002` marked `Resolved`.
- `cmd_force_reset_knob` has explicit support (or explicit safe-decline rationale) for all full-parity kinds.
- No new Blocker/Critical findings introduced.

---

## `RB-002` - Group membership special-case contract hardening

- Findings covered: `AK-AUD-001`
- Priority: `P3`
- Severity target: `Low`
- Fix class: `contract/docs only`
- Status: `Deferred`

### Objective
Keep `group_membership` as an intentional special-case path while making contract language unambiguous for future contributors.

### Defer rationale
- Current behavior is intentional and stable for the release branch.
- Converting `group_membership` into full queue parity would require root group-mutation workflow changes with non-trivial UX/safety impact.
- This is not required to close current safety/functionality goals.

### Deferred milestone
- Re-evaluate during next architecture cycle (`v0.8.x` planning + audit refresh).

### Deferred acceptance note
- Until rework is approved, retain explicit special-case classification in audit artifacts and kind matrix.

---

## Batch order and release gating

1. `RB-001` (required before Phase 6 closeout of open Medium finding)
2. `RB-002` (deferred by rationale; not release-blocking)

---

## Findings disposition map

| Finding | Disposition | Batch | Notes |
|---|---|---|---|
| `AK-AUD-001` | Deferred | `RB-002` | Intentional special-case; revisit in `v0.8.x` planning |
| `AK-AUD-002` | Planned | `RB-001` | Open Medium parity gap; implementation batch required |
| `AK-AUD-003` | Resolved | N/A | Closed in Phase 4 via docs coherence fix |

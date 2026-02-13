# Remediation Batches

## 2026-02-12 - Phase 5 planning disposition

Planning scope:
- Open findings entering Phase 5: `AK-AUD-001`, `AK-AUD-002`
- Already resolved in Phase 4: `AK-AUD-003`

Planning outcome:
1. `AK-AUD-002` is assigned to an implementation batch (`RB-001`) for parity remediation.
2. `AK-AUD-001` is explicitly deferred (`RB-002`) with rationale/milestone.
3. All findings now have a release disposition (planned/deferred/resolved).

Closeout update:
1. `RB-001` completed on 2026-02-12; `AK-AUD-002` resolved.
2. `RB-002` completed on 2026-02-12 via contract hardening; `AK-AUD-001` resolved.
3. No open audit findings remain in this batch set.

---

## `RB-001` - Force-reset parity expansion

- Findings covered: `AK-AUD-002`
- Priority: `P1` (highest open severity in this cycle)
- Severity target: `Medium -> resolved`
- Fix class: `cross-system parity batch`
- Status: `Completed (2026-02-12)`

### Objective
Add explicit `force-reset-knob` support for full-parity kinds that currently rely on transaction-only fallback:
- `irq_affinity`
- `power_profile`
- `qjackctl_server_prefix`
- `wpctl_profile`

### Scope (implemented files)
- `audioknob_gui/worker/cli.py`
- `audioknob_gui/gui/main_window.py`
- `tests/*` (new/updated worker parity tests for added kinds)
- `PROJECT_STATE.md` and `PLAN.md` (force-reset support matrix/status line updates)

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

### Implementation outcome (2026-02-12)
1. Added explicit `force-reset-knob` branches for:
   - `irq_affinity` (generic reset to kernel default IRQ mask + persistence cleanup)
   - `power_profile` (backend-aware conservative reset to `balanced`)
   - `qjackctl_server_prefix` (strip RT/taskset + clear audioknob post-start artifacts)
   - `wpctl_profile` (explicit deterministic safe-decline when fallback profile cannot be inferred safely)
2. Expanded GUI `_force_reset_supported` allowlist to include the above kinds.
3. Added targeted CLI tests for new dispatch/decline behavior.
4. Re-ran compile and consistency gates successfully.

---

## `RB-002` - Group membership special-case contract hardening

- Findings covered: `AK-AUD-001`
- Priority: `P3`
- Severity target: `Low`
- Fix class: `contract/docs only`
- Status: `Completed (2026-02-12)`

### Objective
Keep `group_membership` as an intentional special-case path while making contract language unambiguous for future contributors.

### Contract rationale
- Current behavior is intentional and stable for the release branch.
- Converting `group_membership` into full queue parity would require root group-mutation workflow changes with non-trivial UX/safety impact.
- The required fix for this batch was documentation/contract hardening, not architectural rework.

### Implementation outcome (2026-02-12)
1. `PLAN.md` now explicitly states `group_membership` is outside worker preview/apply/reset/force-reset transaction flows.
2. `PROJECT_STATE.md` now includes a matching special-case contract block in the implementation-kinds section.
3. Audit disposition files now mark `AK-AUD-001` as resolved-by-contract (`RB-002` complete).

### Residual note
- Optional future architecture work (`v0.8.x+`): implement full queue/apply/reset parity for `group_membership` if product direction requires it.

---

## Batch order and release gating

1. `RB-001` (completed; no longer open)
2. `RB-002` (completed; no longer open)

---

## Findings disposition map

| Finding | Disposition | Batch | Notes |
|---|---|---|---|
| `AK-AUD-001` | Resolved | `RB-002` | Special-case contract hardened in `PLAN.md` + `PROJECT_STATE.md` |
| `AK-AUD-002` | Resolved | `RB-001` | Closed in Phase 6 after force-reset parity expansion |
| `AK-AUD-003` | Resolved | N/A | Closed in Phase 4 via docs coherence fix |

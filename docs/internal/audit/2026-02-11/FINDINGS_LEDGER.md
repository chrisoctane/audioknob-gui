# Findings Ledger

Current disposition snapshot:
- `AK-AUD-001`: Resolved (2026-02-12, `RB-002`)
- `AK-AUD-002`: Resolved (2026-02-12, `RB-001`)
- `AK-AUD-003`: Resolved (2026-02-12)
- Historical phase notes below preserve time-ordered status at each checkpoint.

## 2026-02-12 - Phase 2 kind-level audit

| ID | Severity | Confidence | Scope | Finding | Evidence | Proposed fix class | Status |
|---|---|---|---|---|---|---|---|
| `AK-AUD-001` | Low | High | `group_membership` kind | `group_membership` is intentionally outside the standard queue preview/apply/reset pipeline; it remains status-only from worker parity perspective. | `audioknob_gui/worker/ops.py` (`check_knob_status` has `group_membership` branch) and `audioknob_gui/worker/ops.py` (`preview` has no `group_membership` handler branch). | contract/docs only | Resolved (2026-02-12, `RB-002` contract closure) |
| `AK-AUD-002` | Medium | High | force-reset parity | Force-reset coverage was not uniform across full-parity kinds (`irq_affinity`, `power_profile`, `qjackctl_server_prefix`, `wpctl_profile`). | Historical gap: `audioknob_gui/worker/cli.py` (`cmd_force_reset_knob`) and `audioknob_gui/gui/main_window.py` (`_force_reset_supported`) omitted these kinds; resolved by adding explicit handlers/allowlist support (including deterministic safe-decline for `wpctl_profile`). | cross-system parity batch | Resolved (2026-02-12, `RB-001`) |
| `AK-AUD-003` | Low | High | docs coherence (mode-switch workflow) | User workflow docs referenced Tools-menu mode switching while runtime uses the far-left header `View` button. | `audioknob_gui/gui/main_window.py` (`btn_view` + `_on_toggle_view`/`_set_ui_mode`) compared with stale wording in `PLAN.md` and `PROJECT_STATE.md` before Phase 4 correction. | contract/docs only | Resolved (2026-02-12) |

Notes:
- No Blocker/Critical systemic parity failures found in Phase 2.

## 2026-02-12 - Phase 3 Slice A note

- No additional Slice A-specific findings were added.
- At this phase checkpoint, `AK-AUD-001` and `AK-AUD-002` were open and carried forward to remediation planning.

## 2026-02-12 - Phase 3 Slice B note

- No additional Slice B-specific findings were added.
- At this phase checkpoint, `AK-AUD-002` was the active parity gap for non-uniform force-reset fallback across some full-parity kinds.

## 2026-02-12 - Phase 3 Slice C note

- No additional Slice C-specific findings were added.
- At this phase checkpoint, `AK-AUD-002` remained open and was explicitly evidenced by `irq_pinning` (`irq_affinity` kind) in knob-level review.

## 2026-02-12 - Phase 3 Slice D note

- No additional Slice D-specific findings were added.
- Phase 3 worksheet completion and coherence cleanup did not introduce new parity gaps.
- At this phase checkpoint, `AK-AUD-001` and `AK-AUD-002` remained open and moved forward to Phase 4/5 planning.

## 2026-02-12 - Phase 4 coherence note

- Conflict-map runtime and interaction docs are aligned for mapped conflict families.
- Row-level and header-level conflict indicators both use active/queued filtering + tuned-backend pruning.
- Simple-mode queue/ownership-lock behavior matches the documented lock/release contract.
- `AK-AUD-003` (mode-switch wording drift) was fixed directly in `PLAN.md` and `PROJECT_STATE.md`.
- At this phase checkpoint, `AK-AUD-001` and `AK-AUD-002` remained open for Phase 5 remediation planning.

## 2026-02-12 - Phase 5 planning note

- `AK-AUD-002` is assigned to remediation batch `RB-001` (planned implementation batch).
- `AK-AUD-001` is explicitly deferred as `RB-002` with milestone re-evaluation in `v0.8.x` planning.
- `REMEDIATION_BATCHES.md` is now populated and every finding has a concrete disposition.

## 2026-02-12 - Audit docs consistency sweep note

- No new findings were identified.
- Audit-doc wording drift was corrected in `KNOB_WORKSHEET.md` and `KIND_PARITY_MATRIX.md` without changing finding dispositions.

## 2026-02-12 - Phase 6 pre-close verification note

- No new findings were identified in the pre-close drift/evidence pass.
- At this phase checkpoint, `AK-AUD-002` remained open and planned in `RB-001`; implementation had not landed yet.
- At this phase checkpoint, `AK-AUD-001` remained deferred by approved rationale (`RB-002`).

## 2026-02-12 - Phase 6 closeout note

- `RB-001` implementation is complete and validated with consistency/compile gates.
- `AK-AUD-002` is now resolved:
  - `irq_affinity`: explicit generic force reset to kernel default IRQ mask + persistence cleanup.
  - `power_profile`: explicit conservative backend-aware reset to `balanced` with verification.
  - `qjackctl_server_prefix`: explicit reset of RT/taskset/post-start artifacts.
  - `wpctl_profile`: explicit safe-decline when deterministic fallback profile inference is unsafe.
- At this phase checkpoint, `AK-AUD-001` remained deferred as planned (`RB-002`).

## 2026-02-12 - Post-close alignment extraction note

- No new audit findings were identified in the post-close sweep.
- Open non-audit backlog/research items were centralized in:
  - `docs/internal/audit/2026-02-11/ALIGNMENT_GAP_TRACKER.md`

## 2026-02-12 - Phase A contract closure note

- `AK-AUD-001` is now resolved through `RB-002` contract hardening:
  - `PLAN.md` and `PROJECT_STATE.md` explicitly codify `group_membership` as an intentional immediate-action special-case.
  - Audit disposition files now align on resolved status for this finding.

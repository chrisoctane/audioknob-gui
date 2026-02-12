# Findings Ledger

## 2026-02-12 - Phase 2 kind-level audit

| ID | Severity | Confidence | Scope | Finding | Evidence | Proposed fix class | Status |
|---|---|---|---|---|---|---|---|
| `AK-AUD-001` | Low | High | `group_membership` kind | `group_membership` is intentionally outside the standard queue preview/apply/reset pipeline; it remains status-only from worker parity perspective. | `audioknob_gui/worker/ops.py` (`check_knob_status` has `group_membership` branch) and `audioknob_gui/worker/ops.py` (`preview` has no `group_membership` handler branch). | contract/docs only | Open |
| `AK-AUD-002` | Medium | High | force-reset parity | Force-reset coverage is not uniform across full-parity kinds (`irq_affinity`, `power_profile`, `qjackctl_server_prefix`, `wpctl_profile` are transaction-only). | `audioknob_gui/worker/cli.py` (`cmd_force_reset_knob` supported-kind switch omits these kinds). | cross-system parity batch | Open |
| `AK-AUD-003` | Low | High | docs coherence (mode-switch workflow) | User workflow docs referenced Tools-menu mode switching while runtime uses the far-left header `View` button. | `audioknob_gui/gui/main_window.py` (`btn_view` + `_on_toggle_view`/`_set_ui_mode`) compared with stale wording in `PLAN.md` and `PROJECT_STATE.md` before Phase 4 correction. | contract/docs only | Resolved (2026-02-12) |

Notes:
- No Blocker/Critical systemic parity failures found in Phase 2.

## 2026-02-12 - Phase 3 Slice A note

- No additional Slice A-specific findings were added.
- `AK-AUD-001` and `AK-AUD-002` remain open and are carried forward to remediation planning.

## 2026-02-12 - Phase 3 Slice B note

- No additional Slice B-specific findings were added.
- `AK-AUD-002` remains the active parity gap for non-uniform force-reset fallback across some full-parity kinds.

## 2026-02-12 - Phase 3 Slice C note

- No additional Slice C-specific findings were added.
- `AK-AUD-002` remains open and is now explicitly evidenced by `irq_pinning` (`irq_affinity` kind) in knob-level review.

## 2026-02-12 - Phase 3 Slice D note

- No additional Slice D-specific findings were added.
- Phase 3 worksheet completion and coherence cleanup did not introduce new parity gaps.
- `AK-AUD-001` and `AK-AUD-002` remain open and move forward to Phase 4/5 planning.

## 2026-02-12 - Phase 4 coherence note

- Conflict-map runtime and interaction docs are aligned for mapped conflict families.
- Row-level and header-level conflict indicators both use active/queued filtering + tuned-backend pruning.
- Simple-mode queue/ownership-lock behavior matches the documented lock/release contract.
- `AK-AUD-003` (mode-switch wording drift) was fixed directly in `PLAN.md` and `PROJECT_STATE.md`.
- `AK-AUD-001` and `AK-AUD-002` remain open for Phase 5 remediation planning.

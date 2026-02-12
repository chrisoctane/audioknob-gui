# Findings Ledger

## 2026-02-12 - Phase 2 kind-level audit

| ID | Severity | Confidence | Scope | Finding | Evidence | Proposed fix class | Status |
|---|---|---|---|---|---|---|---|
| `AK-AUD-001` | Low | High | `group_membership` kind | `group_membership` is intentionally outside the standard queue preview/apply/reset pipeline; it remains status-only from worker parity perspective. | `audioknob_gui/worker/ops.py` (`check_knob_status` has `group_membership` branch) and `audioknob_gui/worker/ops.py` (`preview` has no `group_membership` handler branch). | contract/docs only | Open |
| `AK-AUD-002` | Medium | High | force-reset parity | Force-reset coverage is not uniform across full-parity kinds (`irq_affinity`, `power_profile`, `qjackctl_server_prefix`, `wpctl_profile` are transaction-only). | `audioknob_gui/worker/cli.py` (`cmd_force_reset_knob` supported-kind switch omits these kinds). | cross-system parity batch | Open |

Notes:
- No Blocker/Critical systemic parity failures found in Phase 2.

## 2026-02-12 - Phase 3 Slice A note

- No additional Slice A-specific findings were added.
- `AK-AUD-001` and `AK-AUD-002` remain open and are carried forward to remediation planning.

## 2026-02-12 - Phase 3 Slice B note

- No additional Slice B-specific findings were added.
- `AK-AUD-002` remains the active parity gap for non-uniform force-reset fallback across some full-parity kinds.

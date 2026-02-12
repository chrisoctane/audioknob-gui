# Verification Report

## 2026-02-12 - Phase 1 baseline freeze

### Baseline metadata
- UTC timestamp: `2026-02-12T17:12:41Z`
- Branch: `master`
- Commit: `4384eae387dce2a0715dbf7828deb03908a09d13` (`4384eae`)

### Inventory re-check
- Total knobs: `48`
- Total categories: `10`
- Total implementation kinds: `17`

### Commands run
1. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
  - Summary: registry/docs/semantic contracts/compile checks all passed.
2. `python3 -m compileall -q audioknob_gui`
  - Result: `pass`

### Phase-1 disposition
- Phase 1 exit criteria: `met`
- Baseline locked for current audit cycle.

## 2026-02-12 - Phase 2 kind-level parity audit

### Scope checked
- All `17` implementation kinds in `config/registry.json`.
- Worker preview/apply/status/force-reset switch coverage against kind set.

### Commands/evidence collection
1. `rg -n \"kind ==|impl.kind|cmd_force_reset_knob|preview|check_knob_status\" audioknob_gui/worker/ops.py audioknob_gui/worker/cli.py`
  - Result: `pass`
  - Summary: every active kind mapped to a parity disposition; special-case kinds retained as documented exceptions.

### Outputs updated
- `docs/internal/audit/2026-02-11/KIND_PARITY_MATRIX.md`
- `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`

### Phase-2 disposition
- Phase 2 exit criteria: `met`
- No Blocker/Critical findings raised.

## 2026-02-12 - Phase 3 Slice A (permissions/vm/cpu/power)

### Scope checked
- Knobs: `cpu_dma_latency_udev`, `cpu_governor_performance_persistent`,
  `audio_group_membership`, `pipewire_rt_limits_group`, `realtime_clock_access`,
  `rt_limits_audio_group`, `power_profile_performance`, `usb_autosuspend_disable`,
  `dirty_bytes`, `inotify_max_watches`, `swappiness`, `thp_mode_madvise`.

### Outputs updated
- `docs/internal/audit/2026-02-11/KNOB_WORKSHEET.md` (Slice A entries populated)

### Finding summary
- New findings added in this slice: `0`
- Existing findings referenced: `AK-AUD-001`, `AK-AUD-002`

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

## 2026-02-12 - Phase 3 Slice B (stack/services)

### Scope checked
- Knobs: `disable_baloo`, `disable_tracker`, `rtkit_daemon_tuning`,
  `pipewire_clock_constraints`, `pipewire_data_loop_affinity`,
  `pipewire_mlock_policy`, `pipewire_pro_audio_profile`, `pipewire_quantum`,
  `pipewire_rt_module_tuning`, `pipewire_rt_setup`, `pipewire_sample_rate`,
  `qjackctl_server_prefix_rt`.

### Outputs updated
- `docs/internal/audit/2026-02-11/KNOB_WORKSHEET.md` (Slice B entries populated)

### Finding summary
- New findings added in this slice: `0`
- Existing findings referenced: `AK-AUD-001`, `AK-AUD-002`

## 2026-02-12 - Phase 3 Slice C (irq/kernel)

### Scope checked
- Knobs: `irq_pinning`, `irqbalance_disable`, `rtirq_enable`,
  `kernel_audit_off`, `kernel_clocksource_tsc`, `kernel_cstate_limit`,
  `kernel_intel_idle_cstate_limit`, `kernel_irqaffinity`, `kernel_isolcpus`,
  `kernel_mitigations_off`, `kernel_nmi_watchdog_off`, `kernel_nohz_full`,
  `kernel_nosmt`, `kernel_nosoftlockup`, `kernel_preempt_full`,
  `kernel_rcu_nocbs`, `kernel_rt_throttling_off`, `kernel_threadirqs`,
  `kernel_tsc_reliable`.

### Outputs updated
- `docs/internal/audit/2026-02-11/KNOB_WORKSHEET.md` (Slice C entries populated and corrected for knob-specific evidence mapping)

### Finding summary
- New findings added in this slice: `0`
- Existing findings referenced: `AK-AUD-002`

## 2026-02-12 - Phase 3 Slice D (testing/read-only + coherence cleanup)

### Scope checked
- Knobs: `blocker_check`, `pipewire_xrun_monitor`, `scheduler_jitter_test`, `stack_detect`.
- Worksheet coherence cleanup: completed remaining VM knob parity sections (`dirty_bytes`, `inotify_max_watches`, `swappiness`, `thp_mode_madvise`) and removed all worksheet TODO placeholders.

### Outputs updated
- `docs/internal/audit/2026-02-11/KNOB_WORKSHEET.md` (Slice D completion + Phase 3 marked complete)
- `docs/internal/audit/2026-02-11/KNOB_AUDIT_PLAN.md` (Phase 3 marked complete; resume point moved to Phase 4)

### Commands run
1. `rg -n "TODO" docs/internal/audit/2026-02-11/KNOB_WORKSHEET.md`
  - Result: `pass`
  - Summary: no remaining TODO placeholders in worksheet.
2. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
3. `python3 -m compileall -q audioknob_gui`
  - Result: `pass`

### Finding summary
- New findings added in this slice: `0`
- Existing findings referenced: `AK-AUD-001`, `AK-AUD-002`

### Phase-3 disposition
- Phase 3 exit criteria: `met`

## 2026-02-12 - Phase 4 cross-system coherence audit

### Scope checked
- Conflict-map contract coherence: `docs/KNOB_INTERACTIONS.md` vs runtime map/filtering (`audioknob_gui/gui/conflicts.py`, `audioknob_gui/gui/table.py`, `audioknob_gui/gui/main_window.py`).
- Info/requirements coherence: knob info formatting and requirement synthesis (`audioknob_gui/gui/main_window.py`, `audioknob_gui/gui/table.py`, `audioknob_gui/gui/knobs/registry.py`).
- Simple-mode queue/lock coherence: queue composition, managed-lock lifecycle, explicit release action (`audioknob_gui/gui/simple_mode.py`, `audioknob_gui/gui/main_window.py`).
- Workflow contract coherence: mode-switch wording in `PLAN.md` and `PROJECT_STATE.md`.

### Commands/evidence collection
1. `python3 - <<'PY' ...` (section-map + conflict-map consistency check)
  - Result: `pass`
  - Summary: `SECTION_MAP` headings all present in `docs/KNOB_INTERACTIONS.md`; conflict-map links are symmetric.
2. `python3 - <<'PY' ...` (simple-mode queue composition sanity)
  - Result: `pass`
  - Summary: level composition/ordering matched contract; level `0` composes reset actions for previously managed knobs; tuned backend excludes CPU governor at level `9`.
3. `python3 -m pytest -q tests/test_conflicts.py tests/test_simple_mode.py`
  - Result: `not_run`
  - Summary: `pytest` is not installed in this environment (`No module named pytest`).
4. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
5. `python3 -m compileall -q audioknob_gui`
  - Result: `pass`

### Outputs updated
- `PLAN.md` (mode-switch workflow wording corrected to header `View` button).
- `PROJECT_STATE.md` (UI mode model wording corrected to header `View` button behavior).
- `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md` (added `AK-AUD-003` as resolved coherence fix).

### Finding summary
- New findings added in this phase: `1` (`AK-AUD-003`, resolved in-phase).
- Open carried findings: `AK-AUD-001`, `AK-AUD-002`.

### Phase-4 disposition
- Phase 4 exit criteria: `met`

## 2026-02-12 - Phase 5 remediation batch planning

### Scope checked
- Open findings disposition: `AK-AUD-001`, `AK-AUD-002`.
- Batch contract completion in `docs/internal/audit/2026-02-11/REMEDIATION_BATCHES.md`.

### Commands run
1. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
2. `python3 -m compileall -q audioknob_gui`
  - Result: `pass`

### Outputs updated
- `docs/internal/audit/2026-02-11/REMEDIATION_BATCHES.md` (fully populated with `RB-001`/`RB-002`, ordering, and exit criteria).
- `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md` (finding statuses mapped to planned/deferred/resolved).
- `docs/internal/audit/2026-02-11/KNOB_AUDIT_PLAN.md` (Phase 5 marked complete; resume moved to Phase 6).

### Finding summary
- `AK-AUD-002`: `Planned` in `RB-001`.
- `AK-AUD-001`: `Deferred` in `RB-002` with explicit milestone/rationale.
- `AK-AUD-003`: remains `Resolved`.

### Phase-5 disposition
- Phase 5 exit criteria: `met`

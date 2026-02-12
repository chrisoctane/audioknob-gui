# Verification Report

Note:
- Entries are chronological by execution time and preserve each phase checkpoint state.
- For current disposition, prefer the latest section and `ALIGNMENT_GAP_TRACKER.md` tracker status.

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

## 2026-02-12 - Audit docs consistency sweep

### Scope checked
- `KNOB_WORKSHEET.md` phase-progress header and stale forward-looking note text.
- `KIND_PARITY_MATRIX.md` title labeling consistency.
- Cross-file placeholder scan for audit docs.

### Commands run
1. `rg -n "TODO|TBD|FIXME|in_progress|Current resume point|Phase [0-9]|Slice [A-D]|AK-AUD-" docs/internal/audit/2026-02-11 -g'*.md'`
  - Result: `pass`
  - Summary: no unresolved TODO/TBD/FIXME placeholders; phase markers and findings references present.
2. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
3. `python3 -m compileall -q audioknob_gui`
  - Result: `pass`

### Outputs updated
- `docs/internal/audit/2026-02-11/KNOB_WORKSHEET.md` (removed stale “Phase 4 next/check later” phrasing; aligned with current finding dispositions).
- `docs/internal/audit/2026-02-11/KIND_PARITY_MATRIX.md` (removed stale `(Template)` title label).

### Finding summary
- New findings added: `0`
- Existing finding dispositions unchanged.

## 2026-02-12 - Phase 6 pre-close verification (blocked)

### Scope checked
- Audit-doc drift/error pass across all Phase 0-6 artifacts.
- `RB-001` implementation precondition check for `AK-AUD-002` closure.
- Force-reset parity evidence re-check in worker + GUI support paths.

### Commands run
1. `rg -n "TODO|TBD|FIXME|TEMPLATE|in_progress|\[ \] Phase 6|Current resume point|AK-AUD-|RB-00" docs/internal/audit/2026-02-11 -g'*.md'`
  - Result: `pass`
  - Summary: no unresolved placeholders or stale phase markers; findings/batch references are coherent.
2. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
3. `python3 -m compileall -q audioknob_gui`
  - Result: `pass`
4. `nl -ba audioknob_gui/worker/cli.py | sed -n '3390,3488p'`
  - Result: `pass`
  - Summary: `cmd_force_reset_knob` still lacks explicit branches for `irq_affinity`, `power_profile`, `qjackctl_server_prefix`, `wpctl_profile`.
5. `nl -ba audioknob_gui/gui/main_window.py | sed -n '4068,4098p'`
  - Result: `pass`
  - Summary: `_force_reset_supported` allowlist omits the same four kinds.

### Outputs updated
- `docs/internal/audit/2026-02-11/KNOB_AUDIT_PLAN.md` (Phase 6 status noted as in-progress/blocked on `RB-001`).
- `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md` (`AK-AUD-002` evidence expanded with GUI support-path omission; Phase 6 note added).
- `docs/internal/audit/2026-02-11/REMEDIATION_BATCHES.md` (`RB-001` status clarified as not implemented at pre-close check time).

### Finding summary
- New findings added: `0`
- `AK-AUD-002`: remains `Planned` in `RB-001` (open Medium; closeout blocker by batch policy).
- `AK-AUD-001`: remains `Deferred` in `RB-002` with documented rationale.
- `AK-AUD-003`: remains `Resolved`.

### Phase-6 disposition
- Phase 6 closeout criteria: `not_met`
- Reason: `RB-001` has not been implemented yet, so `AK-AUD-002` cannot be marked resolved.

## 2026-02-12 - Phase 6 final closeout verification

### Scope checked
- `RB-001` implementation evidence in worker + GUI force-reset support paths.
- Audit artifact alignment (`KIND_PARITY_MATRIX.md`, `KNOB_WORKSHEET.md`, `FINDINGS_LEDGER.md`, `REMEDIATION_BATCHES.md`, `KNOB_AUDIT_PLAN.md`).
- Contract alignment in `PLAN.md` and `PROJECT_STATE.md`.

### Commands run
1. `rg -n "_force_reset_irq_affinity|_force_reset_power_profile|_force_reset_qjackctl_server_prefix|_force_reset_wpctl_profile|kind == \"irq_affinity\"|kind == \"power_profile\"|kind == \"qjackctl_server_prefix\"|kind == \"wpctl_profile\"" audioknob_gui/worker/cli.py`
  - Result: `pass`
  - Summary: all four `RB-001` kinds now have explicit force-reset branches.
2. `rg -n "_force_reset_supported|irq_affinity|power_profile|qjackctl_server_prefix|wpctl_profile" audioknob_gui/gui/main_window.py`
  - Result: `pass`
  - Summary: GUI allowlist now includes all `RB-001` kinds.
3. `python3 -m compileall -q audioknob_gui tests`
  - Result: `pass`
4. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
5. `python3 -m pytest -q tests/test_cli_commands.py -k "force_reset or kernel_cmdline_status_param_fallback"`
  - Result: `not_run`
  - Summary: `pytest` is not installed in this environment (`No module named pytest`).

### Outputs updated
- `audioknob_gui/worker/cli.py` (added explicit force-reset handlers for `irq_affinity`, `power_profile`, `qjackctl_server_prefix`, `wpctl_profile`).
- `audioknob_gui/gui/main_window.py` (expanded `_force_reset_supported` allowlist for `RB-001` kinds).
- `tests/test_cli_commands.py` (added force-reset dispatch and `wpctl_profile` safe-decline tests).
- `PLAN.md` and `PROJECT_STATE.md` (force-reset support contract updated).
- `docs/internal/audit/2026-02-11/*` closeout artifacts updated for `RB-001` completion and finding disposition changes.

### Finding summary
- New findings added: `0`
- `AK-AUD-002`: `Resolved` (Phase 6, `RB-001` completed).
- `AK-AUD-001`: `Deferred` (unchanged, `RB-002`).
- `AK-AUD-003`: `Resolved` (unchanged).

### Phase-6 disposition
- Phase 6 closeout criteria: `met`
- Residual risk note: `wpctl_profile` force reset intentionally uses explicit safe-decline for non-deterministic fallback selection; this is documented behavior, not an open parity defect.

## 2026-02-12 - Post-close alignment extraction sweep

### Scope checked
- Fresh code/docs/audit comparison after Phase 6 closeout.
- Force-reset contract parity re-check across worker, GUI allowlist, and docs.
- Outstanding TODO/open-question extraction into a dedicated tracker document.

### Commands run
1. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
2. `python3 -m compileall -q audioknob_gui tests`
  - Result: `pass`
3. `rg -n "TODO|FIXME|TBD|XXX|HACK|BUG" audioknob_gui docs config scripts tests PLAN.md PROJECT_STATE.md -g'*.py' -g'*.md' -g'*.json' --hidden`
  - Result: `pass`
  - Summary: remaining open items were documentation research/backlog items, now centralized in `ALIGNMENT_GAP_TRACKER.md`.

### Outputs updated
- `audioknob_gui/gui/main_window.py` (`wireplumber_conf` added to `_force_reset_supported`).
- `PLAN.md` and `PROJECT_STATE.md` (force-reset list includes `wireplumber_conf`; stale `BUGFEAT.md` reference removed from DoD policy text).
- `docs/knobs.md` (open-question sections now reference centralized tracker IDs).
- `docs/internal/audit/2026-02-11/ALIGNMENT_GAP_TRACKER.md` (new extracted-gap tracker with phased plan).

### Finding summary
- New audit findings added: `0`
- Existing audit disposition unchanged:
  - `AK-AUD-001`: deferred (`RB-002`)
  - `AK-AUD-002`: resolved (`RB-001`)
  - `AK-AUD-003`: resolved

## 2026-02-12 - Phase A contract closure verification

### Scope checked
- Contract hardening for `group_membership` special-case (`RB-002` / `AK-AUD-001`).
- Disposition alignment across `ALIGNMENT_GAP_TRACKER.md`, `REMEDIATION_BATCHES.md`, and `FINDINGS_LEDGER.md`.

### Commands run
1. `rg -n "group_membership|AK-AUD-001|RB-002|AG-001" PLAN.md PROJECT_STATE.md docs/internal/audit/2026-02-11/*.md`
  - Result: `pass`
  - Summary: special-case contract wording and finding/batch dispositions are now aligned.
2. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
3. `python3 -m compileall -q audioknob_gui`
  - Result: `pass`

### Outputs updated
- `PLAN.md` and `PROJECT_STATE.md` (explicit `group_membership` special-case contract wording).
- `docs/internal/audit/2026-02-11/ALIGNMENT_GAP_TRACKER.md` (`AG-001` closed as `RES-003`).
- `docs/internal/audit/2026-02-11/REMEDIATION_BATCHES.md` (`RB-002` completed).
- `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md` (`AK-AUD-001` resolved).

### Finding summary
- New findings added: `0`
- Updated dispositions:
  - `AK-AUD-001`: resolved (`RB-002`)
  - `AK-AUD-002`: resolved (`RB-001`)
  - `AK-AUD-003`: resolved

## 2026-02-12 - Phase B verification completion (`AG-002`)

### Scope checked
- Test execution completeness for the previously open `AG-002` gap.
- Targeted parity tests referenced in prior Phase 6 notes.
- Full test suite execution in the active development environment.

### Commands run
1. `.venv/bin/python -m pytest -q tests/test_cli_commands.py -k "force_reset or kernel_cmdline_status_param_fallback"`
  - Result: `pass`
  - Summary: `6 passed` (targeted parity checks executed).
2. `.venv/bin/python -m pytest -q`
  - Result: `pass`
  - Summary: full suite completed successfully (`83/83` collected tests passed), with one warning:
    - `DeprecationWarning` in `audioknob_gui/gui/status.py:331` (`datetime.utcnow()`).
3. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
4. `python3 -m compileall -q audioknob_gui`
  - Result: `pass`

### Outputs updated
- `docs/internal/audit/2026-02-11/ALIGNMENT_GAP_TRACKER.md` (`AG-002` closed as `RES-004`).
- `docs/internal/audit/2026-02-11/VERIFICATION_REPORT.md` (this section).

### Gap summary
- `AG-002`: resolved (pytest execution completed and recorded).

## 2026-02-12 - Phase C knob research closure (`AG-003` to `AG-006`)

### Scope checked
- Source-backed closure for remaining knob research gaps:
  - `AG-003` PipeWire RT limits value policy
  - `AG-004` WirePlumber ALSA USB config portability
  - `AG-005` Pro Audio profile discovery portability
  - `AG-006` RTKit tuning research gate
- Drift check between `docs/knobs.md`, runtime behavior, and extracted-gap tracker.

### Commands run
1. `rg -n "AG-003|AG-004|AG-005|AG-006|open questions|WirePlumber|Pro Audio|RTKit" docs/knobs.md`
  - Result: `pass`
  - Summary: identified all research-open sections for closure and wording updates.
2. `.venv/bin/python -m pytest -q tests/test_wpctl_profile_status.py tests/test_cli_commands.py -k "wpctl_profile_status or force_reset"`
  - Result: `pass`
  - Summary: targeted behavior tests passed (`9 passed`) including Pro Audio status fallback/name handling.
3. `python3 scripts/check_repo_consistency.py`
  - Result: `pass`
4. `python3 -m compileall -q audioknob_gui tests`
  - Result: `pass`

### Outputs updated
- `docs/knobs.md`
  - closed `AG-003..AG-006` with explicit decision blocks,
  - corrected WirePlumber status wording to match current file-based status behavior,
  - cleaned malformed legacy RTKit note text.
- `docs/internal/audit/2026-02-11/ALIGNMENT_GAP_TRACKER.md`
  - added `RES-005`..`RES-008`,
  - marked `AG-003..AG-006` resolved (`AG-006` resolved by explicit de-scope).

### Gap summary
- `AG-003`: resolved (default/override RT-limits policy documented).
- `AG-004`: resolved (WirePlumber layout/scope contract documented and drift corrected).
- `AG-005`: resolved (deterministic status/fallback contract documented and tested).
- `AG-006`: resolved (apply/reset formally de-scoped with source-backed rationale).

## 2026-02-12 - Current audit snapshot

### Final status
- Audit findings:
  - `AK-AUD-001`: resolved (`RB-002`)
  - `AK-AUD-002`: resolved (`RB-001`)
  - `AK-AUD-003`: resolved
- Alignment gaps:
  - `AG-001`..`AG-006`: resolved (`AG-006` resolved by explicit de-scope)
- Tracker:
  - `docs/internal/audit/2026-02-11/ALIGNMENT_GAP_TRACKER.md` is closed.

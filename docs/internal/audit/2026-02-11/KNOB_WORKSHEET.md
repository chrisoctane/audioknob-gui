# Knob Worksheet

Complete one section per knob. Use severity labels: Blocker/Critical/High/Medium/Low.

## Phase 3 Progress

- Status: `complete`
- Active slice: `closed (Phase 3 complete; see KNOB_AUDIT_PLAN.md for current phase)`
- Started: `2026-02-12`
- Notes: Slices A-D fully populated on 2026-02-12 (`permissions`, `vm`, `cpu`, `power`, `stack`, `services`, `irq`, `kernel`, `testing`); `AK-AUD-001` and `AK-AUD-002` are resolved via `RB-002` and `RB-001`.

## `cpu_dma_latency_udev` - DMA Latency

- Category: `cpu`
- Kind: `udev_rule`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: `audio`, `realtime`
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (kind-level behavior)
- Config surface parity: Pass (no additional config required)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (no active conflict-map entries)
- Transaction/preset parity: Pass
- Test/docs parity: Partial (kind-level coverage; no dedicated knob test)

Findings
- Severity: None
- Confidence: High
- Evidence: `udev_rule` kind has preview/apply/status/restore/force-reset coverage and this knob uses that path directly.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Reviewed in Phase 4 coherence pass; no additional doc/tooltip drift noted.

## `cpu_governor_performance_persistent` - CPU Performance (persistent)

- Category: `cpu`
- Kind: `sysfs_glob_kv`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (no extra UI config required)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (mapped conflict with power profile)
- Transaction/preset parity: Pass
- Test/docs parity: Partial (baseline/conflict coverage, limited knob-specific tests)

Findings
- Severity: None
- Confidence: High
- Evidence: `sysfs_glob_kv` preview/apply/status/restore and force-reset paths are implemented, including persistence checks for this knob.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/conflicts.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Cross-kind force-reset finding does not affect this knob (`sysfs_glob_kv` force-reset is present).

## `wireplumber_alsa_usb_tuning` - WP USB ALSA

- Category: `device`
- Kind: `wireplumber_conf`
- Risk level: `medium`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: `wpctl`

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (state override/config dialog path)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `wireplumber_conf` has preview/apply/status/restore/force-reset coverage and this knob uses that path directly.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/knobs/registry.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: None.

## `irq_pinning` - IRQ Pinning

- Category: `irq`
- Kind: `irq_affinity`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: `irqbalance_disable`
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (device/core/housekeeping state overrides handled)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (`irqbalance_disable` interaction and isolation-map coverage)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `irq_affinity` now has an explicit force-reset branch (`_force_reset_irq_affinity`) that resets writable IRQ masks to the kernel default and removes audioknob IRQ persistence artifacts.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/conflicts.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: No remaining parity gap for force-reset coverage in this kind.
- Proposed fix class: none
- Notes: `AK-AUD-002` resolved in Phase 6 (`RB-001`).

## `irqbalance_disable` - IRQ Balance

- Category: `irq`
- Kind: `systemd_unit_toggle`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (kind-level behavior)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (paired conflict-map entry with `irq_pinning`)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `systemd_unit_toggle` path has preview/apply/status/restore and force-reset coverage; this knob is a direct instance.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/conflicts.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `rtirq_enable` - RT IRQ

- Category: `irq`
- Kind: `rtirq_config`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: `rtirq`

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (`threadirqs` interaction is documented and warned)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `rtirq_config` has dedicated preview/apply/status logic plus explicit restore and force-reset handlers.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_audit_off` - Kernel Audit

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` preview/apply/status/restore/force-reset pipeline without knob-specific branch drift.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_clocksource_tsc` - Kernel Clocksource (TSC)

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (kind-level behavior)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (TSC safety interactions are documented)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` path with TSC-specific warning behavior documented in interactions.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: Phase 4 coherence pass found no additional warning-copy drift.

## `kernel_cstate_limit` - CPU C-States

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (power-profile interaction mapped)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` path and mapped conflict behavior with `power_profile_performance`.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_intel_idle_cstate_limit` - Intel C-States

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (power-profile interaction mapped)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` path and mapped conflict behavior with `power_profile_performance`.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_irqaffinity` - IRQ Housekeeping

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot + core-mismatch model)
- Config surface parity: Pass (auto/manual housekeeping core overrides)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (isolation-set + data-loop interaction mapped)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses `kernel_cmdline` pipeline with dedicated state overrides for IRQ housekeeping core selection.
- File references: `config/registry.json`, `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/conflicts.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: Phase 4 coherence pass found no additional auto-housekeeping copy drift.

## `kernel_isolcpus` - CPU Isolation

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass (core-list state override)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (isolation-set mismatch checks)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses `kernel_cmdline` pipeline with explicit state override support for core-set parameterization.
- File references: `config/registry.json`, `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/conflicts.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: Phase 4 coherence pass found no additional reboot-state contract drift.

## `kernel_mitigations_off` - CPU Mitigations

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` path with documented security/performance tradeoff interactions.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_nmi_watchdog_off` - NMI Watchdog

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` path; interaction coverage is documented in KNOB_INTERACTIONS.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_nohz_full` - Full Tickless

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot + core-mismatch model)
- Config surface parity: Pass (core-list state override)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (isolation-set mismatch checks)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses `kernel_cmdline` pipeline with explicit state override support for core-set parameterization.
- File references: `config/registry.json`, `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/conflicts.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: Phase 4 coherence pass found no additional reboot-state contract drift.

## `kernel_nosmt` - Disable SMT (nosmt)

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` preview/apply/status/restore/force-reset pipeline.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_nosoftlockup` - Soft Lockup Detector

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` preview/apply/status/restore/force-reset pipeline.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_preempt_full` - Kernel Preemption (full)

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` preview/apply/status/restore/force-reset pipeline.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_rcu_nocbs` - RCU Offload

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot + core-mismatch model)
- Config surface parity: Pass (core-list state override)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (isolation-set mismatch checks)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses `kernel_cmdline` pipeline with explicit state override support for core-set parameterization.
- File references: `config/registry.json`, `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/conflicts.py`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: Phase 4 coherence pass found no additional reboot-state contract drift.

## `kernel_rt_throttling_off` - RT Throttling

- Category: `kernel`
- Kind: `sysctl_conf`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `sysctl_conf` path has preview/apply/status/restore and force-reset support; this knob is a direct instance.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_threadirqs` - Threaded IRQs

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (`rtirq_enable` interaction is documented and warned)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` path with documented threadirqs/RTIRQ interaction behavior.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: None.

## `kernel_tsc_reliable` - TSC Reliable

- Category: `kernel`
- Kind: `kernel_cmdline`
- Risk level: `high`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (TSC safety interactions are documented)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `kernel_cmdline` path with TSC-specific warning behavior documented in interactions.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice C scope.
- Proposed fix class: none
- Notes: Phase 4 coherence pass found no additional warning-copy drift.

## `audio_group_membership` - Audio Groups

- Category: `permissions`
- Kind: `group_membership`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Special-case (intentional)
- Apply/reset parity: Special-case (requirement workflow)
- Status parity: Pass
- Partial-reason parity: Limited
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (dependency source for RT limits)
- Transaction/preset parity: Special-case (not a standard transaction knob)
- Test/docs parity: Partial

Findings
- Severity: Low
- Confidence: High
- Evidence: Worker parity model treats `group_membership` as status-only kind while apply/reset flows are handled via requirements workflow.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/requirements.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: Contract clarity issue was closed by explicit special-case documentation in `PLAN.md` and `PROJECT_STATE.md`.
- Proposed fix class: contract/docs only
- Notes: Linked finding `AK-AUD-001`.

## `pipewire_rt_limits_group` - PipeWire RT Limits

- Category: `permissions`
- Kind: `pam_limits_audio_group`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: `audio_group_membership`
- Requires groups: `audio`, `realtime`, `pipewire`
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (state overrides for group/limits bundle)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (depends on `audio_group_membership`)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `pam_limits_audio_group` has full preview/apply/status/restore/force-reset parity and this knob follows that path with dependency wiring.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/requirements.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: None.

## `realtime_clock_access` - Realtime Clock Access

- Category: `permissions`
- Kind: `udev_rule`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (kind-level behavior)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (no direct conflict-map entries)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Implemented via common `udev_rule` path with matching interaction documentation for RTC/HPET access behavior.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: None.

## `rt_limits_audio_group` - RT Limits

- Category: `permissions`
- Kind: `pam_limits_audio_group`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: `audio_group_membership`
- Requires groups: `audio`, `realtime`
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (depends on `audio_group_membership`)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `pam_limits_audio_group` path provides full parity including force-reset line removal and dependency handling.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/requirements.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: None.

## `power_profile_performance` - Power Profile

- Category: `power`
- Kind: `power_profile`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: `powerprofilesctl`, `tuned-adm`

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (backend/state-dependent)
- Config surface parity: Pass (backend override via state/UI)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (mapped against governor and C-state limiters)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `power_profile` now has an explicit force-reset branch (`_force_reset_power_profile`) with backend-aware conservative reset to `balanced` and post-write verification.
- File references: `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/conflicts.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: No remaining parity gap for force-reset coverage in this kind.
- Proposed fix class: none
- Notes: `AK-AUD-002` resolved in Phase 6 (`RB-001`).

## `usb_autosuspend_disable` - USB Power

- Category: `power`
- Kind: `udev_rule`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (kind-level behavior)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (no direct conflict-map entries)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `udev_rule` preview/apply/status/restore/force-reset pipeline.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: None.

## `disable_baloo` - KDE Indexer

- Category: `services`
- Kind: `baloo_disable`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: `balooctl`

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (command-output heuristic)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `baloo_disable` has preview/apply/status/restore and force-reset coverage with explicit user-scope command handling.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: Retained as a runtime-variant watch item; no contract drift found in Phase 4.

## `disable_tracker` - GNOME Indexer

- Category: `services`
- Kind: `user_service_mask`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `user_service_mask` includes preview/apply/status, transaction restore, and force-reset unmask path.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: None.

## `rtkit_daemon_tuning` - RTKit Tuning

- Category: `services`
- Kind: `read_only`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Special-case (read-only by design)
- Status parity: Pass
- Partial-reason parity: N/A
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Special-case (no transaction expected)
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `read_only` kind intentionally routes through preview/status only with no apply/reset mutation path.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/knobs/registry.py`
- Impact: No parity defect; behavior matches “on hold” contract.
- Proposed fix class: none
- Notes: Wording remained coherent in Phase 4 contract checks.

## `pipewire_clock_constraints` - PipeWire Clock Constraints

- Category: `stack`
- Kind: `pipewire_conf`
- Risk level: `medium`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (state override/config dialog path)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (mapped against quantum/sample-rate)
- Transaction/preset parity: Pass
- Test/docs parity: Partial (conflict tests present; limited knob-specific worker tests)

Findings
- Severity: None
- Confidence: High
- Evidence: `pipewire_conf` parity path is complete and conflict wiring for this knob is present in the GUI map/tests.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/conflicts.py`, `tests/test_conflicts.py`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: Conflict-doc wording remained coherent in Phase 4 checks.

## `pipewire_data_loop_affinity` - PipeWire Data Loops

- Category: `stack`
- Kind: `pipewire_conf`
- Risk level: `medium`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (state override/config dialog path)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (mapped against isolation/IRQ knobs)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Implemented through `pipewire_conf` path with explicit conflict-map entries for isolation/IRQ interaction.
- File references: `config/registry.json`, `audioknob_gui/gui/conflicts.py`, `audioknob_gui/worker/ops.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: Phase 4 coherence pass verified warning-copy alignment against conflict docs.

## `pipewire_mlock_policy` - PipeWire Memory Lock

- Category: `stack`
- Kind: `pipewire_conf`
- Risk level: `medium`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: `pipewire_rt_limits_group`
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (dependency on `pipewire_rt_limits_group`)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `pipewire_conf` full parity plus explicit dependency metadata for RT limits.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/requirements.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: Dependency-lock behavior remained aligned in Phase 4 UX coherence checks.

## `pipewire_pro_audio_profile` - PipeWire Pro Audio

- Category: `stack`
- Kind: `wpctl_profile`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: `wpctl`

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (device/runtime-dependent)
- Config surface parity: Pass (selected device state override)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `wpctl_profile` now has an explicit force-reset branch (`_force_reset_wpctl_profile`) that performs deterministic safe-decline when fallback profile inference is unsafe, avoiding blind profile selection.
- File references: `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: No remaining untracked force-reset parity gap; unsupported cases are explicit and conservative.
- Proposed fix class: none
- Notes: `AK-AUD-002` resolved in Phase 6 (`RB-001`).

## `pipewire_quantum` - PipeWire Buffer

- Category: `stack`
- Kind: `pipewire_conf`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (dialog/state override)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (conflicts with clock constraints mapped)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `pipewire_conf` parity path plus conflict mapping with `pipewire_clock_constraints`.
- File references: `config/registry.json`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/conflicts.py`, `tests/test_conflicts.py`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: None.

## `pipewire_rt_module_tuning` - PipeWire RT Module

- Category: `stack`
- Kind: `pipewire_conf`
- Risk level: `medium`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (state override fields)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses `pipewire_conf` parity branch with explicit state override support in CLI composition.
- File references: `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/knobs/registry.py`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: Simple-mode bundle behavior already covered in docs.

## `pipewire_rt_setup` - PipeWire RT Setup

- Category: `stack`
- Kind: `read_only`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: `audio_group_membership`
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Special-case (composed read-only coordinator)
- Status parity: Pass (combined status synthesis)
- Partial-reason parity: Limited
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Special-case
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Marked `read_only`, with explicit combined-status synthesis in CLI from underlying RT-limit/module knobs.
- File references: `config/registry.json`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/knobs/registry.py`, `PLAN.md`
- Impact: No parity defect; behavior is intentionally orchestration-only.
- Proposed fix class: none
- Notes: Special-case remained explicit in Phase 4 coherence pass.

## `pipewire_sample_rate` - PipeWire Sample Rate

- Category: `stack`
- Kind: `pipewire_conf`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (dialog/state override)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (conflicts with clock constraints mapped)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `pipewire_conf` parity path and conflict-map/test coverage align with this knob.
- File references: `config/registry.json`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/conflicts.py`, `tests/test_conflicts.py`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: None.

## `qjackctl_server_prefix_rt` - QjackCtl RT

- Category: `stack`
- Kind: `qjackctl_server_prefix`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: `audio`, `realtime`
- Requires commands: `qjackctl`

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass (CPU core state override)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `qjackctl_server_prefix` now has an explicit force-reset branch (`_force_reset_qjackctl_server_prefix`) that strips RT/taskset settings, clears audioknob post-start hooks, and removes generated post-start scripts when owned.
- File references: `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: No remaining parity gap for force-reset coverage in this kind.
- Proposed fix class: none
- Notes: `AK-AUD-002` resolved in Phase 6 (`RB-001`).

## `blocker_check` - RT Scan

- Category: `testing`
- Kind: `read_only`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Special-case (read-only by design)
- Status parity: Pass
- Partial-reason parity: N/A
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Special-case
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `read_only` kind behavior is intentional (diagnostic path only) and aligns with status/preview contract.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/testing/rtcheck.py`
- Impact: No knob-specific parity gap identified in Slice D scope.
- Proposed fix class: none
- Notes: None.

## `pipewire_xrun_monitor` - PipeWire XRUN Monitor

- Category: `testing`
- Kind: `read_only`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: `pw-top`

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Special-case (read-only by design)
- Status parity: Pass
- Partial-reason parity: N/A
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Special-case
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `read_only` diagnostic behavior with explicit command requirements (`pw-top`) remains consistent with requirements gating.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/requirements.py`
- Impact: No knob-specific parity gap identified in Slice D scope.
- Proposed fix class: none
- Notes: None.

## `scheduler_jitter_test` - Jitter Test

- Category: `testing`
- Kind: `read_only`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: `cyclictest`

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Special-case (read-only by design)
- Status parity: Pass
- Partial-reason parity: N/A
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Special-case
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `read_only` diagnostic behavior is consistent; root/command requirements are declarative and enforced by requirement gates.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/requirements.py`
- Impact: No knob-specific parity gap identified in Slice D scope.
- Proposed fix class: none
- Notes: None.

## `stack_detect` - Audio Stack

- Category: `testing`
- Kind: `read_only`
- Risk level: `low`
- Requires root: `false`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Special-case (read-only by design)
- Status parity: Pass
- Partial-reason parity: N/A
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Special-case
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `read_only` diagnostic behavior is consistent with non-mutating stack detection intent.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/testing/rtcheck.py`
- Impact: No knob-specific parity gap identified in Slice D scope.
- Proposed fix class: none
- Notes: None.

## `dirty_bytes` - Dirty Bytes

- Category: `vm`
- Kind: `sysctl_conf`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (no direct conflict-map entries)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `sysctl_conf` path has preview/apply/status/restore/force-reset support; status details include file content, live sysctl reads, and explicit missing-line partial reasons.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/status.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Uses dedicated sysctl drop-in path for surgical reset behavior.

## `inotify_max_watches` - Inotify Watches

- Category: `vm`
- Kind: `sysctl_conf`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (no direct conflict-map entries)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Implements standard `sysctl_conf` workflow with deterministic line-based status checks and explicit force-reset line removal.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/status.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Dedicated drop-in path avoids cross-knob reset interference.

## `swappiness` - Swappiness

- Category: `vm`
- Kind: `sysctl_conf`
- Risk level: `low`
- Requires root: `true`
- Requires reboot: `false`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (no direct conflict-map entries)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses shared `sysctl_conf` parity path with matching preview/apply/status coverage and status detail exposing expected/current sysctl values.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/status.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Baseline/factory preset hint tests include this knob path.

## `thp_mode_madvise` - Huge Pages

- Category: `vm`
- Kind: `kernel_cmdline`
- Risk level: `medium`
- Requires root: `true`
- Requires reboot: `true`
- Depends on: none
- Requires groups: none
- Requires commands: none

Checks
- Registry/schema parity: Pass
- Preview parity: Pass
- Apply/reset parity: Pass
- Status parity: Pass
- Partial-reason parity: Limited (pending-reboot vs active-state model)
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (no direct conflict-map entries)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `kernel_cmdline` flow provides preview/apply/status/restore and force-reset support; status compares running cmdline and boot config with reboot-aware outcomes.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/status.py`, `tests/test_kernel_cmdline.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Phase 4 coherence pass verified bootloader warning/follow-up contract text.

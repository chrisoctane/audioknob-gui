# Knob Worksheet (Template)

Complete one section per knob. Use severity labels: Blocker/Critical/High/Medium/Low.

## Phase 3 Progress

- Status: `in_progress`
- Active slice: `Slice C (irq, kernel)` next
- Started: `2026-02-12`
- Notes: Slice A (`permissions`, `vm`, `cpu`, `power`) and Slice B (`stack`, `services`) populated on 2026-02-12; findings linked to `AK-AUD-001` and `AK-AUD-002`.

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
- Notes: Re-check in Phase 4 for doc/tooltip wording drift.

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
- Preview parity: Special-case (intentional)
- Apply/reset parity: Special-case (requirement workflow)
- Status parity: Pass
- Partial-reason parity: Limited
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (acts as dependency source)
- Transaction/preset parity: Special-case (not standard knob transaction pipeline)
- Test/docs parity: Partial

Findings
- Severity: Low
- Confidence: High
- Evidence: Worker parity uses status path only for `group_membership`; preview/apply/reset are requirement workflow special-cases.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/requirements.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: Documentation clarity issue only; no immediate functional break.
- Proposed fix class: contract/docs only
- Notes: Linked finding `AK-AUD-001`.

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
- Config surface parity: Pass (state overrides handled)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (depends on `audio_group_membership`)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `pam_limits_audio_group` has full preview/apply/status/restore/force-reset parity and this knob includes dependency + state override handling.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/knobs/registry.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Hidden/internal bundle behavior documented in `PROJECT_STATE.md`.

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
- Conflict/dependency parity: Pass (no direct conflicts documented)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Implemented on the common `udev_rule` path with matching interaction docs for RTC/HPET behavior.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Included in simple-mode design and scanner guidance docs.

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
- Conflict/dependency parity: Pass (dependency gate on `audio_group_membership`)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `pam_limits_audio_group` path provides full parity including force-reset line removal and dependency handling.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `audioknob_gui/gui/requirements.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Safety-latch usage in simple mode remains documented and aligned.

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
- Partial-reason parity: Limited (backend/state-specific)
- Config surface parity: Pass (backend override via state/UI)
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass (conflicts with governor/C-states are mapped)
- Transaction/preset parity: Pass (transaction effects restore path)
- Test/docs parity: Partial (conflict coverage present; limited knob-specific worker tests)

Findings
- Severity: Medium
- Confidence: High
- Evidence: `power_profile` kind is full parity for preview/apply/status/transaction restore, but explicit force-reset branch is absent.
- File references: `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `audioknob_gui/gui/conflicts.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: Recovery consistency is weaker when transaction data is unavailable.
- Proposed fix class: cross-system parity batch
- Notes: Linked finding `AK-AUD-002`.

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
- Conflict/dependency parity: Pass (no active conflict-map entries)
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses common `udev_rule` parity path with preview/apply/status/restore and force-reset support.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`, `docs/KNOB_INTERACTIONS.md`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Keep monitoring for distro-specific udev reload differences in Phase 4.

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
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
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
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Same `sysctl_conf` parity pipeline as other VM knobs; no knob-specific divergence found.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
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
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `sysctl_conf` kind-level parity behavior applies directly with no custom branch divergence.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: None.

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
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: Uses full `kernel_cmdline` preview/apply/status/restore/force-reset pipeline; no knob-specific divergence detected.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice A scope.
- Proposed fix class: none
- Notes: Revisit with cross-system reboot-state checks in Phase 4.

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
- Partial-reason parity: Limited (status text from command output heuristics)
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
- Notes: Keep monitoring distro command variants (`balooctl`/`balooctl6`) during Phase 4 coherence pass.

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
- Partial-reason parity: Pass
- Config surface parity: Pass
- Tooltip/info/requirements parity: Pass
- Conflict/dependency parity: Pass
- Transaction/preset parity: Pass
- Test/docs parity: Partial

Findings
- Severity: None
- Confidence: High
- Evidence: `user_service_mask` kind includes preview/apply/status, transaction restore, and force-reset unmask path.
- File references: `config/registry.json`, `audioknob_gui/worker/ops.py`, `audioknob_gui/worker/cli.py`
- Impact: No knob-specific parity gap identified in Slice B scope.
- Proposed fix class: none
- Notes: Service applicability is correctly reported as `not_applicable` when units are absent.

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
- Impact: No parity defect; behavior matches contract for on-hold RTKit tuning.
- Proposed fix class: none
- Notes: Coherence check in Phase 4 should confirm “on hold” wording remains aligned in docs/UI.

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Notes: Re-check conflict-doc wording coherence in Phase 4.

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
- Notes: Cross-system coherence should verify warning copy against conflict docs.

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
- Notes: Dependency lock behavior should be re-checked in Phase 4 UX coherence.

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
- Severity: Medium
- Confidence: High
- Evidence: `wpctl_profile` has full preview/apply/status/transaction restore, but no explicit force-reset branch.
- File references: `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: Recovery parity depends on transaction availability.
- Proposed fix class: cross-system parity batch
- Notes: Linked finding `AK-AUD-002`.

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
- Notes: Keep this special-case explicit in Phase 4 coherence pass.

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
- Severity: Medium
- Confidence: High
- Evidence: `qjackctl_server_prefix` has preview/apply/status/transaction restore, but no explicit force-reset branch.
- File references: `audioknob_gui/worker/cli.py`, `audioknob_gui/worker/ops.py`, `docs/internal/audit/2026-02-11/FINDINGS_LEDGER.md`
- Impact: Recovery parity depends on transaction availability.
- Proposed fix class: cross-system parity batch
- Notes: Linked finding `AK-AUD-002`.

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

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
- Registry/schema parity: TODO
- Preview parity: TODO
- Apply/reset parity: TODO
- Status parity: TODO
- Partial-reason parity: TODO
- Config surface parity: TODO
- Tooltip/info/requirements parity: TODO
- Conflict/dependency parity: TODO
- Transaction/preset parity: TODO
- Test/docs parity: TODO

Findings
- Severity: TODO
- Confidence: TODO
- Evidence: TODO
- File references: TODO
- Impact: TODO
- Proposed fix class: TODO
- Notes: TODO

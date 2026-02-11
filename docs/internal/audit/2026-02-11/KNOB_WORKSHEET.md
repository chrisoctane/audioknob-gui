# Knob Worksheet (Template)

Complete one section per knob. Use severity labels: Blocker/Critical/High/Medium/Low.

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


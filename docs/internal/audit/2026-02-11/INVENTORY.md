# Inventory Snapshot (2026-02-11)

## Phase 1 Baseline Lock (2026-02-12)

- Locked at UTC: `2026-02-12T17:12:41Z`
- Branch: `master`
- Commit (full): `4384eae387dce2a0715dbf7828deb03908a09d13`
- Commit (short): `4384eae`
- Pre-existing repo drift at lock time: `none` (clean worktree)

This baseline remains authoritative for the current audit cycle unless a new lock point is explicitly recorded.

- Total knobs: `48`
- Total categories: `10`
- Total implementation kinds: `17`

## Categories

| Category | Count |
|---|---:|
| `cpu` | 2 |
| `device` | 1 |
| `irq` | 3 |
| `kernel` | 16 |
| `permissions` | 4 |
| `power` | 2 |
| `services` | 3 |
| `stack` | 9 |
| `testing` | 4 |
| `vm` | 4 |

## Implementation kinds

| Kind | Count |
|---|---:|
| `baloo_disable` | 1 |
| `group_membership` | 1 |
| `irq_affinity` | 1 |
| `kernel_cmdline` | 16 |
| `pam_limits_audio_group` | 2 |
| `pipewire_conf` | 6 |
| `power_profile` | 1 |
| `qjackctl_server_prefix` | 1 |
| `read_only` | 6 |
| `rtirq_config` | 1 |
| `sysctl_conf` | 4 |
| `sysfs_glob_kv` | 1 |
| `systemd_unit_toggle` | 1 |
| `udev_rule` | 3 |
| `user_service_mask` | 1 |
| `wireplumber_conf` | 1 |
| `wpctl_profile` | 1 |

## Knobs by category

### `cpu`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `cpu_dma_latency_udev` | DMA Latency | `udev_rule` | `low` | true | false |
| `cpu_governor_performance_persistent` | CPU Performance (persistent) | `sysfs_glob_kv` | `medium` | true | false |

### `device`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `wireplumber_alsa_usb_tuning` | WP USB ALSA | `wireplumber_conf` | `medium` | false | false |

### `irq`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `irq_pinning` | IRQ Pinning | `irq_affinity` | `medium` | true | false |
| `irqbalance_disable` | IRQ Balance | `systemd_unit_toggle` | `medium` | true | false |
| `rtirq_enable` | RT IRQ | `rtirq_config` | `medium` | true | false |

### `kernel`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `kernel_audit_off` | Kernel Audit | `kernel_cmdline` | `medium` | true | true |
| `kernel_clocksource_tsc` | Kernel Clocksource (TSC) | `kernel_cmdline` | `high` | true | true |
| `kernel_cstate_limit` | CPU C-States | `kernel_cmdline` | `medium` | true | true |
| `kernel_intel_idle_cstate_limit` | Intel C-States | `kernel_cmdline` | `medium` | true | true |
| `kernel_irqaffinity` | IRQ Housekeeping | `kernel_cmdline` | `high` | true | true |
| `kernel_isolcpus` | CPU Isolation | `kernel_cmdline` | `high` | true | true |
| `kernel_mitigations_off` | CPU Mitigations | `kernel_cmdline` | `high` | true | true |
| `kernel_nmi_watchdog_off` | NMI Watchdog | `kernel_cmdline` | `high` | true | true |
| `kernel_nohz_full` | Full Tickless | `kernel_cmdline` | `high` | true | true |
| `kernel_nosmt` | Disable SMT (nosmt) | `kernel_cmdline` | `high` | true | true |
| `kernel_nosoftlockup` | Soft Lockup Detector | `kernel_cmdline` | `high` | true | true |
| `kernel_preempt_full` | Kernel Preemption (full) | `kernel_cmdline` | `high` | true | true |
| `kernel_rcu_nocbs` | RCU Offload | `kernel_cmdline` | `high` | true | true |
| `kernel_rt_throttling_off` | RT Throttling | `sysctl_conf` | `high` | true | false |
| `kernel_threadirqs` | Threaded IRQs | `kernel_cmdline` | `medium` | true | true |
| `kernel_tsc_reliable` | TSC Reliable | `kernel_cmdline` | `high` | true | true |

### `permissions`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `audio_group_membership` | Audio Groups | `group_membership` | `low` | true | true |
| `pipewire_rt_limits_group` | PipeWire RT Limits | `pam_limits_audio_group` | `medium` | true | true |
| `realtime_clock_access` | Realtime Clock Access | `udev_rule` | `low` | true | false |
| `rt_limits_audio_group` | RT Limits | `pam_limits_audio_group` | `low` | true | true |

### `power`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `power_profile_performance` | Power Profile | `power_profile` | `medium` | true | false |
| `usb_autosuspend_disable` | USB Power | `udev_rule` | `low` | true | false |

### `services`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `disable_baloo` | KDE Indexer | `baloo_disable` | `low` | false | false |
| `disable_tracker` | GNOME Indexer | `user_service_mask` | `low` | false | false |
| `rtkit_daemon_tuning` | RTKit Tuning | `read_only` | `low` | false | false |

### `stack`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `pipewire_clock_constraints` | PipeWire Clock Constraints | `pipewire_conf` | `medium` | false | false |
| `pipewire_data_loop_affinity` | PipeWire Data Loops | `pipewire_conf` | `medium` | false | false |
| `pipewire_mlock_policy` | PipeWire Memory Lock | `pipewire_conf` | `medium` | false | false |
| `pipewire_pro_audio_profile` | PipeWire Pro Audio | `wpctl_profile` | `low` | false | false |
| `pipewire_quantum` | PipeWire Buffer | `pipewire_conf` | `low` | false | false |
| `pipewire_rt_module_tuning` | PipeWire RT Module | `pipewire_conf` | `medium` | false | false |
| `pipewire_rt_setup` | PipeWire RT Setup | `read_only` | `medium` | true | false |
| `pipewire_sample_rate` | PipeWire Sample Rate | `pipewire_conf` | `low` | false | false |
| `qjackctl_server_prefix_rt` | QjackCtl RT | `qjackctl_server_prefix` | `low` | false | false |

### `testing`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `blocker_check` | RT Scan | `read_only` | `low` | false | false |
| `pipewire_xrun_monitor` | PipeWire XRUN Monitor | `read_only` | `low` | false | false |
| `scheduler_jitter_test` | Jitter Test | `read_only` | `low` | true | false |
| `stack_detect` | Audio Stack | `read_only` | `low` | false | false |

### `vm`

| Knob ID | Title | Kind | Risk | Root | Reboot |
|---|---|---|---|---:|---:|
| `dirty_bytes` | Dirty Bytes | `sysctl_conf` | `low` | true | false |
| `inotify_max_watches` | Inotify Watches | `sysctl_conf` | `low` | true | false |
| `swappiness` | Swappiness | `sysctl_conf` | `low` | true | false |
| `thp_mode_madvise` | Huge Pages | `kernel_cmdline` | `medium` | true | true |

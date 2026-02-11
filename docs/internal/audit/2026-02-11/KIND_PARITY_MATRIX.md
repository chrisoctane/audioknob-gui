# Kind Parity Matrix (Template)

Use this file to track parity status by implementation kind before knob-by-knob review.

| Kind | Knob count | Sample knobs | Parity class | Preview | Apply | Reset | Status | Partial reason | Force reset | Notes |
|---|---:|---|---|---|---|---|---|---|---|---|
| `baloo_disable` | 1 | `disable_baloo` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `group_membership` | 1 | `audio_group_membership` | Special-case | TODO | TODO | TODO | TODO | TODO | TODO | |
| `irq_affinity` | 1 | `irq_pinning` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `kernel_cmdline` | 16 | `kernel_audit_off`, `kernel_clocksource_tsc`, `kernel_cstate_limit` (+13) | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `pam_limits_audio_group` | 2 | `pipewire_rt_limits_group`, `rt_limits_audio_group` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `pipewire_conf` | 6 | `pipewire_clock_constraints`, `pipewire_data_loop_affinity`, `pipewire_mlock_policy` (+3) | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `power_profile` | 1 | `power_profile_performance` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `qjackctl_server_prefix` | 1 | `qjackctl_server_prefix_rt` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `read_only` | 6 | `blocker_check`, `pipewire_rt_setup`, `pipewire_xrun_monitor` (+3) | Special-case | TODO | TODO | TODO | TODO | TODO | TODO | |
| `rtirq_config` | 1 | `rtirq_enable` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `sysctl_conf` | 4 | `dirty_bytes`, `inotify_max_watches`, `kernel_rt_throttling_off` (+1) | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `sysfs_glob_kv` | 1 | `cpu_governor_performance_persistent` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `systemd_unit_toggle` | 1 | `irqbalance_disable` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `udev_rule` | 3 | `cpu_dma_latency_udev`, `realtime_clock_access`, `usb_autosuspend_disable` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `user_service_mask` | 1 | `disable_tracker` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `wireplumber_conf` | 1 | `wireplumber_alsa_usb_tuning` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |
| `wpctl_profile` | 1 | `pipewire_pro_audio_profile` | Full | TODO | TODO | TODO | TODO | TODO | TODO | |


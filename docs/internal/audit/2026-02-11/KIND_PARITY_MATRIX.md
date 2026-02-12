# Kind Parity Matrix

Use this file to track parity status by implementation kind before knob-by-knob review.

| Kind | Knob count | Sample knobs | Parity class | Preview | Apply | Reset | Status | Partial reason | Force reset | Notes |
|---|---:|---|---|---|---|---|---|---|---|---|
| `baloo_disable` | 1 | `disable_baloo` | Full | Pass | Pass | Pass | Pass | Limited | Pass | `ops.preview` + `cmd_apply_user` + `check_knob_status`; force reset in `cmd_force_reset_knob`. |
| `group_membership` | 1 | `audio_group_membership` | Special-case | Special | Special | Special | Pass | Limited | No | No queue/apply pipeline branch; status exists in `check_knob_status` (`group_membership`). |
| `irq_affinity` | 1 | `irq_pinning` | Full | Pass | Pass | Pass | Pass | Pass | No | Preview/apply/status present; reset via transaction effects (`restore_irq_affinity`) and backup restore path. |
| `kernel_cmdline` | 16 | `kernel_audit_off`, `kernel_clocksource_tsc`, `kernel_cstate_limit` (+13) | Full | Pass | Pass | Pass | Pass | Limited | Pass | Full preview/apply/status; reset has dedicated restore logic and force-reset support. |
| `pam_limits_audio_group` | 2 | `pipewire_rt_limits_group`, `rt_limits_audio_group` | Full | Pass | Pass | Pass | Pass | Pass | Pass | Preview/apply/status covered; force-reset line removal implemented. |
| `pipewire_conf` | 6 | `pipewire_clock_constraints`, `pipewire_data_loop_affinity`, `pipewire_mlock_policy` (+3) | Full | Pass | Pass | Pass | Pass | Pass | Pass | Config-aware preview/apply/status and force-reset file removal path. |
| `power_profile` | 1 | `power_profile_performance` | Full | Pass | Pass | Pass | Pass | Limited | No | Backend-aware preview/apply/status; reset via transaction effects (`restore_power_profile`). |
| `qjackctl_server_prefix` | 1 | `qjackctl_server_prefix_rt` | Full | Pass | Pass | Pass | Pass | Pass | No | User-scope preview/apply/status and transaction restore path. |
| `read_only` | 6 | `blocker_check`, `pipewire_rt_setup`, `pipewire_xrun_monitor` (+3) | Special-case | Pass | Special | Special | Pass | N/A | N/A | Preview/status only by design; apply in root path is explicit no-op. |
| `rtirq_config` | 1 | `rtirq_enable` | Full | Pass | Pass | Pass | Pass | Pass | Pass | Preview/apply/status present; dedicated restore + force-reset handlers implemented. |
| `sysctl_conf` | 4 | `dirty_bytes`, `inotify_max_watches`, `kernel_rt_throttling_off` (+1) | Full | Pass | Pass | Pass | Pass | Pass | Pass | Full preview/apply/status with transaction restore and force-reset line removal. |
| `sysfs_glob_kv` | 1 | `cpu_governor_performance_persistent` | Full | Pass | Pass | Pass | Pass | Pass | Pass | Preview/apply/status present, including persistence checks; restore + force-reset supported. |
| `systemd_unit_toggle` | 1 | `irqbalance_disable` | Full | Pass | Pass | Pass | Pass | Limited | Pass | Preview/apply/status present; reset via systemd effect restore and force-reset. |
| `udev_rule` | 3 | `cpu_dma_latency_udev`, `realtime_clock_access`, `usb_autosuspend_disable` | Full | Pass | Pass | Pass | Pass | Limited | Pass | Preview/apply/status present; transaction restore and force-reset rule removal implemented. |
| `user_service_mask` | 1 | `disable_tracker` | Full | Pass | Pass | Pass | Pass | Pass | Pass | User-scope preview/apply/status with transaction restore and force-reset unmask. |
| `wireplumber_conf` | 1 | `wireplumber_alsa_usb_tuning` | Full | Pass | Pass | Pass | Pass | Pass | Pass | Config-aware preview/apply/status and force-reset file removal path. |
| `wpctl_profile` | 1 | `pipewire_pro_audio_profile` | Full | Pass | Pass | Pass | Pass | Limited | No | Preview/apply/status present; reset handled by transaction effect restore (no force-reset branch). |

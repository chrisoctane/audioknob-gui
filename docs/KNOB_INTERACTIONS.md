# Knob Interactions and Conflict Map

## Purpose
This document is the source of truth for knob interactions, conflicts, and
common blockers. It is used by agents, maintainers, and the GUI warning logic.

## Conflict policy (user-facing)
- Warn by default, never auto-disable without explicit confirmation.
- When a conflict is detected, offer an optional "Queue resets" action.
- Conflicts are informational unless they are known to override or undo settings.
- If a knob requires another (dependency), surface a clear requirement note.

## Interaction map

### Power Profile (powerprofilesctl / tuned)
- tuned (latency-performance) can override or duplicate:
  - CPU Performance (persistent governor)
  - CPU C-States / Intel C-States limiters
- powerprofilesctl can be changed by desktop UI (KDE taskbar / GNOME power).
- If tuned is active, it should be treated as the authoritative power manager.
- In Simple AudioKnob mode, queue composition skips CPU Performance when backend resolution is tuned.

### CPU Performance (persistent governor)
- Conflicts with tuned profiles that manage CPU governor.
- Persistence depends on cpupower/cpufrequtils service presence.
- If tuned is active, the runtime governor may already be `performance` even when
  cpupower persistence is not configured; the app treats that case as not applied
  (to avoid false partial/conflict state after a reset).

### CPU C-States / Intel C-States limiters
- Conflicts with tuned profiles that manage C-states or power policy.
- Can affect suspend and increase heat/fan activity.

### RT Throttling (sched_rt_runtime_us = -1)
- Can reduce xruns, but a runaway RT thread can starve the system.
- May block suspend; users should reset before sleep if needed.

### Threaded IRQs + RTIRQ
- RTIRQ only helps when IRQs are threaded:
  - RT kernel, or kernel cmdline "threadirqs".
- Without threaded IRQs, RTIRQ will not take effect (partial).
- The app warns when RTIRQ is enabled without Threaded IRQs.
- RTIRQ requires the `rtirq` package (including `rtirq.service`). If the unit is
  missing, the knob cannot apply until RTIRQ is installed.

### IRQ Pinning + IRQ Balance
- irqbalance can override IRQ pinning and undo affinity changes.
- The `irqbalance_disable` knob is a prerequisite for `irq_pinning` and is not
  treated as a conflict with it.
- `irqbalance_banned_cpulist` is a policy knob for irqbalance itself; it is
  complementary to `irq_pinning` but less strict (irqbalance still manages IRQs
  on non-banned CPUs).
- IRQ pinning moves audio device IRQs to audio cores and sweeps other IRQs off.
- Some IRQs are kernel-managed (read-only) and cannot be moved.
- Clearing IRQ/core selections and applying now runs reset behavior: empty
  IRQ pinning cores reset affinities back to kernel default masks; empty
  `irqbalance_banned_cpulist` removes the banned CPU policy line.

### IRQ Housekeeping + kernel irqaffinity
- Housekeeping cores define where non-audio IRQs are pushed.
- Auto housekeeping is the inverse of audio cores unless manually set.
- `kernel_irqaffinity` is treated as a housekeeping-role knob; in linked mode
  it is expected to differ from audio isolation core lists by inversion.

### Workqueue cpumask + user.slice AllowedCPUs
- `kernel_workqueue_cpumask` and `cgroup_user_slice_allowed_cpus` should align
  with the same housekeeping/audio-core strategy used by IRQ pinning/isolation.
- In Full mode, these partition-policy knobs and `irqbalance_banned_cpulist`
  are surfaced in the **Cores & IRQ** tab for shared core-plan workflow.
- `kernel_workqueue_cpumask` is runtime sysfs state and may be reset by reboot
  or distro policies.
- Some kernels expose `/sys/devices/virtual/workqueue/cpumask` in hex mask
  syntax; the app normalizes configured CPU-list selections to that mask format
  during apply and accepts either list or mask representation during status.
- `cgroup_user_slice_allowed_cpus` constrains user-session workloads via
  systemd/cgroup v2 and can reduce desktop contention on selected audio cores.
- Clearing core selections and applying is treated as an explicit reset path for
  these knobs (`kernel_workqueue_cpumask` resets to all present CPUs, and
  `cgroup_user_slice_allowed_cpus` removes the drop-in file).
- Mismatched cpuset selections across these knobs can produce partial isolation
  and unpredictable scheduling pressure.
- The GUI now defaults to a linked core-plan mode so audio-role knobs and
  housekeeping-role knobs stay synchronized by inversion unless expert override
  mode is enabled.

### CPU isolation set (isolcpus / nohz_full / rcu_nocbs)
- These audio-role isolation knobs should use a consistent audio core set.
- Mismatched core sets cause partial status and weaker isolation.
- The app warns when these audio isolation knobs use mismatched core sets.
- `kernel_irqaffinity` is evaluated separately as housekeeping policy (see
  IRQ Housekeeping section above).

### Kernel RT extras (clocksource=tsc / tsc=reliable / nmi_watchdog=0 / nosoftlockup / preempt=full)
- In Full mode, TSC timing knobs (`kernel_clocksource_tsc`, `kernel_tsc_reliable`)
  are surfaced in the **Main** tab (advanced-gated); other RT extras remain in **Dev**.
- Disables watchdog diagnostics (NMI/soft lockup); reduces visibility into hangs.
- clocksource/tsc options are hardware-specific and can be unstable on some systems.
- The app warns before applying TSC-related knobs if pre-flight checks look unsafe.
- Requires reboot; should remain dev-only until validated on target hardware.

### Disable SMT (nosmt)
- Disables SMT/Hyper-Threading and reduces logical core count.
- Can invalidate audio core plans, IRQ pinning selections, and isolation core sets.
- Re-run core selection and IRQ pinning after changes.

### QjackCtl RT
- Must quit QjackCtl before applying (QjackCtl rewrites its config on exit).
- Uses a post-start script to pin JACK; JACK must be restarted to take effect.

### PipeWire Quantum / Sample Rate
- These only affect PipeWire sessions; apps can still request overrides.
- In JACK-only setups, these may not be relevant.

### PipeWire Clock Constraints / Mlock / RT Module / Pulse / Data Loops / systemd RT
- Clock constraints and quantum/rate knobs can conflict if ranges disallow the chosen quantum/rate.
- PW Memory Lock depends on PW RT Limits; low memlock limits can cause failures.
- RT module tuning depends on RT limits and/or RTKit/portal behavior.
- PW RT Setup combines RT limits + RT module tuning; if module fields are left blank, only limits are applied.
- `pipewire_pulse_latency` sets global `pulse.properties` defaults; per-app
  `pipewire_pulse_app_rules` can intentionally override those defaults.
- `pipewire_profiler_enable` is complementary to diagnostics (`pw-top`) but can
  add minor runtime overhead.
- `systemd_pipewire_service_rt` / `systemd_wireplumber_service_rt` can overlap
  with module-rt policy; keep scheduling priorities consistent to avoid
  contradictory policy layers.
- Data loop affinity should align with CPU isolation/pinning choices to avoid jitter.
- Simple AudioKnob uses a fixed Safe RT preset bundle (group `audio`, conservative RT-module fields, fixed mlock policy).

### Realtime clock device access
- `realtime_clock_access` installs a udev rule to expose read access for `/dev/rtc*` and `/dev/hpet`.
- This is intended to satisfy scanner-level clock access checks with low operational risk.
- No known direct conflicts with other knobs; reset removes only the dedicated rule file.

### Simple AudioKnob mode
- Dial movement composes queue entries only; it never auto-applies.
- Dial up composes apply actions, and dial down composes resets for knobs managed by AudioKnob.
- Simple apply normalizes queue payloads before worker execution:
  - `group_membership`/`read_only` kinds are excluded from worker apply/reset payloads.
  - already-active knobs are skipped to avoid duplicate apply attempts.
- Level `0` reset preview stays intent-complete: all simple knobs are listed, and non-queued reset rows are annotated (`manual action`, `set outside AudioKnob`, `already off`).
- If queued knobs require audio groups and groups are missing, simple apply routes through the same Join Audio Groups prerequisite workflow as Full mode.
- Top safety latch tiers are:
  - level 10: Safe RT stack (RT limits + fixed Safe PipeWire RT bundle)
  - level 11: Safe IRQ stack (threadirqs + irqbalance disable + rtirq)
- Knobs applied from simple mode are treated as managed in Full mode to avoid mixed-workflow edits.
- Full-mode managed locks are released only by explicit user action (Tools -> Locks -> Release AudioKnob Locks).

### WirePlumber ALSA USB Tuning
- Manual ALSA period settings can fight PipeWire's auto-tuning (0.3.43+).
- Disabling batch mode can increase CPU usage; test with XRUN monitor.

### Pro Audio Profile (wpctl)
- Switching device profiles can change node topology and channel layouts.
- May conflict with JACK/ALSA apps expecting a different profile.

### XRUN Monitor (pw-top)
- Requires pw-top and profiler data; missing modules show unknown output.

### RTKit Daemon Tuning (On hold)
- Distro-specific; blocked until verified against official docs.

### Desktop indexers (Tracker / Baloo)
- GNOME vs KDE only; not applicable outside their desktop environment.

## Blockers and silent failure sources
- Missing commands or packages (e.g., tuned-adm, powerprofilesctl).
- Missing WirePlumber/wpctl or pw-top for PipeWire dev tools.
- Services not present or masked (rtirq, irqbalance, cpupower).
- systemd daemon-reload/service restart not performed after user-unit drop-in edits.
- Malformed PipeWire pulse rules (ignored by parser, resulting in partial/not_applied status).
- Kernel cmdline updates not written to bootloader (changes do not take effect).
- Read-only IRQs (kernel-managed) cannot be reaffined.
- Missing sysfs entries (feature not present on kernel/hardware).
- Group membership changes not active until logout/reboot.
- QjackCtl running when applying QjackCtl RT (config overwritten on exit).
- Power profile not supported (powerprofilesctl lacks "performance" profile).

## Research references
- LinuxAudio.org: system configuration and RT recommendations.
- LinuxMusicians.net threads (see docs/research for captured PDFs).
- Distro docs for power management:
  - power-profiles-daemon, tuned, cpupower/cpufrequtils.
- systemd execution/resource controls:
  - https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
  - https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html
- PipeWire pulse config and rules:
  - https://docs.pipewire.org/page_man_pipewire-pulse_conf_5.html
- Kernel parameter reference:
  - https://www.kernel.org/doc/html/latest/admin-guide/kernel-parameters.html
- Linux workqueue internals and affinity behavior:
  - https://docs.kernel.org/core-api/workqueue.html
- irqbalance policy options:
  - https://manpages.ubuntu.com/manpages/noble/man1/irqbalance.1.html
- Ubuntu RT kernel tuning parameters:
  - https://documentation.ubuntu.com/real-time/en/latest/tutorial/intel-tcc/kernel-parameters/

## Maintenance rules
- Update this file when adding a new knob, changing behavior, or discovering
  new conflicts/blockers.
- Repository consistency gate enforces updates here when conflict/knob behavior
  paths change (registry behavior metadata, worker behavior paths, and
  conflict/simple queue behavior modules), unless explicitly waived with
  `docs-not-needed:` for pure refactors.
- Keep warnings in the UI aligned with this map.

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

### CPU Performance (persistent governor)
- Conflicts with tuned profiles that manage CPU governor.
- Persistence depends on cpupower/cpufrequtils service presence.

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

### IRQ Pinning + IRQ Balance
- irqbalance can override IRQ pinning and undo affinity changes.
- IRQ pinning moves audio device IRQs to audio cores and sweeps other IRQs off.
- Some IRQs are kernel-managed (read-only) and cannot be moved.

### IRQ Housekeeping + kernel irqaffinity
- Housekeeping cores define where non-audio IRQs are pushed.
- Auto housekeeping is the inverse of audio cores unless manually set.

### CPU isolation set (isolcpus / nohz_full / rcu_nocbs / irqaffinity)
- These knobs should use a consistent audio core set.
- Mismatched core sets cause partial status and weaker isolation.

### Kernel RT extras (clocksource=tsc / tsc=reliable / nmi_watchdog=0 / nosoftlockup / preempt=full)
- Disables watchdog diagnostics (NMI/soft lockup); reduces visibility into hangs.
- clocksource/tsc options are hardware-specific and can be unstable on some systems.
- The app warns before applying TSC-related knobs if pre-flight checks look unsafe.
- Requires reboot; should remain dev-only until validated on target hardware.

### QjackCtl RT
- Must quit QjackCtl before applying (QjackCtl rewrites its config on exit).
- Uses a post-start script to pin JACK; JACK must be restarted to take effect.

### PipeWire Quantum / Sample Rate
- These only affect PipeWire sessions; apps can still request overrides.
- In JACK-only setups, these may not be relevant.

### PipeWire Clock Constraints / Mlock / RT Module / Data Loops
- Clock constraints and quantum/rate knobs can conflict if ranges disallow the chosen quantum/rate.
- PW Memory Lock depends on PW RT Limits; low memlock limits can cause failures.
- RT module tuning depends on RT limits and/or RTKit/portal behavior.
- PW RT Setup combines RT limits + RT module tuning; if module fields are left blank, only limits are applied.
- Data loop affinity should align with CPU isolation/pinning choices to avoid jitter.

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
- Kernel parameter reference:
  - https://www.kernel.org/doc/html/latest/admin-guide/kernel-parameters.html
- Ubuntu RT kernel tuning parameters:
  - https://documentation.ubuntu.com/real-time/en/latest/tutorial/intel-tcc/kernel-parameters/

## Maintenance rules
- Update this file when adding a new knob, changing behavior, or discovering
  new conflicts/blockers.
- Keep warnings in the UI aligned with this map.

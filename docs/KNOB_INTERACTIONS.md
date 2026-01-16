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

### QjackCtl RT
- Must quit QjackCtl before applying (QjackCtl rewrites its config on exit).
- Uses a post-start script to pin JACK; JACK must be restarted to take effect.

### PipeWire Quantum / Sample Rate
- These only affect PipeWire sessions; apps can still request overrides.
- In JACK-only setups, these may not be relevant.

### Desktop indexers (Tracker / Baloo)
- GNOME vs KDE only; not applicable outside their desktop environment.

## Blockers and silent failure sources
- Missing commands or packages (e.g., tuned-adm, powerprofilesctl).
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

## Maintenance rules
- Update this file when adding a new knob, changing behavior, or discovering
  new conflicts/blockers.
- Keep warnings in the UI aligned with this map.

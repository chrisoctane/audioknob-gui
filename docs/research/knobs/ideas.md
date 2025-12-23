# Knob Ideas

This list focuses on new knobs or meaningful improvements backed by the sources in
`docs/research/knobs/sources.md`.

## Near-term candidates

- PipeWire RT limits group (`pipewire_limits_group`)
  - What: create `/etc/security/limits.d/95-pipewire.conf` with:
    - `@pipewire - rtprio 95`
    - `@pipewire - nice -19`
    - `@pipewire - memlock 4194304`
    - then ensure user is in `pipewire` group.
  - Why: PipeWire wiki recommends dedicated limits for PipeWire users.
  - Risk: higher RT priorities can starve other workloads.
  - Source: https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

- RTKit daemon tuning (`rtkit_daemon_tune`)
  - What: systemd override to pass `RTKIT_ARGS` (priority limits, rttime, thread
    caps) to `rtkit-daemon` via `/etc/sysconfig/rtkit` or `/etc/dbus-1/system.d/rtkit`.
  - Why: PipeWire recommends tuning RTKit to ensure stable RT priority handling.
  - Risk: distro-specific paths; misconfiguration can break RTKit service.
  - Source: https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

- PipeWire ALSA USB period size (`pipewire_alsa_period_size`)
  - What: set `api.alsa.period-size` for USB devices (via PipeWire config) to
    tune latency; align with graph quantum.
  - Why: PipeWire notes period-size tuning for USB devices.
  - Risk: wrong values can cause xruns or device instability.
  - Source: https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

- PipeWire clock constraints (`pipewire_clock_limits`)
  - What: add `default.clock.min-quantum`, `default.clock.max-quantum`,
    `default.clock.quantum-limit`, `default.clock.quantum-floor`, and
    `default.clock.allowed-rates` in a drop-in `pipewire.conf.d` file.
  - Why: PipeWire config docs describe explicit min/max and allowed rates to
    stabilize graph settings across device changes.
  - Risk: overly tight limits can block device activation or cause xruns.
  - Source: https://pipewire.pages.freedesktop.org/pipewire/page_man_pipewire_conf_5.html

- PipeWire data loop tuning (`pipewire_data_loop_affinity`)
  - What: configure `context.num-data-loops` and `context.data-loops` with
    `loop.rt-prio` and `thread.affinity` to pin the RT data loop to chosen cores.
  - Why: PipeWire supports RT data loop priority and CPU affinity for scheduling.
  - Risk: mis-pinning can starve other workloads or reduce overall throughput.
  - Source: https://pipewire.pages.freedesktop.org/pipewire/page_man_pipewire_conf_5.html

- PipeWire mlock policy (`pipewire_mlock_all`)
  - What: set `mem.allow-mlock` and optionally `mem.mlock-all` to keep PipeWire
    memory resident.
  - Why: PipeWire supports mlock to avoid swap-induced hiccups.
  - Risk: increased locked memory usage; may fail on low memlock limits.
  - Source: https://pipewire.pages.freedesktop.org/pipewire/page_man_pipewire_conf_5.html

- Kernel preempt mode (`kernel_preempt_full`)
  - What: add `preempt=full` to kernel cmdline on PREEMPT_DYNAMIC kernels.
  - Why: PipeWire wiki notes this can reduce latency on supported kernels.
  - Risk: higher scheduling overhead; may affect throughput.
  - Source:
    - https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning
    - https://linuxmusicians.com/viewtopic.php?t=26784 (notes PREEMPT_DYNAMIC requirement)

- SMT disable (`smt_disable`)
  - What: write `off` to `/sys/devices/system/cpu/smt/control` (revert with `on`).
  - Why: Linux Audio wiki notes SMT can cause DSP spikes at higher loads.
  - Risk: reduces multi-thread throughput; some workloads slow down.
  - Source: https://wiki.linuxaudio.org/wiki/system_configuration

- RTC/HPET max user frequency (`rtc_hpet_max_user_freq`)
  - What: set `/sys/class/rtc/rtc0/max_user_freq` and `/proc/sys/dev/hpet/max-user-freq`
    to 2048 (Arch guidance), with a persistent systemd unit.
  - Why: ArchWiki suggests increasing max_user_freq for improved timing.
  - Risk: higher timer interrupt rate; extra CPU wakeups/power use.
  - Source: https://wiki.archlinux.org/title/Professional_audio

- CPU idle-state limit (`cpu_idle_state_limit`)
  - What: use `cpupower idle-set` to disable deepest C-states for lower wake
    latency (optionally per-CPU).
  - Why: openSUSE tuning guide notes deep C-states increase wake latency.
  - Risk: higher power usage and thermals.
  - Source: https://doc.opensuse.org/documentation/leap/tuning/html/book-tuning/cha-tuning-power.html

- I/O scheduler selection (`io_scheduler_device`)
  - What: set per-device I/O scheduler to `mq-deadline`, `bfq`, `kyber`, or `none`
    via `/sys/block/<dev>/queue/scheduler`, with optional udev persistence.
  - Why: openSUSE tuning guide documents per-device scheduler tuning.
  - Risk: wrong scheduler can hurt throughput or latency for that device.
  - Source: https://doc.opensuse.org/documentation/leap/tuning/html/book-tuning/cha-tuning-io.html

- TuneD profile selection (`tuned_profile`)
  - What: use `tuned-adm profile latency-performance` or `realtime`, with
    revert/verify via `tuned-adm`.
  - Why: TuneD provides prebuilt low-latency profiles with rollback support.
  - Risk: profile effects are broad; requires tuned on the target distro.
  - Sources:
    - https://tuned-project.org/
    - https://manpages.opensuse.org/Tumbleweed/tuned/tuned-adm.8.en.html

- Noatime for audio filesystems (`fstab_noatime`)
  - What: add `noatime` to selected mounts in `/etc/fstab` (root or audio disks).
  - Why: multiple sources note reduced metadata writes and small perf gains.
  - Risk: breaks apps relying on atime; should be optional and documented.
  - Sources:
    - https://wiki.linuxaudio.org/wiki/system_configuration
    - https://wiki.archlinux.org/title/fstab
    - https://opensource.com/article/20/6/linux-noatime
    - https://wiki.tnonline.net/w/Btrfs/Mount_Options

- rtirq config helper (`rtirq_config`)
  - What: add an optional config editor for `/etc/sysconfig/rtirq` or
    `/etc/default/rtirq` (e.g., set `RTIRQ_NAME_LIST`, `RTIRQ_HIGH_LIST`).
  - Why: Linux Audio wiki documents how tuning RTIRQ lists improves IRQ priorities.
  - Risk: misconfiguration can destabilize IRQ scheduling.
  - Source: https://wiki.linuxaudio.org/wiki/system_configuration

- rtcirqus integration (`rtcirqus_enable`)
  - What: install/config `rtcirqus` + udev rule to auto-raise IRQ RT priorities for
    audio devices (USB + onboard).
  - Why: rtcirqus automates IRQ priority changes on device plug/unplug.
  - Risk: new dependency stack; distro packaging variability.
  - Source:
    - https://codeberg.org/autostatic/rtcirqus
    - https://linuxmusicians.com/viewtopic.php?t=26784

- rtirq vs rtcirqus guidance (`irq_priority_strategy`)
  - What: surface a short guide that rtcirqus targets audio IRQs via udev (USB
    hotplug), while rtirq is broader but not udev-aware and can only prioritize
    by IRQ class (e.g., xhci_hcd) rather than a single USB interface.
  - Why: forum discussion highlights practical differences and limitations.
  - Risk: informational only, but sets expectations for USB class-compliant devices.
  - Source: https://linuxmusicians.com/viewtopic.php?t=26784

- PCI latency timer tuning (`pci_latency_timer`)
  - What: optional advanced knob using `setpci` to raise PCI latency timers for
    legacy PCI audio devices.
  - Why: Linux Audio wiki and ArchWiki note this can reduce xruns on PCI.
  - Risk: only applies to conventional PCI; can degrade other devices.
  - Sources:
    - https://wiki.linuxaudio.org/wiki/system_configuration
    - https://wiki.archlinux.org/title/Professional_audio

## Improvements to existing knobs

- Firefox speech-dispatcher mitigation (`firefox_speech_dispatcher_disable`)
  - What: toggle `reader.parse-on-load.enabled=false` and
    `media.webspeech.synth.enabled=false` in `about:config`.
  - Why: PipeWire wiki notes speech dispatcher can hog CPU, especially in VMs.
  - Risk: disables read-aloud features.
  - Source: https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

- CPU governor persistent (`cpu_governor_performance_persistent`)
  - Improvement: add a systemd unit or distro-specific control (e.g., mask
    `ondemand.service` on Ubuntu) so the performance governor does not revert.
  - Source: https://wiki.linuxaudio.org/wiki/system_configuration

- CPU DMA latency udev (`cpu_dma_latency_udev`)
  - Improvement: optional helper service that keeps `/dev/cpu_dma_latency` open with
    `0`, instead of only enabling permissions.
  - Source: https://wiki.linuxaudio.org/wiki/system_configuration

- rtirq enable (`rtirq_enable`)
  - Improvement: surface RTIRQ priority lists in the UI (similar to QjackCtl cores).
  - Source: https://wiki.linuxaudio.org/wiki/system_configuration

## Research backlog

- PipeWire performance tuning wiki
  - Blocked by Anubis; revisit with a JS-capable fetcher to confirm recommended
    `pipewire.conf` knobs (quantum limits, allowed rates, RT priorities, etc.).

- power-profiles-daemon docs
  - Blocked by Anubis; revisit to confirm whether disabling or pinning profiles
    is recommended for low-latency audio on recent distros.

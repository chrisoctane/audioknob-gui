# Sources

## Primary sources reviewed

- https://wiki.linuxaudio.org/wiki/system_configuration
  - CPU governor performance, SMT disable, /dev/cpu_dma_latency udev rule, noatime, rtirq config, PCI latency timer.
- https://wiki.archlinux.org/title/Professional_audio
  - Optimization checklist: performance governor, threadirqs, noatime, RTC/HPET max_user_freq, swappiness, inotify watches, PCI latency timer.
- https://wiki.archlinux.org/title/fstab
  - atime/relatime/noatime tradeoffs and app compatibility notes.
- https://opensource.com/article/20/6/linux-noatime
  - Explains atime/relatime defaults and when noatime can still help.
- https://wiki.tnonline.net/w/Btrfs/Mount_Options
  - noatime reduces metadata writes; especially useful with many snapshots.
- https://codeberg.org/autostatic/rtcirqus
  - udev-driven IRQ RT priority for audio devices; config options and install steps.
- https://linuxmusicians.com/viewtopic.php?t=26784
  - Content provided by user paste (thread on rtcirqus vs rtirq).
  - Notes: rtcirqus focuses on audio IRQs (USB + onboard), rtirq is broader but
    not udev-aware; threadirqs + PREEMPT_DYNAMIC + preempt=full interplay.
- https://pipewire.pages.freedesktop.org/pipewire/page_man_pipewire_conf_5.html
  - PipeWire config properties: default clock rates/quantums, allowed rates,
    data loop RT priority and CPU affinity, mlock settings, node/device rules.
- https://doc.opensuse.org/documentation/leap/tuning/html/book-tuning/cha-tuning-io.html
  - openSUSE I/O scheduler selection and tunables (mq-deadline, bfq, kyber, none).
- https://doc.opensuse.org/documentation/leap/tuning/html/book-tuning/cha-tuning-power.html
  - openSUSE power management: C-states/P-states, cpupower idle-set examples.
- https://manpages.opensuse.org/Tumbleweed/cpupower/cpupower.1.en.html
  - cpupower toolset overview and subcommands (idle-set, frequency-set, etc.).
- https://manpages.opensuse.org/Tumbleweed/cpupower/cpupower-idle-set.1.en.html
  - cpupower idle-set options for enabling/disabling CPU C-states by latency.
- https://tuned-project.org/
  - TuneD overview, profiles, and rollback model.
- https://manpages.opensuse.org/Tumbleweed/tuned/tuned-adm.8.en.html
  - tuned-adm profile switching and profile list/recommendations.
- https://docs.kernel.org/admin-guide/kernel-parameters.html
  - Kernel cmdline parameters for preempt mode, nohz_full, rcu_nocbs,
    isolcpus, irqaffinity, idle=, intel_idle.max_cstate, processor.max_cstate.
- https://docs.kernel.org/scheduler/sched-rt-group.html
  - RT throttling controls: sched_rt_runtime_us and sched_rt_period_us behavior.
- https://docs.kernel.org/power/pm_qos_interface.html
  - PM QoS interface; /dev/cpu_dma_latency and cpu_wakeup_latency semantics.
- https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning
  - Content provided by user paste (page blocked by Anubis when fetched).
  - Notes: preempt=full on PREEMPT_DYNAMIC kernels, module-rt/RTKit portal, limits.d
    pipewire group, RTKit daemon args, ALSA period-size property, Firefox speech
    dispatcher mitigation, pw-top/pw-profiler.
- https://help.ubuntu.com/community/UbuntuStudio/UbuntuStudioControls
  - Ubuntu Studio Controls features: CPU governor, audio group membership, JACK controls,
    ALSA MIDI/PulseAudio bridging, USB hotplugging into JACK, multi-device JACK, JACK periods.
- https://help.ubuntu.com/community/UbuntuStudio/RealTimeKernel
  - Explains low-latency kernel benefits and cautions against full RT kernels.

## Blocked or limited sources

- https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning
  - Blocked by Anubis anti-bot protection (requires JS/Pow); content was provided
    by user paste above.
- https://linuxmusicians.com/viewtopic.php?t=26784
  - JS-only loading; text fetch unavailable.
- https://gitlab.freedesktop.org/upower/power-profiles-daemon/-/blob/main/README.md
  - Blocked by Anubis anti-bot protection (requires JS/Pow).
- https://forum.cockos.com/forumdisplay.php?f=52
- https://discourse.ardour.org/
- https://discussion.fedoraproject.org
- https://discourse.ubuntu.com/
  - Landing pages only; no concrete tuning guidance captured.

## Out of scope for knob ideas

- https://lwn.net/Articles/652156/
  - RCU fundamentals; not directly relevant to audio tuning knobs.

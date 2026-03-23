# Info Panel Copy Rewrite Plan

Purpose
- Create one review document for the current info-panel copy before we replace any live text.
- Keep the copy musician-friendly and technically honest.
- Explain what a knob changes, why someone would use it, and what the tradeoffs are, without assuming the reader already knows Linux internals.

Scope
- Covers the human-authored text shown in the info panel today:
  - registry description lines from `config/registry.json`
  - the shared auto-generated requirements sentence pattern from `audioknob_gui/gui/main_window.py`
  - knob-specific helper sections from `audioknob_gui/gui/knobs/*`
- Does not try to capture machine-specific runtime values from Status/Check, implementation tables, or CLI commands.

Review status
- Cross-checked against the current `config/registry.json` knob set on 2026-03-18.
- Covers all 58 current registry knobs plus the shared helper-only `_rt_limits_extra_html` block.
- Headings should stay aligned with live registry IDs and titles so this file can be used as a reliable rewrite checklist later.

Tone rules for the rewrite
- Keep normal audio terms such as sample rate, buffer, JACK, PipeWire, and XRUN.
- Expand lower-level Linux terms when they are the only explanation. Example: say what `irqbalance` or `pw-top` does, not just the command name.
- Prefer "what changes" and "what you gain" before "how it is implemented."
- Keep warnings calm and concrete. Avoid wording that sounds scary unless the risk is genuinely high.
- Do not talk down to the reader.

## Formatting Proposal

Current label style
- `[i]` summary
- `[r]` requirements
- `[+]` benefits
- `[-]` tradeoffs

Problems
- The brackets feel cramped.
- The symbols look like shorthand notes instead of finished product copy.
- The current labels visually blend into the body text.

Proposed label style
- `Info`
- `Requirements`
- `Benefits`
- `Tradeoffs`

Rendering proposal
- Render each label in bold with the app's accent blue, then render the body text in normal panel text color.
- Keep the label as a short inline prefix rather than a large heading, so the panel stays compact.
- Example:
  - Current: `[i] sets PipeWire default sample rate.`
  - Proposed: `Info: Sets PipeWire's default sample rate.`

Implementation note
- The current formatter lives in [audioknob_gui/gui/main_window.py](/home/chris/audioknob-gui/audioknob_gui/gui/main_window.py#L4355).
- The live replacement should use theme-aware styling rather than a hard-coded bright blue.

## Shared Generated Requirements Line

Current generated pattern
- `requires root access; reboot; group membership: ...; commands: ...; depends on: ...; advanced mode`

Problems
- It reads like a debug string.
- Semicolons and machine labels make it feel mechanical.
- It leads with implementation constraints instead of user guidance.

Proposed pattern
- `Requirements: needs root access.`
- `Requirements: takes effect after reboot.`
- `Requirements: your user must be in the audio and realtime groups.`
- `Requirements: depends on Audio Groups.`
- `Requirements: unlock Advanced mode to change this setting.`

Implementation note
- We should convert the current single compressed line into readable phrases, but still keep it auto-generated from metadata.

## Description Review

### Permissions and Baseline Setup

#### Audio Groups (`audio_group_membership`)
- Before: [i] adds the current user to audio-related groups (audio, realtime, pipewire). [+] required for RT limits and low-latency device access. [-] grants extra device permissions and needs a reboot or log out/in.
- After: Info: Adds your user account to the audio-related groups used by low-latency audio features: audio, realtime, and pipewire. Benefits: Needed before RT limits and several device-access knobs can work. Tradeoffs: Gives your account broader access to audio devices. Log out and back in, or reboot, before the new group membership fully takes effect.

#### RT Limits (`rt_limits_audio_group`)
- Before: [i] sets PAM limits for the audio group (rtprio 95, memlock unlimited, nice -10). [+] lets audio apps use realtime priority and lock memory to avoid xruns. [-] requires log out/in or reboot; runaway RT apps can affect system responsiveness.
- After: Info: Sets login-session limits for the audio group so audio apps can use realtime priority, lock memory, and raise scheduling priority. Benefits: Helps DAWs, JACK, and similar audio apps avoid dropouts when they need realtime scheduling. Tradeoffs: Takes effect after log out and back in, or reboot. A misbehaving realtime app can make the desktop less responsive.

#### IRQ Balance (`irqbalance_disable`)
- Before: [i] disables irqbalance. [+] prevents IRQs moving between CPUs, which stabilizes audio latency and pinning. [-] IRQ distribution becomes static and can reduce throughput for some workloads.
- After: Info: Disables the irqbalance service so interrupt handling stays where you place it. Benefits: Makes IRQ pinning and CPU-isolation plans more stable for audio work. Tradeoffs: Interrupt load no longer moves automatically, which can reduce performance for some non-audio workloads.

#### RT IRQ (`rtirq_enable`)
- Before: [i] configures rtirq priorities and enables the rtirq service. [+] with threaded IRQs, higher IRQ thread priority reduces audio interrupt latency. [-] requires threaded IRQs (threadirqs or RT kernel) to have effect and can deprioritize other IRQs.
- After: Info: Configures RTIRQ and enables its service so audio-related IRQ threads run at higher realtime priority. Benefits: Can reduce interrupt-handling latency when threaded IRQs are active. Tradeoffs: Only helps when IRQs are threaded, and it can push other interrupts lower in the queue.

#### IRQ Pinning (`irq_pinning`)
- Before: [i] pins IRQs for selected audio devices to chosen cores and sweeps other IRQs off audio cores. [+] isolates audio interrupts to reduce jitter. [-] USB devices share controller IRQs; requires irqbalance off; poor choices can shift IRQ load.
- After: Info: Pins interrupts for selected audio devices to chosen CPU cores and moves other IRQs away from those audio cores. Benefits: Reduces jitter by keeping audio interrupt work on a predictable set of CPUs. Tradeoffs: USB devices often share controller IRQs, so pinning can affect more than one device. You usually want irqbalance off first, and poor core choices can just move the bottleneck elsewhere.

#### IRQ Balance Policy (`irqbalance_banned_cpulist`)
- Before: [i] sets irqbalance banned CPUs policy (IRQBALANCE_BANNED_CPULIST). [r] configure before apply. [+] keeps irqbalance from moving IRQs onto selected audio CPUs. [-] wrong bans can concentrate IRQ load.
- After: Info: Sets the CPU ban list used by irqbalance so it avoids selected audio CPUs. Requirements: Choose the CPUs to protect before Apply. Benefits: Lets irqbalance stay enabled while still keeping interrupts off your audio cores. Tradeoffs: If you ban the wrong CPUs, interrupt work can pile up on the remaining ones.

#### CPU Performance (persistent) (`cpu_governor_performance_persistent`)
- Before: [i] sets CPU governor to performance now and configures it to persist across reboots. [+] avoids frequency scaling latency spikes under realtime load. [-] higher power use and heat.
- After: Info: Switches the CPU governor to performance now and keeps that setting across reboots. Benefits: Avoids frequency-scaling delays that can show up as audio latency spikes. Tradeoffs: Uses more power and creates more heat.

#### DMA Latency (`cpu_dma_latency_udev`)
- Before: [i] grants the audio group access to /dev/cpu_dma_latency. [+] allows audio apps to request low-latency C-state behavior. [-] apps can keep CPUs in higher power states.
- After: Info: Lets the audio group access `/dev/cpu_dma_latency`, which allows apps to request a lower-latency CPU idle policy. Benefits: Helps audio apps reduce wake-up delays from deep idle states. Tradeoffs: Apps can keep the CPU in higher-power states while they are running.

#### Realtime Clock Access (`realtime_clock_access`)
- Before: [i] grants non-root read access to realtime clock devices (/dev/rtc*, /dev/hpet) via udev. [+] satisfies common low-latency checks that require readable clock devices. [-] requires udev reload or replug/session refresh; broadens read access to timing devices.
- After: Info: Grants non-root read access to realtime clock devices such as `/dev/rtc*` and `/dev/hpet` through a udev rule. Benefits: Satisfies common low-latency checks and tools that expect those timing devices to be readable. Tradeoffs: You may need a device replug, session refresh, or udev reload before it is visible, and it broadens read access to timing hardware.

#### Swappiness (`swappiness`)
- Before: [i] sets vm.swappiness=10. [+] reduces swapping that can cause dropouts under memory pressure. [-] uses more RAM and less swap.
- After: Info: Sets `vm.swappiness` to `10` so the system is less eager to push memory out to swap. Benefits: Reduces swap-driven pauses that can cause audio dropouts under memory pressure. Tradeoffs: Keeps more data in RAM and uses swap less aggressively.

#### Huge Pages (`thp_mode_madvise`)
- Before: [i] sets transparent huge pages to madvise. [+] avoids unexpected THP latency while keeping opt-in behavior. [-] requires reboot; may reduce THP benefits for some workloads.
- After: Info: Sets Transparent Huge Pages to `madvise`, so applications must opt in instead of getting huge pages automatically. Benefits: Avoids surprise latency spikes from automatic THP behavior while still allowing software that wants THP to request it. Tradeoffs: Requires reboot, and some workloads may lose performance benefits from always-on huge pages.

#### Inotify Watches (`inotify_max_watches`)
- Before: [i] sets fs.inotify.max_user_watches=600000. [+] prevents DAWs from hitting file watch limits. [-] uses more kernel memory for watchers.
- After: Info: Raises `fs.inotify.max_user_watches` to `600000`. Benefits: Helps DAWs and sample-heavy tools avoid running out of file-watch entries. Tradeoffs: Uses more kernel memory for those watch slots.

#### Dirty Bytes (`dirty_bytes`)
- Before: [i] lowers vm.dirty_bytes and vm.dirty_background_bytes. [+] reduces long writeback stalls that cause audio glitches. [-] increases writeback frequency.
- After: Info: Lowers the dirty-writeback thresholds so the kernel flushes file changes sooner instead of letting large write bursts build up. Benefits: Reduces long writeback stalls that can cause audible glitches. Tradeoffs: The system writes back data more often.

#### USB Power (`usb_autosuspend_disable`)
- Before: [i] disables USB autosuspend via udev. [+] prevents USB audio device dropouts. [-] higher USB power draw and reduced battery life.
- After: Info: Disables USB autosuspend for matched devices through a udev rule. Benefits: Helps prevent USB audio interfaces from sleeping and dropping out mid-session. Tradeoffs: Uses more USB power and can reduce battery life.

### Power, CPU, and Kernel Scheduling

#### Power Profile (`power_profile_performance`)
- Before: [i] sets the system power profile to performance (powerprofilesctl) or latency-performance (tuned) and restores the previous profile on reset. [+] ensures a known low-latency profile even if desktop UI toggles are unavailable. [-] higher power use/heat; tuned can override CPU governor and C-state knobs.
- After: Info: Switches the system to a high-performance power profile using `powerprofilesctl` or `tuned`, then restores the previous profile on reset. Benefits: Gives you a known low-latency power policy even when the desktop power controls are missing or inconsistent. Tradeoffs: Uses more power and creates more heat. If `tuned` is active, it can also take control of governor, C-state, swappiness, and dirty-byte settings.

#### CPU C-States (`kernel_cstate_limit`)
- Before: [i] adds processor.max_cstate=1 to kernel cmdline. [+] limits deep idle states to reduce latency jitter. [-] higher power/heat, fans, and possible suspend issues.
- After: Info: Adds `processor.max_cstate=1` to the kernel command line to keep the CPU out of deeper idle states. Benefits: Can reduce latency jitter caused by deeper sleep and wake-up behavior. Tradeoffs: Uses more power, can keep fans active, and may affect suspend reliability.

#### Intel C-States (`kernel_intel_idle_cstate_limit`)
- Before: [i] adds intel_idle.max_cstate=1 to kernel cmdline. [+] limits deep idle states on systems using intel_idle for lower jitter. [-] Intel-only, higher power/heat, possible suspend issues.
- After: Info: Adds `intel_idle.max_cstate=1` to the kernel command line on systems that use the Intel idle driver. Benefits: Can reduce latency jitter from deep Intel idle states. Tradeoffs: Intel-only, uses more power, and can affect heat and suspend behavior.

#### Threaded IRQs (`kernel_threadirqs`)
- Before: [i] adds threadirqs to kernel cmdline. [+] makes IRQ handlers schedulable threads so RTIRQ can prioritize them. [-] requires reboot and can add overhead.
- After: Info: Adds `threadirqs` to the kernel command line so interrupt handlers run as schedulable threads where the kernel allows it. Benefits: Lets tools such as RTIRQ raise priority on those IRQ threads. Tradeoffs: Requires reboot and can add some overhead.

#### RT Throttling (`kernel_rt_throttling_off`)
- Before: [i] sets kernel.sched_rt_runtime_us=-1. [+] avoids periodic RT throttling that can cause xruns. [-] runaway RT tasks can starve the system or block suspend.
- After: Info: Disables the kernel's realtime CPU time throttle by setting `kernel.sched_rt_runtime_us=-1`. Benefits: Avoids periodic RT throttling that can show up as XRUNs or dropouts. Tradeoffs: A runaway realtime task can starve the rest of the system and may block suspend.

#### CPU Isolation (`kernel_isolcpus`)
- Before: [i] adds isolcpus=<cores> to kernel cmdline. [+] isolates selected cores for dedicated audio work. [-] reduces CPU capacity for general workloads; requires reboot.
- After: Info: Adds `isolcpus=<cores>` to the kernel command line so the selected CPUs are kept more dedicated to explicit work such as audio threads. Benefits: Helps reserve CPU time for audio workloads. Tradeoffs: Reduces CPU capacity for general desktop work and requires reboot.

#### Full Tickless (`kernel_nohz_full`)
- Before: [i] adds nohz_full=<cores> to kernel cmdline. [+] reduces timer ticks on audio cores for lower jitter. [-] requires reboot and works best with isolcpus/rcu_nocbs.
- After: Info: Adds `nohz_full=<cores>` to the kernel command line so selected CPUs receive fewer scheduler timer ticks. Benefits: Can lower jitter on dedicated audio cores. Tradeoffs: Requires reboot and usually works best as part of a broader isolation plan with `isolcpus` and `rcu_nocbs`.

#### RCU Offload (`kernel_rcu_nocbs`)
- Before: [i] adds rcu_nocbs=<cores> to kernel cmdline. [+] offloads RCU callbacks from audio cores to reduce jitter. [-] requires reboot and shifts work to housekeeping cores.
- After: Info: Adds `rcu_nocbs=<cores>` to the kernel command line so RCU callback work moves off the selected CPUs. Benefits: Reduces background kernel work on audio cores. Tradeoffs: Requires reboot and shifts that work onto housekeeping cores.

#### IRQ Housekeeping (`kernel_irqaffinity`)
- Before: [i] adds irqaffinity=<cores> to kernel cmdline for default IRQ handling. [+] keeps interrupts off audio cores. [-] requires reboot; bad choices can concentrate IRQ load.
- After: Info: Adds `irqaffinity=<cores>` to the kernel command line to set the default CPUs used for interrupt handling. Benefits: Helps keep interrupts off dedicated audio cores. Tradeoffs: Requires reboot, and a bad CPU choice can overload the remaining housekeeping CPUs.

#### Workqueue cpumask (`kernel_workqueue_cpumask`)
- Before: [i] sets /sys/devices/virtual/workqueue/cpumask for global unbound workqueues. [r] configure before apply. [+] keeps kernel workqueue load off selected audio CPUs. [-] runtime only unless persisted by separate policy.
- After: Info: Sets the CPU mask used by global unbound kernel workqueues. Requirements: Choose the target CPUs before Apply. Benefits: Keeps general kernel background work off selected audio CPUs. Tradeoffs: On its own this is only a runtime change unless another policy keeps it in place.

#### Cgroup CPU Partition (`cgroup_user_slice_allowed_cpus`)
- Before: [i] writes a user.slice AllowedCPUs drop-in (cgroup v2 cpuset partitioning). [r] configure before apply. [+] constrains user-session workloads to selected CPUs. [-] requires service/session restart to fully take effect.
- After: Info: Writes a `user.slice` systemd drop-in that limits your user session to selected CPUs. Requirements: Choose the CPUs before Apply. Benefits: Helps keep general desktop workloads away from audio-dedicated CPUs. Tradeoffs: Usually needs a service or session restart before the full effect is visible.

#### PipeWire systemd RT (`systemd_pipewire_service_rt`)
- Before: [i] writes a systemd user drop-in for pipewire.service scheduling/affinity. [r] configure before apply. [+] allows explicit RT policy/priority and CPUAffinity for PipeWire. [-] incorrect values can starve desktop threads.
- After: Info: Writes a systemd user drop-in for `pipewire.service` so you can set scheduling policy, priority, and CPU affinity explicitly. Requirements: Configure the values before Apply. Benefits: Gives you direct control over how PipeWire is scheduled. Tradeoffs: Incorrect settings can make other desktop threads wait too long.

#### WirePlumber systemd RT (`systemd_wireplumber_service_rt`)
- Before: [i] writes a systemd user drop-in for wireplumber.service scheduling/affinity. [r] configure before apply. [+] allows explicit RT policy/priority and CPUAffinity for WirePlumber. [-] incorrect values can starve desktop threads.
- After: Info: Writes a systemd user drop-in for `wireplumber.service` so you can set scheduling policy, priority, and CPU affinity explicitly. Requirements: Configure the values before Apply. Benefits: Gives you direct control over how WirePlumber is scheduled. Tradeoffs: Incorrect settings can make other desktop threads wait too long.

#### Kernel Preemption (full) (`kernel_preempt_full`)
- Before: [i] adds preempt=full to kernel cmdline (PREEMPT_DYNAMIC). [+] increases kernel preemption for lower scheduling latency. [-] higher overhead; may affect stability on some systems; requires reboot.
- After: Info: Adds `preempt=full` to the kernel command line on kernels that support dynamic preemption. Benefits: Can lower scheduling latency by making the kernel more preemptible. Tradeoffs: Adds overhead, may affect stability on some systems, and requires reboot.

#### Kernel Clocksource (TSC) (`kernel_clocksource_tsc`)
- Before: [i] adds clocksource=tsc to kernel cmdline. [+] uses TSC as the kernel clocksource for lower latency. [-] may be unstable on some hardware; requires reboot.
- After: Info: Adds `clocksource=tsc` to the kernel command line so the system prefers TSC as its kernel clock source. Benefits: Can reduce timing overhead on systems where TSC is reliable. Tradeoffs: May be unstable on some hardware and requires reboot.

#### TSC Reliable (`kernel_tsc_reliable`)
- Before: [i] adds tsc=reliable to kernel cmdline. [+] marks TSC as reliable and disables runtime stability checks. [-] may be unsafe on some systems; requires reboot.
- After: Info: Adds `tsc=reliable` to the kernel command line so the kernel trusts TSC without its usual runtime stability checks. Benefits: Can reduce timing-related uncertainty on systems with a truly stable TSC. Tradeoffs: Unsafe on systems where TSC is not actually reliable, and requires reboot.

#### NMI Watchdog (`kernel_nmi_watchdog_off`)
- Before: [i] adds nmi_watchdog=0 to kernel cmdline. [+] disables the NMI watchdog to reduce RT latency. [-] removes a safety diagnostic; requires reboot.
- After: Info: Adds `nmi_watchdog=0` to the kernel command line to disable the NMI watchdog. Benefits: Can shave off a small amount of realtime latency overhead. Tradeoffs: Removes a useful system-hang diagnostic and requires reboot.

#### Soft Lockup Detector (`kernel_nosoftlockup`)
- Before: [i] adds nosoftlockup to kernel cmdline. [+] disables the soft lockup detector to reduce jitter. [-] removes a safety diagnostic; requires reboot.
- After: Info: Adds `nosoftlockup` to the kernel command line to disable the soft lockup detector. Benefits: Can reduce small amounts of scheduler overhead and jitter. Tradeoffs: Removes a useful safety diagnostic and requires reboot.

#### Disable SMT (nosmt) (`kernel_nosmt`)
- Before: [i] adds nosmt to kernel cmdline to disable SMT/Hyper-Threading. [+] can reduce scheduling jitter on some systems. [-] reduces CPU throughput and changes core topology; requires reboot.
- After: Info: Adds `nosmt` to the kernel command line to disable SMT or Hyper-Threading. Benefits: Can reduce scheduling jitter on some systems. Tradeoffs: Lowers total CPU throughput, changes core layout, and requires reboot.

#### sched_ext Scheduler (`scx_scheduler`)
- Before: [i] controls scx.service with a selected sched_ext scheduler. [r] configure before apply. [+] can improve mixed music and gaming responsiveness under CPU contention. [-] experimental whole-system scheduler change; complements rather than replaces PipeWire RT.
- After: Info: Controls `scx.service` using the `sched_ext` scheduler you pick from the available installed `scx_*` binaries. Requirements: Choose a scheduler before Apply. Benefits: Can improve responsiveness when music tools and games compete with background CPU load. Tradeoffs: This is an experimental whole-system scheduler change, and it complements rather than replaces PipeWire's realtime path.

#### Kernel Audit (`kernel_audit_off`)
- Before: [i] adds audit=0 to kernel cmdline. [+] reduces audit overhead on realtime workloads. [-] disables kernel audit logging (security tradeoff).
- After: Info: Adds `audit=0` to the kernel command line to disable kernel audit logging. Benefits: Removes audit overhead from low-latency workloads. Tradeoffs: Gives up kernel audit logs, which is a real security and diagnostics tradeoff.

#### CPU Mitigations (`kernel_mitigations_off`)
- Before: [i] adds mitigations=off to kernel cmdline. [+] reduces CPU mitigation overhead. [-] disables Spectre/Meltdown protections (security risk).
- After: Info: Adds `mitigations=off` to the kernel command line to disable CPU vulnerability mitigations. Benefits: Reduces mitigation overhead on supported systems. Tradeoffs: Disables security protections such as Spectre and Meltdown mitigations.

### JACK, PipeWire, and User-Space Audio Stack

#### QjackCtl RT (`qjackctl_server_prefix_rt`)
- Before: [i] configures QjackCtl realtime/priority and a post-start script to re-pin JACK, updating active presets without removing user presets. [+] keeps JACK RT settings and core pinning consistent across starts. [-] apply while QjackCtl is closed; updates QjackCtl config.
- After: Info: Configures QjackCtl's realtime settings and a post-start hook that re-applies JACK CPU pinning when JACK starts. Benefits: Keeps JACK priority and CPU placement consistent across launches without wiping your existing QjackCtl presets. Tradeoffs: Apply this while QjackCtl is closed, because the knob updates the QjackCtl config file.

#### PipeWire Buffer (`pipewire_quantum`)
- Before: [i] sets PipeWire buffer size (quantum). [+] lower buffers reduce latency for realtime audio. [-] higher CPU usage and xrun risk; PipeWire restarts.
- After: Info: Sets PipeWire's default buffer size (`quantum`). Benefits: Smaller buffers reduce latency. Tradeoffs: Lower values use more CPU and increase XRUN risk, and PipeWire restarts when you apply the change.

#### PipeWire Sample Rate (`pipewire_sample_rate`)
- Before: [i] sets PipeWire default sample rate. [+] matches project/interface rate for consistent audio. [-] higher rates increase CPU use; PipeWire restarts.
- After: Info: Sets PipeWire's default sample rate. Benefits: Helps keep the system sample rate aligned with your project or interface. Tradeoffs: Higher rates use more CPU, and PipeWire restarts when you apply the change.

#### PipeWire Pulse Latency (`pipewire_pulse_latency`)
- Before: [i] sets pipewire-pulse global latency properties. [r] configure before apply. [+] aligns Pulse clients with lower-latency defaults. [-] aggressive values can increase xruns in older clients.
- After: Info: Sets the global latency defaults used by `pipewire-pulse` for PulseAudio-compatible apps. Requirements: Configure the values before Apply. Benefits: Helps older Pulse clients follow lower-latency defaults. Tradeoffs: Aggressive values can increase XRUNs or instability in some clients.

#### PipeWire Pulse App Rules (`pipewire_pulse_app_rules`)
- Before: [i] writes pipewire-pulse per-app latency rules. [r] configure before apply. [+] allows per-application PIPEWIRE_LATENCY-style overrides. [-] malformed rules can be ignored by pipewire-pulse.
- After: Info: Writes per-application latency rules for `pipewire-pulse`. Requirements: Configure the rule list before Apply. Benefits: Lets you tune latency by app instead of using one global default. Tradeoffs: Invalid or mismatched rules may simply be ignored by `pipewire-pulse`.

#### PipeWire Clock Constraints (`pipewire_clock_constraints`)
- Before: [i] constrains PipeWire clock/quantum ranges (advanced). [r] configure before apply; empty fields are ignored. [+] can stabilize buffer ranges and allowed rates. [-] misconfiguration can cause xruns or refused rates.
- After: Info: Sets advanced limits for PipeWire clock and buffer behavior, such as allowed rates and quantum ranges. Requirements: Configure the fields before Apply; blank fields are left untouched. Benefits: Can make buffer ranges and rate switching more predictable. Tradeoffs: Incorrect values can cause XRUNs or make some rates unavailable.

#### PipeWire Memory Lock (`pipewire_mlock_policy`)
- Before: [i] enables PipeWire memory locking (mlock). [+] reduces xruns by keeping audio buffers resident. [-] requires sufficient memlock limits; may fail if limits are low.
- After: Info: Enables PipeWire memory locking so audio buffers can stay resident in RAM. Benefits: Can reduce XRUNs caused by memory pages being moved out at the wrong time. Tradeoffs: Needs enough `memlock` headroom from your realtime limits, and may fail if those limits are too low.

#### PipeWire RT (`pipewire_rt_setup`)
- Before: [i] guided PipeWire RT setup for permissions and fallback behavior. [r] configure before apply; advanced fields are optional. [+] keeps the main PipeWire RT choices in one place. [-] enabling PAM limits still requires log out/in or reboot.
- After: Info: Guides PipeWire realtime setup from one place, including permissions and the `module-rt` fallback path. Requirements: Configure the preset before Apply; advanced fields are optional. Benefits: Keeps the main PipeWire RT decisions in one guided workflow instead of spreading them across multiple hidden sub-knobs. Tradeoffs: If you enable PAM limits, you still need to log out and back in, or reboot, before those limits fully apply.

#### PipeWire RT Limits (`pipewire_rt_limits_group`)
- Before: [i] sets PipeWire realtime limits for the selected group. [+] allows PipeWire to obtain realtime scheduling. [-] requires log out/in or reboot; incorrect limits can affect system responsiveness.
- After: Info: Sets login-session realtime limits for the selected PipeWire group. Benefits: Gives PipeWire permission to request realtime scheduling directly instead of relying only on fallback helpers. Tradeoffs: Takes effect after log out and back in, or reboot, and bad limit values can hurt overall system responsiveness.

#### PipeWire RT Module (`pipewire_rt_module_tuning`)
- Before: [i] tunes PipeWire RT module args (advanced). [r] configure before apply. [+] fine-grained realtime priority and budget tuning. [-] incorrect values can reduce stability.
- After: Info: Tunes advanced `module-rt` settings such as priority, runtime budget, and fallback behavior. Requirements: Configure the fields before Apply. Benefits: Gives fine-grained control over how PipeWire asks for realtime scheduling. Tradeoffs: Incorrect values can make the stack less stable or less responsive.

#### PipeWire Data Loops (`pipewire_data_loop_affinity`)
- Before: [i] pins PipeWire data loops to CPU cores (advanced). [r] configure before apply. [+] can reduce jitter by isolating audio threads. [-] incorrect affinity can degrade performance.
- After: Info: Pins PipeWire data-loop threads to selected CPU cores. Requirements: Configure the target CPUs before Apply. Benefits: Can reduce jitter by keeping audio processing on predictable cores. Tradeoffs: Incorrect CPU affinity can reduce performance instead of improving it.

#### WP USB ALSA (`wireplumber_alsa_usb_tuning`)
- Before: [i] tunes WirePlumber ALSA USB period/buffer settings. [r] configure before apply. [+] can lower USB audio latency. [-] aggressive settings can increase xruns.
- After: Info: Tunes WirePlumber's ALSA USB period and buffer settings for USB audio devices. Requirements: Configure the values before Apply. Benefits: Can lower USB audio latency. Tradeoffs: Aggressive values can increase XRUNs.

#### PipeWire Pro Audio (`pipewire_pro_audio_profile`)
- Before: [i] switches a device to the Pro Audio profile when available. [+] enables pro audio routing without JACK. [-] per-device; profile availability varies.
- After: Info: Switches a selected device to PipeWire's Pro Audio profile when that profile is available. Benefits: Exposes pro-audio routing and channel handling without requiring JACK. Tradeoffs: Works per device, and not every interface exposes a Pro Audio profile.

#### PipeWire Profiler (`pipewire_profiler_enable`)
- Before: [i] enables PipeWire profiler module in a user drop-in. [+] ensures pw-top profiler counters are available. [-] minor runtime overhead while enabled.
- After: Info: Enables the PipeWire profiler module in your user configuration. Benefits: Makes profiler counters available to tools such as `pw-top`. Tradeoffs: Adds a small amount of runtime overhead while enabled.

#### PipeWire XRUN Monitor (`pipewire_xrun_monitor`)
- Before: [i] shows live XRUN/ERR counts via pw-top. [+] helps evaluate tuning changes. [-] read-only; requires pw-top.
- After: Info: Shows live XRUN and error counters by reading `pw-top`. Benefits: Helps you see whether a tuning change actually improves runtime behavior. Tradeoffs: Read-only, and it depends on `pw-top` being installed and available.

#### RTKit Tuning (`rtkit_daemon_tuning`)
- Before: [i] RTKit daemon tuning (on hold; distro-specific). This does not affect PipeWire's use of RTKit. [+] can enable higher RT budgets when supported. [-] blocked until verified; no changes applied.
- After: Info: Reserved for future RTKit daemon tuning. It does not currently change how PipeWire uses RTKit. Benefits: Keeps a place for verified distro-specific RTKit tuning later. Tradeoffs: This knob is informational only for now and applies no system changes.

### Background Services and Diagnostics

#### GNOME Indexer (`disable_tracker`)
- Before: [i] disables GNOME Tracker indexer services. [+] avoids background IO/CPU spikes during audio work. [-] GNOME file indexing/search is reduced.
- After: Info: Disables the GNOME Tracker indexing services. Benefits: Reduces background disk and CPU spikes during audio work. Tradeoffs: GNOME file indexing and search become less complete.

#### KDE Indexer (`disable_baloo`)
- Before: [i] disables KDE Baloo indexer. [+] avoids background IO/CPU spikes during audio work. [-] KDE file indexing/search is reduced.
- After: Info: Disables the KDE Baloo indexer. Benefits: Reduces background disk and CPU spikes during audio work. Tradeoffs: KDE file indexing and search become less complete.

#### Audio Stack (`stack_detect`)
- Before: [i] reports the active audio stack (PipeWire/JACK/ALSA) and lists ALSA devices. [+] quick visibility for troubleshooting. [-] read-only; no changes.
- After: Info: Shows which audio stack is active right now, such as PipeWire, JACK, or plain ALSA, and lists detected ALSA devices. Benefits: Gives quick troubleshooting context without leaving the app. Tradeoffs: Read-only; it does not change anything.

#### Jitter Test (`scheduler_jitter_test`)
- Before: [i] runs cyclictest to measure scheduler latency jitter. [+] quantifies realtime latency before/after tuning. [-] uses CPU while running; requires cyclictest.
- After: Info: Runs `cyclictest` to measure scheduler latency jitter. Benefits: Gives you a before-and-after number for realtime tuning changes instead of relying only on feel. Tradeoffs: Uses CPU while it runs and depends on `cyclictest` being installed.

#### ALSA XRUN Monitor (`alsa_xrun_monitor`)
- Before: [i] monitors ALSA xrun counts per sound card via /proc/asound. [+] tracks xruns at the ALSA driver level, independent of PipeWire. [-] enabling xrun_debug logging requires root (non-persistent, resets on reboot).
- After: Info: Monitors ALSA XRUN counts for each sound card using `/proc/asound`. Benefits: Tracks underruns at the ALSA driver level, even if PipeWire or JACK is not the source of the problem. Tradeoffs: Enabling extra `xrun_debug` logging needs root access and resets on reboot.

#### RT Scan (`blocker_check`)
- Before: [i] runs a realtime readiness scan. [+] highlights missing prerequisites and common blockers. [-] read-only; may need extra packages for some checks.
- After: Info: Runs a realtime-readiness scan across common audio prerequisites and blockers. Benefits: Quickly shows what is missing before you start changing knobs one by one. Tradeoffs: Read-only, and some checks need optional packages to be available.

## Supplemental Helper Text Review

Note
- These are the extra explanatory sections appended by knob-specific helper code.
- Dynamic status values are intentionally summarized here as templates rather than copied with machine-specific content.

### Shared helper copy changes

#### Auto-generated requirements line
- Before: requires root access; reboot; group membership: ...; commands: ...; depends on: ...; advanced mode
- After: Requirements: needs root access. Takes effect after reboot. Requires the listed groups or commands. Depends on the listed knob when shown. Unlock Advanced mode to change this setting.

#### RT Limits helper (`_rt_limits_extra_html`)
- Before: Session limits (ulimit): rtprio ... memlock ... Note: limits apply after log out/in or reboot.
- After: Current session limits: shows the active `rtprio` and `memlock` values for this login session. Note: new limits only take effect after you log out and back in, or reboot.

#### QjackCtl helper
- Before: Quit QjackCtl before applying this knob... Buffer math: total buffer = frames/period × periods/buffer...
- After: Note: Close QjackCtl before applying this knob, because QjackCtl rewrites its config on exit. Buffer guidance: total buffer size is `frames per period × periods per buffer`. Lower values reduce latency but increase XRUN risk.

#### IRQ Pinning helper
- Before: Warning: irqbalance is active and can override IRQ pinning... IRQ lines (from /proc/interrupts)... If a line lists multiple devices...
- After: Warning: `irqbalance` is still active and may undo your IRQ pinning choices. IRQ line summary: shows which interrupt lines are attached to the devices you selected. Shared IRQs mean one line can affect more than one device.

#### CPU layout helper
- Before: CPU core layout: SMT detected... For best isolation, select both siblings...
- After: CPU layout: shows physical-versus-logical core layout and sibling groups. Guidance: if SMT or Hyper-Threading is enabled, isolate both siblings from the same physical core together when possible.

#### Threaded IRQs helper
- Before: threadirqs makes IRQ handlers schedulable threads but does not change CPU topology... Pairing tip: Enable RTIRQ...
- After: How it works: `threadirqs` turns eligible interrupt handlers into schedulable threads. Tip: pair this with RTIRQ if you want those IRQ threads to run at higher priority.

#### RTIRQ helper
- Before: Warning: RTIRQ only affects threaded IRQs...
- After: How it works: RTIRQ only changes priorities for threaded IRQs. If IRQs are not threaded yet, enable Threaded IRQs or use an RT kernel first.

#### RT throttling helper
- Before: Current sched_rt_runtime_us ... Warning: disabling RT throttling can let runaway RT tasks starve the system...
- After: Current kernel setting: shows the live `sched_rt_runtime_us` value. Warning: turning throttling off removes the safety brake for runaway realtime tasks, which can freeze other work and interfere with suspend.

#### C-state helper
- Before: CPU idle driver... Note... Limiting C-states can increase power draw and heat...
- After: Current CPU idle driver: shows whether the system is using `intel_idle` or another driver. Guidance: limiting C-states can reduce wake-up latency, but it also increases power draw, heat, and possible suspend side effects.

#### PipeWire RT helper
- Before: What this does... Guides PipeWire realtime setup from one dialog...
- After: What this changes: guides PipeWire realtime setup from one place and combines permissions plus `module-rt` behavior. Tip: start with Safe RT, then move to Full RT or Custom only if you know you need it.

#### PipeWire mlock helper
- Before: Enables PipeWire memory locking in a user drop-in... Requires RT limits...
- After: How it works: enables PipeWire memory locking in your user config. Reminder: memory locking only succeeds when your realtime limits allow enough `memlock`.

#### PipeWire RT Limits helper
- Before: Sets PAM limits for a selected group... Gives PipeWire permission to request realtime scheduling...
- After: How it works: writes login-session limits for the selected group so PipeWire can request realtime scheduling directly. Reminder: these limits do not fully apply until your next login session.

#### PipeWire RT Module helper
- Before: Sets PipeWire module-rt arguments... Only the fields you set are applied...
- After: How it works: writes the advanced `module-rt` settings you choose and leaves unset fields alone. Use this when Safe RT or Full RT is close, but not quite the behavior you want.

#### Power Profile helper
- Before: Backend preference... Resolved backend... Potential conflicts...
- After: Power profile details: show which backend you prefer, which backend the app will actually use, and which overlapping knobs are managed by that backend. If `tuned` is active, say clearly that it takes ownership of governor, C-states, swappiness, and dirty-byte tuning.

#### Jitter Test helper
- Before: Last jitter test... Tip: use "Show Sample List"...
- After: Last jitter test: show the most recent result in plain language first, then the detailed per-thread table. Tip: the sample list is for deep inspection when you want the raw timing values.

## Implementation Sequence

1. Update the live label renderer so `[i]`, `[r]`, `[+]`, and `[-]` become `Info`, `Requirements`, `Benefits`, and `Tradeoffs` with accent styling.
2. Rewrite registry descriptions in small batches, starting with the most visible baseline knobs.
3. Rewrite supplemental helper blocks so they match the new tone and label style.
4. Review the generated requirements sentence separately and make it read like guidance instead of metadata.
5. After copy approval, replace the live text in code and registry files.

## Review Notes

- This document is intentionally more explicit than the current panel copy.
- We should keep the final live text slightly shorter than this review draft once the wording is approved.
- Where a command or subsystem name must remain visible, it should appear after the explanation, not instead of it.
- Registry and helper coverage is complete as of the review-status check above; future knob additions should extend this file before live copy is rewritten.

# Knob Implementation Plans

This doc captures implementation outlines for upcoming knobs. Each outline is
written to be distro- and device-agnostic where possible, with discovery rules
and conservative fallbacks. Use official sources first; if a setting is not
clearly documented, mark it as blocked until verified.

Common rules
- Prefer drop-in configs over editing main config files.
- If a config path can be discovered from the system, use that path and record
  it in the system profile.
- If discovery fails, use conservative fallbacks and report status as unknown
  until confirmed.
- Reset must be surgical: delete only our drop-in file or remove only our block.
- PipeWire supports drop-in config directories and env overrides for config
  lookup; align with PipeWire's lookup rules when possible.

Common sources
- PipeWire config lookup + drop-in behavior
  - https://docs.pipewire.org/page_man_pipewire_conf_5.html
- PipeWire properties & profiles (ALSA/ACP/UCM, Pro Audio profile note)
  - https://docs.pipewire.org/page_man_pipewire-props_7.html
- WirePlumber control CLI (profile switching)
  - https://manpages.ubuntu.com/manpages/resolute/man1/wpctl.1.html
- PipeWire Performance Tuning (user-provided excerpt, Wim Taymans, 20 Apr 2023)

-------------------------------------------------------------------------------
## Kernel RT Extras (Dev)

Goal
- Provide optional kernel boot parameters that can improve RT latency on some
  systems, while keeping them gated as dev-only until validated on user rigs.

Knobs (kernel cmdline)
- clocksource=tsc
- tsc=reliable
- nmi_watchdog=0
- nosoftlockup
- preempt=full
- nosmt

UI
- Dev tab only. High-risk warnings in Info.
- Requires reboot toggle and Advanced knobs toggle (consistent with other kernel
  cmdline knobs).

Apply/Reset
- Use existing kernel cmdline editing; apply appends the parameter.
- Reset removes only the knob’s parameter (surgical).

Status
- Applied when the parameter is present in the configured boot cmdline file.
- Reboot required warning until the system has rebooted into the new cmdline.

Risks/notes
- Disabling watchdogs removes diagnostics that can catch hangs.
- clocksource/tsc options can be unstable on some hardware.
- nosmt disables SMT/Hyper-Threading and can change core topology; re-check core plans after applying.
- The app runs a pre-flight warning for TSC knobs when safety checks look risky.

Sources
- Kernel parameters reference (clocksource=, tsc=, nmi_watchdog=, nosoftlockup)
  - https://www.kernel.org/doc/html/latest/admin-guide/kernel-parameters.html
- Ubuntu RT kernel tuning parameters (NMI watchdog, softlockup, TSC)
  - https://documentation.ubuntu.com/real-time/en/latest/tutorial/intel-tcc/kernel-parameters/

-------------------------------------------------------------------------------
## PipeWire Clock Constraints (Advanced)

Goal
- Provide a single advanced knob to constrain PipeWire’s clock/quantum behavior
  without overwhelming regular users.

Settings in scope (pipewire.conf context.properties)
- default.clock.allowed-rates
- default.clock.min-quantum
- default.clock.max-quantum
- default.clock.quantum-limit
- default.clock.quantum-floor
- clock.power-of-two-quantum

Out of scope (handled by existing knobs)
- default.clock.rate
- default.clock.quantum

UI
- Advanced tab only.
- One dropdown / dialog for all fields.
- Status shows per-setting status for each field.
- Info dialog explains:
  - min/max quantum = allowed operating range
  - quantum floor/limit = buffer reservation range
  - most users should leave these unset
  - allowed-rates is disabled by default in PipeWire due to kernel/Bluetooth issues

Apply/Reset
- Use drop-in: ~/.config/pipewire/pipewire.conf.d/99-audioknob-clock-constraints.conf
- Only write keys with configured values.
- Reset removes this file only.

Status
- Applied if all configured keys match file content.
- Partial if some match.
- Not applied if file missing or no matches.

Sources
- PipeWire config reference: pipewire.conf(5)
  - https://docs.pipewire.org/page_man_pipewire_conf_5.html
  - https://manpages.ubuntu.com/manpages/noble/man5/pipewire.conf.5.html
- PipeWire config lookup + drop-in behavior
  - https://docs.pipewire.org/devel/page_man_pipewire_conf_5.html

-------------------------------------------------------------------------------
## PipeWire Memory Locking (mlock policy)

Goal
- Reduce xruns by keeping PipeWire memory resident, when safe.

Settings (pipewire.conf context.properties)
- mem.allow-mlock
- mem.mlock-all

Dependencies
- Requires sufficient memlock limits (PAM limits). If memlock limits are low,
  mlock-all may fail or be unsafe.

UI
- Advanced tab only. Simple toggle(s) with warning copy.

Apply/Reset
- Drop-in file: ~/.config/pipewire/pipewire.conf.d/99-audioknob-mlock.conf
- Reset removes this file only.

Status
- Verify file contains configured keys.
- Optionally warn if memlock limits appear low (non-blocking).

Sources
- PipeWire config reference: pipewire.conf(5)
  - https://docs.pipewire.org/page_man_pipewire_conf_5.html

-------------------------------------------------------------------------------
## PipeWire RT Limits Group (rtprio/nice/memlock)

Goal
- Provide the equivalent of JACK-style rtprio limits for PipeWire users.
- Ensure PipeWire can obtain realtime scheduling via RLIMIT_RTPRIO.

Rationale
- PipeWire’s RT module requires RLIMIT_RTPRIO at or above the configured RT
  priority; otherwise it falls back to RTKit / portal.

Implementation approach
- Create /etc/security/limits.d/95-pipewire.conf (root).
- Ensure group membership for the target group:
  - Prefer "pipewire" group if it exists.
  - If not, offer a configurable fallback group (audio/realtime) or prompt.
- Add only our lines; keep the file additive.

Example lines (values must be confirmed per distro policy)
- @pipewire - rtprio 95
- @pipewire - nice -19
- @pipewire - memlock 4194304

Apply/Reset
- Apply adds missing lines to our own file.
- Reset removes only our file (never edits other limits files).

Status
- Check presence of required lines in our file.
- Check user membership in target group.

Sources
- PipeWire RT module requires RLIMIT_RTPRIO; falls back to RTKit if not present.
  - https://pipewire.pages.freedesktop.org/pipewire/page_module_rt.html
  - https://manpages.ubuntu.com/manpages/resolute/en/man7/libpipewire-module-rt.7.html
- PipeWire Performance Tuning (user-provided excerpt, 20 Apr 2023)

Open questions / TODO
- Confirm distro-default values for rtprio/nice/memlock in official packaging.
- Decide whether to set conservative defaults or require explicit user input.
- Decide if the knob should offer 95/‑19/4194304 as a preset (matches the
  PipeWire performance tuning guidance) or ask users to enter values.

-------------------------------------------------------------------------------
## PipeWire RT Module Tuning (module.rt.args)

Goal
- Allow advanced users to tune PipeWire’s RT priorities and RT safety budgets
  using official module arguments.

Settings (module.rt.args)
- rt.prio
- rt.time.soft / rt.time.hard
- nice.level
- rlimits.enabled / rtkit.enabled / rtportal.enabled

Apply/Reset
- Drop-in file: ~/.config/pipewire/pipewire.conf.d/99-audioknob-rt-module.conf
- Set only provided args.
- Reset removes this file only.

Status
- Verify configured args exist in our drop-in.

Sources
- libpipewire-module-rt(7) module options and override section
  - https://pipewire.pages.freedesktop.org/pipewire/page_module_rt.html
  - https://manpages.ubuntu.com/manpages/resolute/en/man7/libpipewire-module-rt.7.html
- PipeWire Performance Tuning (user-provided excerpt, 20 Apr 2023)

Notes
- module-rt is enabled in server and client configs; relevant files listed by PipeWire:
  - /usr/share/pipewire/pipewire.conf
  - /usr/share/pipewire/pipewire-pulse.conf
  - /usr/share/pipewire/client-rt.conf
  - /usr/share/pipewire/jack.conf
  Use drop-ins rather than editing these vendor files.
- UI note: the app now exposes a combined **PipeWire RT Setup** knob that configures
  RT limits and module-rt together for simpler setup; the standalone knobs are
  hidden in the UI but retained for worker operations. RT limits can be disabled
  in the setup dialog (Safe RT preset uses RTKit/portal only).

-------------------------------------------------------------------------------
## WirePlumber ALSA USB Period/Buffer Tuning

Goal
- Reduce latency and jitter for USB audio devices by tuning period size and
  buffer behavior in the ALSA monitor rules.

Settings (WirePlumber ALSA rules)
- api.alsa.period-size
- api.alsa.period-num
- api.alsa.headroom
- api.alsa.disable-batch

Notes
- USB devices are commonly batch devices; `api.alsa.disable-batch` can be used
  to force timer-based scheduling.
- `api.alsa.headroom` and period settings influence latency vs stability.

Device scope
- Should target USB audio devices only (match rules), not all ALSA devices.

Apply/Reset
- WirePlumber drop-in in user config:
  - ~/.config/wireplumber/wireplumber.conf.d/90-audioknob-alsa.conf
- Use monitor rules to match USB cards and set ALSA properties.
- Reset removes this file only.

Status
- Check for our drop-in file and configured properties.
- If the system uses a different session manager, status is not_applicable.

Sources
- WirePlumber ALSA configuration reference (property semantics)
  - https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/alsa.html
- PipeWire Performance Tuning (user-provided excerpt, 20 Apr 2023)

Notes (from performance tuning guidance)
- Since PipeWire 0.3.43, ALSA USB period-size tuning is applied automatically
  when the device is opened and is based on the graph quantum. Any manual rule
  should avoid fighting the automatic behavior.

Open questions / TODO
- Confirm WirePlumber config directory layout for 0.5+ across distros.
- Decide how to scope to USB devices (match rules).

-------------------------------------------------------------------------------
## Pro Audio Profile (per-device toggle)

Goal
- Provide a simple per-device toggle to switch a device into "Pro Audio" profile
  when it exists, without relying on JACK.

Background (official)
- PipeWire lists ALSA card profiles that come from UCM or ACP, except "Pro Audio"
  which is a special profile not supplied by those systems.
- The "Pro Audio" profile usually enables `api.alsa.disable-tsched` and
  `api.alsa.auto-link` when IRQ scheduling is expected to work on the hardware.
- In Pro Audio mode, nodes from the same device are assumed to share a clock,
  so adaptive resampling is avoided when linking capture to playback on that
  device.

Implementation approach
- Detect available profiles for each device; prefer `wpctl` and fall back to
  `pactl` when profiles are not exposed via `wpctl inspect`.
- Apply by switching the profile via WirePlumber's control tool:
  - wpctl set-profile <device-id> <profile-index>
- If `wpctl` does not expose profiles, apply via:
  - pactl set-card-profile <card-name> pro-audio
- Reset by restoring the previous profile (recorded during apply).

Discovery / device-agnostic rules
- Use `wpctl` to list devices and profiles when possible.
- Use `pactl list cards` to confirm availability and current profile when
  `wpctl inspect` omits profiles.
- Do not hardcode profile indices; read them at runtime.
- If the session manager is not WirePlumber (wpctl missing), mark as
  not_applicable and do not offer the toggle.

Status
- Applied if the current profile equals "Pro Audio".
- Not applied if Pro Audio exists but another profile is active.
- Not applicable if no Pro Audio profile exists for the device.

Sources
- PipeWire properties & ALSA profile origins (UCM/ACP, Pro Audio exception):
  https://docs.pipewire.org/page_man_pipewire-props_7.html
- Pro Audio profile behavior (disable-tsched/auto-link, clock sharing):
  https://docs.pipewire.org/1.2/page_man_pipewire-props_7.html
- WirePlumber CLI profile switching (wpctl set-profile):
  https://manpages.ubuntu.com/manpages/resolute/man1/wpctl.1.html

Open questions / TODO
- Confirm the best way to enumerate device profiles with wpctl (status vs inspect).
- Verify how profile naming appears across distros ("Pro Audio" vs "pro-audio").

-------------------------------------------------------------------------------
## PipeWire Data Loop Affinity (Advanced)

Goal
- Allow expert users to pin PipeWire data loop threads to specific CPU cores
  and set RT priority for those loops.

Settings (pipewire.conf context.properties)
- context.num-data-loops
- context.data-loops
- loop.rt-prio
- thread.affinity

Apply/Reset
- Drop-in file: ~/.config/pipewire/pipewire.conf.d/99-audioknob-data-loops.conf
- Reset removes this file only.

Status
- Verify configured loop definitions in our drop-in.

Sources
- PipeWire config reference: context.data-loops / loop.rt-prio / thread.affinity
  - https://docs.pipewire.org/page_man_pipewire_conf_5.html
- PipeWire Performance Tuning (user-provided excerpt, 20 Apr 2023)

-------------------------------------------------------------------------------
## RTKit Daemon Tuning (On hold / Needs verification)

Goal
- Tune RTKit daemon limits where distros expose configuration hooks.

Risk
- Highly distro-specific. Incorrect overrides can break RTKit or system DBus
  policy, or be ignored entirely.

Status
- On hold until distro-specific configuration guidance is confirmed.
- PipeWire can still use RTKit via module-rt; this knob only tunes the daemon.

TODO (research gate)
- Identify authoritative config locations per distro (systemd override or
  EnvironmentFile, if any).
- Confirm supported arguments and defaults from official RTKit docs.

Potential sources to investigate
- Distro packaging docs for rtkit-daemon
- systemd unit EnvironmentFile declarations

-------------------------------------------------------------------------------
## Live XRUN Counter (Monitoring)

Goal
- Provide a live XRUN/error counter to help users evaluate tuning changes.

Background (official)
- The profiler module provides profiling data consumed by pw-top/pw-profiler.
- pw-top shows a live table of nodes with an ERR column (XRUNs + errors).

Implementation approach
- Use profiler data to sample ERR counts per relevant node (driver + client).
- Display total and delta counts (e.g., XRUNs per minute).
- If profiler data is unavailable, show "unknown" with a hint to enable it.

Discovery / device-agnostic rules
- Check for the profiler module; if absent, offer a one-click enable action
  (advanced) via a drop-in config (module.profiler.args).
- Avoid hard dependency on JACK; use PipeWire's own profiler data.

Status / UX
- Live counter should be read-only (no apply/reset).
- Surface per-node ERR deltas and total errors.

Sources
- Profiler module (libpipewire-module-profiler):
  https://pipewire.pages.freedesktop.org/pipewire/page_module_profiler.html
- pw-top ERR column definition and batch mode options:
  https://man.voidlinux.org/pw-top.1

Notes from performance tuning guidance (user-provided)
- For Red Hat/Arch-style packaging:\n+  - Add a systemd override to inject RTKIT_ARGS and load\n+    /etc/sysconfig/rtkit via EnvironmentFile.\n+  - Replace ExecStart with /usr/libexec/rtkit-daemon $RTKIT_ARGS.\n+- For Debian/Ubuntu-style packaging:\n+  - Use `systemctl edit rtkit-daemon.service` to override ExecStart and load\n+    /etc/dbus-1/system.d/rtkit for RTKIT_ARGS.\n+  - Requires reboot after changes.\n+- Example RTKIT_ARGS (needs confirmation per distro/policy):\n+  --scheduling-policy=FIFO\n+  --our-realtime-priority=89\n+  --max-realtime-priority=88\n+  --min-nice-level=-19\n+  --rttime-usec-max=2000000\n+  --users-max=100\n+  --processes-per-user-max=1000\n+  --threads-per-user-max=10000\n+  --actions-burst-sec=10\n+  --actions-per-burst-max=1000\n+  --canary-cheep-msec=30000\n+  --canary-watchdog-msec=60000

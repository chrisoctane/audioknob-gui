# Changelog

All notable changes to audioknob-gui are documented here.

Format: Keep a short summary per release with clear headings.

## [0.7.13] - 2026-03-17

### Changed
- Local openSUSE RPM builds now package the tracked working tree instead of `git HEAD`, so local launcher builds include uncommitted tracked fixes. Untracked files remain excluded unless added to git.

### Fixed
- **Tuned persistence across reboot**: applying the Power Profile knob with backend `tuned` now masks `power-profiles-daemon.service`, preventing D-Bus activation from restarting ppd and stopping tuned after reboot.
- **Power Profile reset safety**: reset, force-reset, and transaction restore now unmask and restore `power-profiles-daemon.service` before returning to the prior backend/profile, including older transactions that predate the new metadata.
- **Dev-mode root worker mismatch**: repo GUI runs now refuse privileged actions when the fixed-path pkexec worker is still pointing at an older installed checkout, preventing silent split-brain behavior between GUI code and root operations.

## [0.7.12] - 2026-03-08

### Added
- **Live system state probing** for sysctl knobs: when audioknob's config file
  is absent but the live `/proc/sys/` value matches the target, status shows
  "~ Active" (blue) instead of "not applied". Covers swappiness, dirty_bytes,
  inotify, and rt_throttling.
- **Tuned status details**: Power Profile status dialog shows a "tuned-managed
  settings" section with live system values and match indicators. Individual
  tuned-locked knob dialogs show tuned ownership context.

### Fixed
- **Power Profile backend switch**: applying tuned now disables ppd first;
  resetting or force-resetting stops tuned and re-enables ppd with balanced
  profile. Previously reset left tuned running.
- **Stale config cleanup**: applying tuned automatically removes audioknob's
  sysctl config files for swappiness and dirty_bytes (backed up in the
  transaction for restore), preventing config stacking.

## [0.7.11] - 2026-03-08

### Added
- **Tuned ownership locks**: when Power Profile is applied with tuned backend,
  overlapping knobs (CPU Governor, C-state limits, Swappiness, Dirty Bytes) are
  locked with "via tuned" status and disabled action buttons. Locks are derived
  (no persistent state) and release when Power Profile is reset.
- Simple mode conflict gate extended to skip Swappiness and Dirty Bytes when
  tuned is active, preventing config stacking.
- Future enhancement logged: Live System State Probing (per-knob probe of actual
  system values regardless of who applied them).

### Fixed
- Tuned-locked knobs now show disabled lock buttons instead of active
  Apply/Reset buttons.
- Status buttons on locked rows retain hover feedback and click behaviour.
- Preset dots suppressed on tuned-managed knobs to avoid showing stale
  reference/factory indicators.

## [0.7.10] - 2026-03-04

### Changed
- PipeWire RT setup dialog redesigned with a preset dropdown (Full RT, Safe RT, Custom)
  replacing the single Safe RT button; layout switched to a compact two-column grid (520×600).
- Knob ID strings extracted to a new `knob_ids.py` constants module; 16 files updated
  to use named constants instead of bare string literals.

### Fixed
- PipeWire module status check now correctly includes `uclamp_min`, `uclamp_max`, and
  `cpu_zero_denormals` in `module_keys`; previously these fields were silently ignored,
  causing RT setup to report as unconfigured when only uclamp/denormal settings were set.

## [0.7.9] - 2026-02-19

### Changed
- RTIRQ restore now auto-disables `rtirq.service` when older transactions were recorded before the service existed, reducing force-reset handoffs during normal reset flows.
- Workqueue cpumask handling now normalizes CPU-list selections to kernel mask syntax on apply and accepts both list/mask representations during status checks.

### Fixed
- Sysfs write failures in apply now surface a clear knob-scoped error message instead of bubbling an unhandled traceback.
- Modeless XRUN/Jitter monitor dialogs now stop polling cleanly on close to prevent hidden background refresh loops.

## [0.7.8] - 2026-02-18

### Fixed
- CI quality-gate workflows now install required Qt runtime libraries (`libegl1`, `libgl1`) before pytest so PySide6 imports succeed on GitHub-hosted Ubuntu runners.
- Release-tag and master-branch gate runs now use the same Qt runtime preinstall step, preventing `ImportError: libEGL.so.1` during test collection.

## [0.7.7] - 2026-02-18

### Added
- New Dev-tab knobs for advanced partitioning and stack policy: `irqbalance_banned_cpulist`, `kernel_workqueue_cpumask`, `cgroup_user_slice_allowed_cpus`, `systemd_pipewire_service_rt`, `systemd_wireplumber_service_rt`, `pipewire_pulse_latency`, `pipewire_pulse_app_rules`, and `pipewire_profiler_enable`.
- New regression coverage for linked core-plan behavior and newly added config-required knob flows.

### Changed
- Cores & IRQ now defaults to a linked core-plan model where audio-role selectors share one core set and housekeeping-role selectors use its inverse.
- Clearing core selections and applying now performs explicit reset semantics for core-policy knobs instead of silently reusing defaults.
- Dev config-required knobs stay locked on Apply until configured, while Configure remains available.

### Fixed
- Conflict/status handling now reports audio isolation mismatches consistently across `isolcpus`, `nohz_full`, and `rcu_nocbs`.

## [0.7.6] - 2026-02-16

### Changed
- Queue dependency handling now treats queued dependency applies as satisfying dependency locks, so dependent knobs can be applied together in one run.
- Queue apply execution is now dependency-ordered, so prerequisite knobs are applied before dependent knobs in the same queue.

### Fixed
- IRQ Pinning no longer shows a conflict against the `irqbalance_disable` dependency knob.
- Configure dialogs for IRQ Pinning, QjackCtl RT cores, and kernel core selectors now use the PySide6 dialog result enum correctly (fixes `AttributeError: ... has no attribute 'Accepted'`).

## [0.7.5] - 2026-02-16

### Changed
- Reset workflows now restore knob-owned state from transaction backups/effects with surgical semantics, reducing unintended drift across unrelated knobs.
- Full-table action behavior now treats `Partial` status as resettable, so mixed-state knobs queue `Reset` directly.

### Fixed
- CPU Performance vs Power Profile conflict handling now remains stable after reset by treating CPU governor persistence (config + service) as the status source of truth.
- RT IRQ mixed states (`config`/`service` mismatch) now expose a direct reset path, and reset surfaces a force-reset handoff when baseline service state cannot be reconstructed from transaction history.
- Factory reset no longer relies on package reinstall side effects; package-owned files are restored from captured transaction backups.

## [0.7.4] - 2026-02-14

### Added
- Release-gate version drift enforcement across `pyproject.toml`, `audioknob_gui/__init__.py`, and `PROJECT_STATE.md`.
- Simple-mode queue preview now stays intent-complete for dial-up/down:
  - dimmed reason labels for filtered apply rows (`already active`, `manual action`)
  - level-0 reset preview shows all simple knobs, including non-reset rows with explanations (`set outside AudioKnob`, `already off`, `manual action`)

### Changed
- Simple apply preflight now removes non-queue kinds from worker payload and skips duplicate applies for already-active knobs, while preserving full preview visibility.
- Simple/full mode transitions keep queue semantics stable (no spurious re-queue on view switch for already-active knobs).
- App title git-revision detection now prefers `git rev-parse` and falls back to `.git` metadata/packed-refs parsing.

### Fixed
- `audio_group_membership` no longer triggers worker `Unsupported knob kind: group_membership` failures from simple apply paths.
- App runtime version was aligned from `0.7.2` drift to release-tracked package versioning.

## [0.7.3] - 2026-02-14

### Added
- Stabilization batch control contract at `docs/internal/audit/STABILIZATION_STATE.md`.
- Multi-agent control architecture blueprint at `docs/internal/audit/MULTI_AGENT_CONTROL_SYSTEM.md`.
- Additional gate-script regression coverage for docs/privilege/stabilization enforcement paths.

### Changed
- `scripts/check_repo_consistency.py` now enforces:
  - `docs/KNOB_INTERACTIONS.md` updates when conflict/knob behavior paths change.
  - Stabilization scope constraints (allowlist + max changed files) when stabilization mode is on.
- Quality gate and agent workflow docs now include stabilization scope requirements.

### Fixed
- Local consistency checks now use local in-progress diffs for stabilization scope checks (avoids false positives from historical branch deltas).
- Privilege-path and docs-drift guardrails were tightened to reduce agent scope creep and policy bypass risk.

## [0.7.2] - 2026-02-11

### Added
- New simple-mode knob: `realtime_clock_access` (fixed low-latency timer device access preset).
- New parity/audit planning docs and templates under `docs/KNOB_SYSTEM_AUDIT_MAP.md` and `docs/internal/audit/2026-02-11/`.
- Refreshed screenshot set in `docs/` (`screenshot1.png` to `screenshot5.png`) and updated README preview images.

### Changed
- Simple-mode queue composition now keeps apply/reset parity tighter across level transitions.
- Risk-tier plan/docs now include realtime clock access in simple-mode inclusion guidance.

### Fixed
- RT scanner expectation text now aligns with realtime clock access handling.
- Simple-mode queue tests expanded for regression coverage around queue composition behavior.

## [0.7.1] - 2026-02-11

### Added
- Full-view header now has a dedicated `View` button for fast Basic/Full switching.
- Tools menu now has a `Locks` submenu that contains reboot/advanced/technical lock toggles plus `Release AudioKnob Locks`.
- IRQ Overview now includes a dense aligned table (`IRQ`, `Affinity`, `Mode`, per-core counts, `Description`) with horizontal scrolling.
- IRQ Overview adds a hover crosshair with click lock/unlock and a dialog-local font size control.

### Changed
- Renamed the full-view `Advanced` tab to `Cores & IRQ` to reduce naming ambiguity.
- Moved `IRQ Overview` button to the Audio Core Plan header so it remains visible when the plan body is collapsed.
- Simple dial finish is now flat grey/black with a white cap + pointer (no gradient).

### Fixed
- IRQ Overview font scaling now resizes columns/header/core-map consistently.
- IRQ Overview row/header sizing is compact, large per-core counts truncate with tooltip full values, and IRQ ID width avoids clipping for common 3-4 digit IDs.

## [0.7.0] - 2026-02-11

### Added
- Simple-mode `AudioKnob` home view with a large animated dial (`0` Off + `1..11` risk tiers) that composes a visible apply queue.
- Tools menu actions for `Toggle View` (Simple/Full) and `Clear Queue`.
- Simple-mode ownership locks in Full view (`Managed by AudioKnob`) with explicit release action.
- Simple-mode fixed preset composition for included configurable bundles (power-profile backend auto/performance, PipeWire RT safe bundle, mlock preset).

### Changed
- Simple-mode layout now keeps one plain-text **Apply queue** list on the left of the dial.
- Dial rendering upgraded to a custom hardware-style knob with smooth rotation decoupled from queue recomposition.
- Dial pointer bar refined to a wide square-ended white marker integrated with the center cap.
- Dial input now includes an explicit `0` off detent while preserving `1..11` ring label placements.

### Fixed
- Combo-box wheel changes are ignored unless the combo popup is open, preventing accidental config changes while scrolling.
- Simple queue composition skips CPU governor when power profile backend resolves to tuned, avoiding false conflict paths.

## [0.6.10] - 2026-02-10

### Fixed
- PipeWire RT Setup Safe RT preset now restores all setup dialog fields back to the preset/default values.
- Table refreshes now preserve scroll position when changing configs (no more jumping away from the current view).

## [0.6.9] - 2026-02-08

### Fixed
- CI now runs unit tests in headless environments by avoiding Qt imports at module import-time (lazy imports in status helpers).
- IRQ housekeeping `irqaffinity` auto-override no longer generates an implicit "all CPUs" value when audio cores are unset.

## [0.6.8] - 2026-02-08

### Added
- Preset match indicators now use visible color dots (blue for Reference, green for Factory) in the status cell and Presets menu.
- Header now includes a **Technical columns** toggle to show/hide Req/Risk/CLI columns (off by default).
- Tx History now includes expanded detail columns for Knob IDs plus richer Files/Effects summaries.

### Changed
- Preset workflows now use musician-first language and operational status stays primary (`Applied`, `Not applied`, `Partial`, `Reboot`, `Unknown`, `N/A`).
- Factory preset capture/import actions now remain visible with explicit `(Locked)` labeling when factory preset immutability is active.

### Fixed
- Factory preset capture/import menu options no longer appear inert when locked; selecting them now surfaces a clear lock explanation.

## [0.6.7] - 2026-02-03

### Added
- App window icon now loads from the system theme (with fallback to hicolor sizes) to fix taskbar icons.

### Changed
- Package installs now include the app icon at 64/128/256/512/1024 sizes for better desktop integration.
- Placeholder app icon updated with transparent background.

## [0.6.6] - 2026-02-02

### Added
- Factory Defaults workflow (capture/import/export/restore/reset) in Tools menu.
- Pre-import backup capture for mismatched baseline/factory restores (saved in `~/Documents/audioknob/`).

### Changed
- Baseline/factory snapshots preserve the originating system profile metadata on export.
- Mismatched baseline/factory restores warn, capture a backup, and queue only compatible changes.

## [0.6.5] - 2026-02-01

### Changed
- Power profile status now falls back to service state and reports not_applied when the backend is inactive.
- Unconfigured PipeWire/WirePlumber knobs report not_applied instead of unknown.

### Fixed
- PipeWire Pro Audio status detection now handles node-based IDs via device.profile.pro and ALSA card name fallback.

## [0.6.4] - 2026-02-01

### Added
- Baseline snapshots now capture per-knob config values and support queued restore via Tools → Baseline → Queue Restore Baseline.
- Conflict resolution dialog in the header with selectable resets.
- Dev kernel knob for nosmt (Disable SMT).
- Tools menu shortcuts for Jitter Monitor/Jitter Test plus terminal launchers for Latencytop and Cyclictest.

### Changed
- Conflicting knobs now show a red Conflict action and red status instead of a lock icon.
- Conflict detection ignores unknown/not applicable knobs unless queued.
- Partial status color adjusted to a lighter pastel yellow.

### Fixed
- Conflict counter now refreshes after status updates.
- Terminal tool detection now respects GUI PATH quirks via which_command.

## [0.6.3] - 2026-01-29

### Added
- PipeWire RT Setup status check (Status column + info dialog) with component breakdown.
- PipeWire RT Setup Safe RT preset (RTKit/portal only) and RT limits toggle.
- Apply-time conflict prompt with Apply+Reset / Apply anyway / Cancel and details from KNOB_INTERACTIONS.
- TSC knobs now show a pre-flight warning when safety checks look risky.
- Status labels now show a conflict marker and tooltip when a knob conflicts with other applied/queued knobs.
- Dev kernel knob for preempt=full.
- Expanded conflict warnings: PipeWire mlock vs RT limits, RTIRQ vs threadirqs, and CPU isolation core mismatches.

### Changed
- PipeWire RT Setup promoted out of Dev and shown in main/advanced views.
- PipeWire knobs renamed from “PW …” to “PipeWire …”.
- Global Apply/Apply & Reboot controls moved left of Tools in the header.
- Pro Audio profile switching now prefers pactl when wpctl doesn’t expose profiles; reset restores the previous profile.

### Fixed
- Pro Audio device parsing and apply flow (wpctl/pactl fallback) now records JSON output reliably.
- PipeWire RT Setup queue button styling now reflects queued actions.
- Status/Check dialog now includes partial reasons for PipeWire config knobs and RT Setup components.

## [0.6.2] - 2026-01-27

### Added
- Live Jitter Monitor dialog (modeless) with rolling per-thread stats and a snapshot refresh in the info dialog.
- XRUN monitor reset button (local baseline) and ERR summary table.

### Changed
- XRUN monitor now pulls the latest pw-top batch output and fills QUANT/RATE from pw-dump when batch metrics are zero.
- XRUN monitor moved to Main tab.
- Requirements column now uses A/R/D markers; dependency tooltips include group details.
- Tools menu layout updated (Baseline + Tx History grouped under Tools; “Scan System Profile…” label shown in full).

## [0.6.1] - 2026-01-26

### Fixed
- Pro Audio device list now parses `wpctl status` tree output reliably.

### Changed
- Agent workflow docs now explicitly require reading the correct docs per task.

## [0.6.0] - 2026-01-26

### Added
- Dev tab for experimental knobs and tooling.
- PipeWire advanced knobs: clock constraints, mlock policy, RT module tuning, data loop affinity.
- WirePlumber ALSA USB tuning drop-in.
- Pro Audio profile switch (wpctl) and live XRUN monitor (pw-top).

### Changed
- GUI refactor into modular dialogs, table, and knob-specific UI hooks.
- System profile discovery expanded for WirePlumber paths and improved cpupower/rtirq detection.

### Notes
- Dev knobs are experimental; RTKit tuning remains a placeholder until distro guidance is verified.

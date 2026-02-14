# Changelog

All notable changes to audioknob-gui are documented here.

Format: Keep a short summary per release with clear headings.

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

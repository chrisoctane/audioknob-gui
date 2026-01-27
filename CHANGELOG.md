# Changelog

All notable changes to audioknob-gui are documented here.

Format: Keep a short summary per release with clear headings.

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

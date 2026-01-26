# Changelog

All notable changes to audioknob-gui are documented here.

Format: Keep a short summary per release with clear headings.

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

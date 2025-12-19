# audioknob-gui: Project State

## Guardrails (non-negotiable)

- No system changes without an explicit **Preview → Confirm → Apply**.
- Every apply is a **transaction** with backups + manifest; undo is always possible.
- Keep UI simple; advanced info is optional.
- Distro-aware: detect and adapt to openSUSE/Fedora/Debian/Arch differences.

---

## Status

- ✅ **Phase 1: Foundation**: Complete
  - Repo skeleton, GUI, Worker (pkexec), Registry Schema, Transaction/Undo
  - Initial Knobs: rt_limits, irqbalance, swappiness, thp_madvise, governor

- ✅ **Phase 2: Essential Knobs**: Complete
  - 8 knobs implemented and working (including read-only knobs)

- ✅ **Phase 3: UX Refinements**: Complete
  - Status column showing applied/not-applied state per knob
  - Per-knob restore functionality ("Restore original" works)
  - Read-only knob action buttons (View Stack, Run Test)
  - CPU core selector dialog for QjackCtl knob
  - Simplified confirmation dialogs (rely on pkexec password)
  - Reset to Defaults with smart restore (delete/backup/package-manager)
  - Font size control with persistence
  - Rich multi-line tooltips

- 🔄 **Phase 4: Audio Configuration Knobs**: In Progress
  - [ ] Audio interface selection for apps
  - [ ] Sample rate configuration
  - [ ] Bit depth configuration
  - [ ] Buffer size configuration
  - [ ] PipeWire quantum tuning

- 🔲 **Phase 5: Monitoring & Diagnostics**: Planned
  - [ ] Underrun monitoring (xruns)
  - [ ] Interrupt inspection
  - [ ] Blocker prediction (what prevents optimizations)
  - [ ] Live latency display

- 🔲 **Phase 6: Advanced System Knobs**: Planned
  - Kernel cmdline knobs with distro-aware GRUB/BLS handling
  - rtirq, cpu_dma_latency, PCI latency

- 🔲 **Phase 7: Distro Abstraction**: Planned
  - Bootloader detection (openSUSE BLS vs traditional GRUB)
  - Package manager integration (zypper, apt, dnf, pacman)

- 🔲 **Phase 8: Packaging & Distribution**: Planned
  - Proper packaging (RPM, DEB, Flatpak)
  - Bundle dependencies or prompt to install them
  - Remove hardcoded dev paths from worker script

- 🔲 **Phase 9: Distro-Specific Integrations** (optional):
  - openSUSE: YaST module wrapper
  - Fedora: GNOME Settings panel or Cockpit plugin
  - Ubuntu: ubuntu-drivers-common style integration

---

## Current Implementation

### Entry Points
- **GUI**: `bin/audioknob-gui` (PySide6)
- **Worker (pkexec target)**: `packaging/audioknob-gui-worker` → `/usr/local/libexec/audioknob-gui-worker`

### Knob Registry
- File: `config/registry.json`
- Current knobs (8):
  - `rt_limits_audio_group` (PAM limits for @audio)
  - `irqbalance_disable` (systemd unit toggle)
  - `cpu_governor_performance_temp` (sysfs)
  - `swappiness` (sysctl.d)
  - `thp_mode_madvise` (sysfs)
  - `qjackctl_server_prefix_rt` (user config file)
  - `stack_detect` (read-only info)
  - `scheduler_jitter_test` (read-only test)

### GUI Table Columns

| # | Column | Purpose |
|---|--------|---------|
| 0 | Title | Knob name |
| 1 | Status | Applied/Not applied/Partial (color-coded) |
| 2 | Description | What it does |
| 3 | Category | Grouping |
| 4 | Risk | Low/Medium/High |
| 5 | Action | Dropdown OR button (see below) |
| 6 | Configure | Per-knob config buttons |

### Action Column Widget Types

The **Action column (5)** uses different widgets based on knob type:

| Knob Type | Widget | Options/Action |
|-----------|--------|----------------|
| **Normal knob** | `QComboBox` | Keep current / Apply optimization / Restore original |
| **Read-only info** | `QPushButton` | "View Stack" → shows detection results |
| **Read-only test** | `QPushButton` | "Run Test" → runs test and shows results |

### Configure Column Widget Types

The **Configure column (6)** is for per-knob configuration:

| Knob | Widget | Action |
|------|--------|--------|
| `qjackctl_server_prefix_rt` | `QPushButton` | "Configure…" → CPU core selector dialog |
| Other normal knobs | Empty | - |
| Read-only knobs | Empty | - |

**Future additions** (interface/rate/buffer config) should follow this pattern:
- If configurable parameters exist → add "Configure…" button in column 6
- If it's an action/test → use button in column 5 instead of dropdown

### Transaction Model
- Root knobs: `/var/lib/audioknob-gui/transactions/<txid>/`
- User knobs: `~/.local/state/audioknob-gui/transactions/<txid>/`
- Each file backup includes: `we_created`, `reset_strategy`, `package` metadata

### Reset Strategies
- **delete**: File we created → just delete it
- **backup**: User config → restore from our backup
- **package**: System file → use `rpm --restore` / `apt reinstall` / `pacman -S`

### This System (openSUSE Tumbleweed)
- **Boot loader**: GRUB2-BLS with sdbootutil
- **Kernel cmdline**: `/etc/kernel/cmdline` (already has `threadirqs`)
- **Update command**: `sdbootutil update-all-entries`

---

## Known Issues / TODO

### Preview Dialog Clarity
- **Issue**: "Will change" section shows empty when no file changes
- **Fix needed**: Show meaningful message like "No file changes (runtime-only)" or hide section

### Potential Blockers to Detect
These conditions might prevent optimizations from working:

| Blocker | Detection | Message |
|---------|-----------|---------|
| Not in audio group | `groups` command | "Add yourself to 'audio' group and re-login" |
| Kernel not RT | `/sys/kernel/realtime` or `uname -v` | "Consider installing RT kernel for lowest latency" |
| PipeWire not running | systemctl status | "PipeWire not active - some knobs won't apply" |
| JACK not configured | QjackCtl config missing | "Configure QjackCtl before applying prefix" |
| No cyclictest | `which cyclictest` | "Install cyclictest package for jitter testing" |
| cpupower not installed | `which cpupower` | "Install cpupower for persistent governor" |

---

## Comprehensive Plan

See `PLAN.md` for:
- Complete list of planned knobs organized by category
- New Audio Configuration category (interface, rate, buffer, depth)
- Monitoring & Diagnostics features
- Distro-specific implementation notes
- Architecture diagram
- Implementation phases with checkboxes

---

## Key References

- https://wiki.linuxaudio.org/wiki/system_configuration
- https://wiki.archlinux.org/title/Professional_audio
- https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

---

*Document updated by Claude Opus 4.5 on 2024-12-19*

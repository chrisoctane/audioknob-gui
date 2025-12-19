# audioknob-gui: Project State

## Guardrails (non-negotiable)

- No system changes without an explicit **Preview → Confirm → Apply**.
- Every apply is a **transaction** with backups + manifest; undo is always possible.
- Keep UI simple; advanced info is optional.
- Distro-aware: detect and adapt to openSUSE/Fedora/Debian/Arch differences.

## Status

- ✅ **Phase 1: Foundation**: Complete
  - Repo skeleton, GUI, Worker (pkexec), Registry Schema, Transaction/Undo
  - Initial Knobs: rt_limits, irqbalance, swappiness, thp_madvise, governor

- ✅ **Phase 2: Essential Knobs**: Complete
  - 7 knobs implemented and working

- 🔄 **Phase 3: User-Space Knobs**: In Progress
  - QjackCtl Prefix knob (core done, needs CPU core selector UI)
  - PipeWire tuning (planned)

- 🔲 **Phase 4: Advanced System Knobs**: Planned
  - Kernel cmdline knobs with distro-aware GRUB/BLS handling
  - rtirq, cpu_dma_latency, PCI latency

- 🔲 **Phase 5: Distro Abstraction**: Planned
  - Bootloader detection (openSUSE BLS vs traditional GRUB)
  - Package manager integration (zypper, apt, dnf, pacman)

## Current Implementation

### Entry Points
- **GUI**: `bin/audioknob-gui` (PySide6)
- **Worker (pkexec target)**: `bin/audioknob-worker` (privileged CLI)

### Knob Registry
- File: `config/registry.json`
- Current knobs (8):
  - `rt_limits_audio_group` (PAM limits for @audio)
  - `irqbalance_disable` (systemd unit toggle)
  - `cpu_governor_performance_temp` (sysfs)
  - `swappiness` (sysctl.d)
  - `thp_mode_madvise` (sysfs)
  - `qjackctl_server_prefix_rt` (user config file)
  - `stack_detect` (read-only)
  - `scheduler_jitter_test` (read-only)

### Transaction Model
- Root knobs: `/var/lib/audioknob-gui/transactions/<txid>/`
- User knobs: `~/.local/state/audioknob-gui/transactions/<txid>/`

### This System (openSUSE Tumbleweed)
- **Boot loader**: GRUB2-BLS with sdbootutil
- **Kernel cmdline**: `/etc/kernel/cmdline` (already has `threadirqs`)
- **Update command**: `sdbootutil update-all-entries`

## Comprehensive Plan

See `PLAN.md` for:
- Complete list of planned knobs (35+) organized by 11 categories
- Distro-specific implementation notes
- GRUB/boot loader handling per distro
- Package manager commands per distro
- Architecture diagram
- Implementation phases with checkboxes
- Learnings from multi-agent comparison

## Key References

- https://wiki.linuxaudio.org/wiki/system_configuration
- https://wiki.archlinux.org/title/Professional_audio
- https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

---

*Document updated by Claude Opus 4.5 on 2024-12-19*

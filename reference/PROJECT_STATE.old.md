## PROJECT_STATE (authoritative, update-only)

Purpose: prevent drift and make it easy to revert/verify what exists. This file is intended to be readable by both humans and tools.

### Guardrails
- **No code edits or system changes without explicit user approval.**
- Prefer **read-only detection** before adding any “apply” action.
- Any “apply” action must be **transactional**: backup → apply → verify → manifest → rollback supported.

### Repo location
- Working directory: `/home/chris/audioknobs/`

### What this project is
A cross-distro, safety-first tool to:
- enumerate “realtime audio performance knobs”
- show current state and risk
- apply/rollback changes transactionally
- run repeatable latency tests with plain-language output

### What this project is not (v1)
- Not an auto-tuner.
- Not a full DAW benchmark suite.
- Not a kernel build system.

---

## Current implementation snapshot (as of 2025-12-17)

### Entry points
- **GUI**: `/home/chris/audioknobs/bin/audioknobs-gui`
- **Worker (pkexec target)**: `/home/chris/audioknobs/bin/audioknobs-worker`

Run examples:
- `PYTHONPATH=/home/chris/audioknobs /home/chris/audioknobs/bin/audioknobs-worker preview --knob irqbalance_disable`

### Knob registry (data-driven)
- File: `/home/chris/audioknobs/config/registry.json`
- Current knobs (5):
  - `rt_limits_audio_group`
  - `irqbalance_disable`
  - `rtirq_enable_and_config`
  - `cpu_governor_performance_temporary`
  - `cpu_governor_performance_persistent`
- Each knob includes a short **description** used for user-facing previews.

### UI
- Qt GUI (PySide6) is the primary UI.\n+- The earlier TUI prototype has been removed (kept in git history).

### Transaction model (backup + rollback)
- Unprivileged/dry-run transactions: `~/.local/share/audioknobs/transactions/<txid>/...`
- Privileged/apply transactions: `/var/lib/audioknobs/transactions/<txid>/...`
- Each transaction directory contains:
  - `manifest.json`
  - `backups/<absolute/system/path/...>`

### Privilege model
- GUI runs unprivileged.\n+- Privileged operations are executed via **polkit (`pkexec`)** by invoking `bin/audioknobs-worker`.\n+- Backups/manifests are stored under `/var/lib/audioknobs/transactions/<txid>/...`.\n+- The GUI keeps transaction ids internal in `~/.local/share/audioknobs/state.json` (used for Restore actions).

### Dependency checks
- The GUI checks dependencies at startup and can offer pkexec-based installation of missing optional tools.\n+- Package installation uses distro adapters (zypper/dnf/apt-get; pacman not implemented yet).
- Current supported installers:
  - openSUSE family: `zypper`
  - Fedora/RHEL family: `dnf`
  - Debian/Ubuntu family: `apt-get update && apt-get install`
  - Arch/pacman: not implemented yet

### Tests implemented
Accessible from TUI via `t:tests`:
1) **Scheduler latency** (`cyclictest`)
   - Output field: `max_us` (microseconds of scheduler jitter)
   - Note: not audio buffer latency
2) **Theoretical audio latency** (computed)
   - Outputs: `one_way_ms`, `roundtrip_ms`
3) **Measured RTL (JACK)** (`jack_iodelay`)
   - Output field: `delay_frames`
   - Requires: JACK running + a loopback path (internal interface loopback or a cable)

---

## Known limitations / TODO (tracked design, not yet implemented)

### Audio stack + device selection (critical next area)
Goal: let users dedicate one interface to “pro audio” and keep desktop audio stable.
Not yet implemented:
- read-only detection of:
  - PipeWire running state + nodes
  - JACK running state + ports
  - ALSA cards/devices
- UI choice of:
  - “Pro Audio device” vs “Desktop device”
- safe “apply” actions to enforce routing/device ownership across:
  - PipeWire + WirePlumber policy
  - JACK device selection
  - ALSA direct (where applicable)

### Measured “system-only RTL”
Not yet implemented:
- ALSA loopback (`snd-aloop`) based measurement for software-only RTL (no physical device path)

### Versioning / reverting tool versions
Git is initialized in `/home/chris/audioknobs/` and changes are committed regularly.

---

## Decision log (short)
- TUI-first implementation (safer/faster to iterate).
- Cross-distro support via distro-family adapters.
- Don’t rely on hidden state: always print/store manifests and backups.

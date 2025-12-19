# audioknob-gui: project state log

## Guardrails (non-negotiable)

- No system changes without an explicit **Preview → Confirm → Apply**.
- Every apply is a **transaction** with backups + manifest; undo is always possible.
- Keep UI simple; advanced info is optional.

## Status

- ✅ **Repo skeleton**: Complete (separate git repo, GitHub: `chrisoctane/audioknob-gui`)
- ✅ **Knob registry schema + initial catalog**: Complete (5 foundational knobs)
- ✅ **Privileged worker (pkexec)**: Complete (preview/apply/restore/history commands)
- ✅ **GUI (Qt/PySide6)**: Complete (plan/preview/apply/undo workflow)
- ✅ **Stack/device detection**: Complete (read-only JACK/PipeWire/ALSA detection)
- ✅ **Testing integration**: Complete (cyclictest jitter test in GUI)
- ✅ **Polkit integration**: Complete (fixed-path worker launcher + policy)
- ✅ **Expanded knobs**: Complete (sysctl_conf kind, swappiness, thp_mode_madvise)
- 🔄 **QjackCtl Prefix knob**: In progress (non-root knob for JACK -R flags)

## Current implementation

### Entry points
- **GUI**: `bin/audioknob-gui` (PySide6)
- **Worker (pkexec target)**: `bin/audioknob-worker` (privileged CLI)

### Knob registry
- File: `config/registry.json`
- Current knobs (7):
  - `rt_limits_audio_group` (PAM limits for @audio)
  - `irqbalance_disable` (systemd unit toggle)
  - `cpu_governor_performance_temp` (sysfs)
  - `swappiness` (sysctl.d)
  - `thp_mode_madvise` (sysfs)
  - `stack_detect` (read-only)
  - `scheduler_jitter_test` (read-only)

### Transaction model
- Root knobs: `/var/lib/audioknob-gui/transactions/<txid>/`
- User knobs (planned): `~/.local/state/audioknob-gui/transactions/<txid>/`

### Next: QjackCtl Prefix knob
See `PLAN.md` for details on the non-root knob for JACK realtime flags.

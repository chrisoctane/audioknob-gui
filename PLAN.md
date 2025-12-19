## audioknob-gui: canonical plan

### Guardrails
- No system changes without explicit **Preview → Confirm → Apply**.
- Every apply creates a **transaction** with backups + manifest; undo is always possible.
- Keep UI simple; advanced info is optional.

### Reality check: JACK realtime flags (-R) in practice
On this system, adding JACK realtime flags like `-R` wasn’t effective unless they were applied via **QjackCtl**.

- **Where**: QjackCtl → Setup → Settings → Advanced → **Server Prefix**
- **Example that worked**: `taskset -c 8 jackd -R -P90`

Note: users should be able to choose the CPU core(s) (the `taskset -c …` part), rather than hard-coding `8`.

Technical note: QjackCtl persists this in `~/.config/rncbc.org/QjackCtl.conf` under `[Settings]` preset keys like `<Preset>\\Server=...`.

### Planned feature: QjackCtl Prefix knob (non-root)
Add a knob `qjackctl_server_prefix_rt` that:
- Reads the active QjackCtl preset (via `DefPreset`) and current JACK server command.
- Previews the exact diff to `QjackCtl.conf`.
- Applies a minimal change:
  - ensure `-R` is present
  - ensure the command is prefixed with `taskset -c <corelist>` (corelist is user-provided)
  - (optionally) ensure `-P90` if the user wants
- Undo restores prior file contents via a user-scope transaction.

### Transaction model: user vs root
- Non-root knobs apply without pkexec and store transactions under `~/.local/state/audioknob-gui/transactions/...`.
- Root knobs apply via pkexec and store transactions under `/var/lib/audioknob-gui/transactions/...`.
- Mixed batches are split into two phases (non-root then root).

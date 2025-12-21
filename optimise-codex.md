# Optimisation notes for audioknob-gui

Goal: identify simplifications and streamlining opportunities without changing behavior.
This is a review-only document; no code changes proposed here are applied.

## Quick assessment
- The codebase is already small and mostly straightforward.
- The main complexity hot spots are `audioknob_gui/gui/app.py` and `audioknob_gui/worker/cli.py`.
- Most opportunities are about reducing duplication and centralizing rules so they do not drift.

## Low-risk, high-value simplifications
1) Centralize GUI state overrides for knobs
   - Today, override logic for QjackCtl/ PipeWire is repeated in:
     - `audioknob_gui/gui/app.py` (read + validate + display)
     - `audioknob_gui/worker/cli.py` (`_qjackctl_cpu_cores_override`, `_pipewire_*_override`, and repeated per-command overrides)
   - Suggestion: create a single helper module (e.g., `audioknob_gui/core/state.py`) with:
     - `load_state()` and `save_state()` (move from GUI)
     - `apply_overrides(knob: Knob, state: dict) -> Knob`
     - shared constants for allowed values (quantum/sample rate)
   - Benefit: fewer chances for divergent rules, smaller GUI + CLI files.

2) Deduplicate file line-append logic
   - `pam_limits_audio_group` and `sysctl_conf` share identical logic in `audioknob_gui/worker/cli.py`.
   - Suggestion: move to a helper like `audioknob_gui/core/textfile.py` or into `audioknob_gui/worker/ops.py`.
   - Benefit: reduces two large blocks to one and makes future knobs cheaper to add.

3) Extract effect-kind constants
   - Many string literals are used across GUI + worker (e.g., `sysfs_write`, `systemd_unit_toggle`, `user_service_mask`, `pipewire_restart`).
   - Suggestion: define constants (or an Enum) in `audioknob_gui/core/transaction.py` or `audioknob_gui/worker/ops.py`.
   - Benefit: avoids subtle bugs from typos and makes reset/restore code easier to read.

4) Consolidate command execution helpers
   - GUI runs many subprocess calls with similar error handling patterns.
   - Suggestion: introduce a small wrapper in `audioknob_gui/core/runner.py` for:
     - pkexec commands
     - JSON stdout parsing
     - consistent error messages
   - Benefit: less repeated try/except, more consistent failures, smaller GUI file.

5) Split `MainWindow._populate()` into smaller steps
   - `_populate()` is a long multi-purpose method (status computation, widget creation, wiring, config control setup).
   - Suggestion: break it into small helpers:
     - `_make_row_widgets()`
     - `_apply_row_status()`
     - `_apply_row_actions()`
     - `_apply_row_config()`
   - Benefit: reduces mental load and makes targeted changes safer.

## Medium-scope refactors (still safe if done carefully)
1) Create a data-driven knob action map
   - `audioknob_gui/gui/app.py` uses a long if/elif chain for knob IDs.
   - Suggestion: use a dict keyed by knob id with small handler objects, or a single map of lambdas/closures.
   - Benefit: less branching, easier to add new knobs without touching a huge method.

2) Normalize registry + state defaults into schemas
   - GUI state migrations and defaults are embedded in `load_state()`.
   - Suggestion: define a `StateSchema` dataclass with defaults + validation; serialize with `asdict`.
   - Benefit: fewer ad-hoc checks, easier to reason about new fields.

3) Reduce duplicate logic in reset/restore flows
   - `cmd_restore`, `cmd_reset_defaults`, and `cmd_restore_knob` all traverse backups + effects with similar logic.
   - Suggestion: create a single restore pipeline in `worker/ops.py` that takes a list of effects + backups and handles scope.
   - Benefit: fewer places to keep in sync, fewer edge-case differences.

4) Separate GUI-only vs. system-only logic
   - GUI currently knows about package manager operations and group changes.
   - Suggestion: move system operations to worker (even if user-scope), so GUI only calls worker commands.
   - Benefit: more consistent error handling and clearer separation of concerns.

## Smaller cleanups that reduce cognitive overhead
- Extract repeated lists into constants:
  - PipeWire quantum and sample rate values (currently duplicated in GUI + CLI).
  - Group names (`audio`, `realtime`, `pipewire`).
- Replace a few broad `except Exception: pass` with narrower exception handling where reasonable.
  - This avoids silent behavior changes during real errors and makes debugging simpler.

## Notes about risk
- The suggestions above are mostly structural and should not affect behavior if done carefully.
- The riskiest area is any change touching transaction reset logic; keep those changes fully covered by tests in `tests/`.

## Suggested order if you want to act on this
1) Introduce shared constants + state helper module, switch GUI/CLI to use it.
2) Extract small helpers in `worker/cli.py` for file edits + overrides.
3) Refactor GUI `_populate()` into sub-functions.
4) Consolidate reset/restore effect handling.

If you want, I can turn any of the above into concrete, minimal code changes with tests.

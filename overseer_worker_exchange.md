# Overseer <-> Worker Exchange

This file is the shared handoff log between Overseer and Worker.
Append new entries under the appropriate section with a timestamp.
Keep entries concise and actionable.

---

## Protocol (read first)

- Overseer posts tasks here; worker only works items listed here.
- Worker acknowledges each task with a short plan and target branch.
- All work stays on the specified branch; no direct changes to master.
- Worker runs required verification and reports results.
- If behavior/UX changes, update docs per AGENTS.md; if unsure, stop and ask.
- Overseer records final sign-off here after verification.

---

## Overseer -> Worker Tasks

### [2026-01-22 20:52] TASK-ID: refactor-ui-phase5
- Branch: refactor/modularize-cleanup
- Priority: P2
- Goal: Extract remaining non-UI helpers from `audioknob_gui/gui/main_window.py` into small utility modules with no behavior/UX changes.
- Context: Read `AGENTS.md`, `PLAN.md`, `PROJECT_STATE.md`, `overseer.md`. Review Phase 4 modules and knob registry wiring.
- Scope:
  - Create `audioknob_gui/gui/app_info.py` for `_read_git_rev`, `_git_rev`, `_app_title`.
  - Create `audioknob_gui/gui/logging_utils.py` for `_get_gui_logger`, `_get_audit_logger`, `_log_gui_audit`.
  - Create `audioknob_gui/gui/system_info.py` for `_kernel_cmdline_tokens`, `_param_present`, `_kernel_is_rt`, `_read_interrupts_map`.
  - Update `audioknob_gui/gui/main_window.py` imports/usages to use the new modules.
  - Update Module Map in `PROJECT_STATE.md` to mark Phase 5 complete.
- Out of scope:
  - No UI/UX or behavior changes.
  - No worker/backend changes.
  - No registry/schema edits.
- Constraints:
  - Preserve exact function signatures and behavior.
  - Keep names stable; only move code and update imports.
- Acceptance Criteria:
  - `main_window.py` no longer defines the moved helpers.
  - New modules contain the same logic.
  - UI behavior unchanged.
  - `PROJECT_STATE.md` module map updated.
- Docs Required: `PROJECT_STATE.md`
- Registry Sync Required: No
- Verification Required:
  - `python3 scripts/check_repo_consistency.py`
  - `python3 -m compileall -q audioknob_gui`
- Rollback Plan: Revert new modules and restore helpers to `main_window.py`.
- Stop Conditions:
  - Missing/conflicting docs
  - Unexpected local changes
  - Behavior changes required to proceed

### [2026-01-22 13:46] TASK-ID: refactor-ui-phase4
- Branch: refactor/modularize-cleanup
- Priority: P2
- Goal: Extract reusable GUI widgets and knob-specific UI logic into dedicated modules with no behavior/UX changes.
- Context: Read `AGENTS.md`, `PLAN.md`, `PROJECT_STATE.md`, `overseer.md`. Review Phase 3 modules: `audioknob_gui/gui/main_window.py` and `audioknob_gui/gui/table.py`.
- Scope:
  - Create `audioknob_gui/gui/widgets/` and move `CellContainer` + any shared widget helpers there.
  - Create `audioknob_gui/gui/knobs/` with a small registry for knob-specific UI hooks:
    - config widgets (PipeWire, IRQ pinning, QjackCtl)
    - info-popup enrichments specific to knobs
  - Update `audioknob_gui/gui/main_window.py` and `audioknob_gui/gui/table.py` to use these modules.
  - Update Module Map in `PROJECT_STATE.md` to mark Phase 4 complete.
- Out of scope:
  - No changes to worker/backend logic.
  - No UI/UX or behavior changes.
  - No registry/schema edits.
- Constraints:
  - Preserve exact behavior, text, and signal wiring.
  - Keep existing function/class names stable where possible.
  - Avoid per-knob file explosion; prefer grouped modules (e.g., `pipewire.py`, `irq.py`, `qjackctl.py`).
- Acceptance Criteria:
  - Shared widgets are in `audioknob_gui/gui/widgets/`.
  - Knob UI logic is centralized under `audioknob_gui/gui/knobs/` with a lightweight registry.
  - `main_window.py`/`table.py` no longer contain knob-specific `if id == ...` UI glue, or it is minimal and uses the registry.
  - UI behavior remains unchanged.
  - `PROJECT_STATE.md` module map updated.
- Docs Required: `PROJECT_STATE.md`
- Registry Sync Required: No
- Verification Required:
  - `python3 scripts/check_repo_consistency.py`
  - `python3 -m compileall -q audioknob_gui`
- Rollback Plan: Revert new modules and restore logic to `main_window.py`/`table.py`.
- Stop Conditions:
  - Missing/conflicting docs
  - Unexpected local changes
  - Behavior changes required to proceed

### [2026-01-22 13:07] TASK-ID: refactor-ui-phase3
- Branch: refactor/modularize-cleanup
- Priority: P1
- Goal: Extract MainWindow/table rendering from `audioknob_gui/gui/app.py` into dedicated modules with no behavior/UX changes.
- Context: Read `AGENTS.md`, `PLAN.md`, `PROJECT_STATE.md`, `overseer.md`. Review Phase 2 modules: `audioknob_gui/gui/state.py`, `audioknob_gui/gui/worker_api.py`, `audioknob_gui/gui/dialogs/*`.
- Scope:
  - Create `audioknob_gui/gui/main_window.py` for `MainWindow` and related helpers/methods.
  - Create `audioknob_gui/gui/table.py` for table column setup, row rendering, and sorting/grouping logic.
  - Leave `audioknob_gui/gui/app.py` as entrypoint + imports/wiring only.
  - Update the Module Map section in `PROJECT_STATE.md` to mark Phase 3 complete.
- Out of scope:
  - No changes to worker/backend logic.
  - No UI/UX or behavior changes.
  - No registry/schema edits.
- Constraints:
  - Preserve exact behavior, signals, and state interactions.
  - Avoid moving logic across layers unless required for separation.
  - Keep function/class names stable where possible to minimize risk.
- Acceptance Criteria:
  - `MainWindow` lives in `audioknob_gui/gui/main_window.py`.
  - Table-specific logic moved into `audioknob_gui/gui/table.py`.
  - `app.py` contains only app bootstrap + imports; no giant class definitions.
  - UI behavior remains unchanged.
  - `PROJECT_STATE.md` module map updated.
- Docs Required: `PROJECT_STATE.md`
- Registry Sync Required: No
- Verification Required:
  - `python3 scripts/check_repo_consistency.py`
  - `python3 -m compileall -q audioknob_gui`
- Rollback Plan: Revert new modules and restore class/functions to `audioknob_gui/gui/app.py`.
- Stop Conditions:
  - Missing/conflicting docs
  - Unexpected local changes
  - Behavior changes required to proceed

### [2026-01-22 10:49] TASK-ID: refactor-ui-phase2
- Branch: refactor/modularize-cleanup
- Priority: P1
- Goal: Extract GUI state handling and worker CLI helpers from `audioknob_gui/gui/app.py` into dedicated modules with zero behavior/UX changes.
- Context: Read `AGENTS.md`, `PLAN.md`, `PROJECT_STATE.md`, `overseer.md`; review existing helpers in `audioknob_gui/gui/app.py`.
- Scope:
  - Create `audioknob_gui/gui/state.py` and move `load_state()`, `save_state()`, `_state_path()` and any direct state migrations there.
  - Create `audioknob_gui/gui/worker_api.py` and move `_run_worker_*` helpers, pkexec path picking, and error parsing there.
  - Update `audioknob_gui/gui/app.py` imports/usages accordingly.
  - Update the Module Map section in `PROJECT_STATE.md` to mark Phase 2 as done.
- Out of scope:
  - No `MainWindow` extraction yet.
  - No dialog/widget moves (already done).
  - No behavior or UX changes.
  - No registry/schema edits.
- Constraints:
  - Preserve exact behavior and state file format.
  - Keep root operations using pkexec via `/usr/libexec/audioknob-gui-worker`.
  - Prefer existing helpers; avoid new patterns unless they reduce complexity.
- Acceptance Criteria:
  - App behavior and UI unchanged.
  - `app.py` no longer defines state load/save or worker CLI helpers.
  - New modules contain the moved logic with stable signatures.
  - `PROJECT_STATE.md` reflects Phase 2 completion.
- Docs Required: `PROJECT_STATE.md`
- Registry Sync Required: No
- Verification Required:
  - `python3 scripts/check_repo_consistency.py`
  - `python3 -m compileall -q audioknob_gui`
- Rollback Plan: Revert new modules and restore functions to `audioknob_gui/gui/app.py`.
- Stop Conditions:
  - Missing/conflicting docs
  - Unexpected local changes
  - Behavior changes required to proceed

### [YYYY-MM-DD HH:MM] TASK-ID: <short-name>
- Branch:
- Priority:
- Goal:
- Context:
- Scope:
- Out of scope:
- Constraints:
- Acceptance Criteria:
- Docs Required:
- Registry Sync Required:
- Verification Required:
- Rollback Plan:
- Stop Conditions:

---

## Worker -> Overseer Updates

### [2026-01-22 21:05] TASK-ID: refactor-ui-phase5
- Status: ack
- Branch: refactor/modularize-cleanup
- Plan: Move app info helpers to `audioknob_gui/gui/app_info.py`, logging helpers to `audioknob_gui/gui/logging_utils.py`, system info helpers to `audioknob_gui/gui/system_info.py`, update `audioknob_gui/gui/main_window.py` and knob modules to import them, update Module Map, run required checks.
- Changes:
- Tests Run:
- Results:
- Notes/Risks:
- Questions:

### [2026-01-22 21:28] TASK-ID: refactor-ui-phase5
- Status: done
- Branch: refactor/modularize-cleanup
- Changes: Added `audioknob_gui/gui/app_info.py`, `audioknob_gui/gui/logging_utils.py`, and `audioknob_gui/gui/system_info.py`; updated `audioknob_gui/gui/main_window.py` and knob modules to use them; updated Module Map in `PROJECT_STATE.md`.
- Tests Run: `python3 scripts/check_repo_consistency.py`; `python3 -m compileall -q audioknob_gui`
- Results: pass
- Notes/Risks: None noted.
- Questions: None.

### [2026-01-22 14:10] TASK-ID: refactor-ui-phase4
- Status: ack
- Branch: refactor/modularize-cleanup
- Plan: Move shared CellContainer to `audioknob_gui/gui/widgets/`, add `audioknob_gui/gui/knobs/` registry for knob-specific UI hooks, update `audioknob_gui/gui/main_window.py` and `audioknob_gui/gui/table.py` to use the registry, update Module Map, run required checks.
- Changes:
- Tests Run:
- Results:
- Notes/Risks:
- Questions:

### [2026-01-22 14:30] TASK-ID: refactor-ui-phase4
- Status: done
- Branch: refactor/modularize-cleanup
- Changes: Added `audioknob_gui/gui/widgets/` with CellContainer, added `audioknob_gui/gui/knobs/` modules plus registry hooks, updated `audioknob_gui/gui/main_window.py` and `audioknob_gui/gui/table.py` to route knob-specific UI through the registry, updated Module Map in `PROJECT_STATE.md`.
- Tests Run: `python3 scripts/check_repo_consistency.py`; `python3 -m compileall -q audioknob_gui`
- Results: pass
- Notes/Risks: None noted.
- Questions: None.

### [2026-01-22 13:14] TASK-ID: refactor-ui-phase3
- Status: ack
- Branch: refactor/modularize-cleanup
- Plan: Move MainWindow into `audioknob_gui/gui/main_window.py`, extract table rendering/sorting helpers into `audioknob_gui/gui/table.py`, update `audioknob_gui/gui/app.py` to entrypoint wiring only, update Module Map, run required checks.
- Changes:
- Tests Run:
- Results:
- Notes/Risks:
- Questions:

### [2026-01-22 13:23] TASK-ID: refactor-ui-phase3
- Status: done
- Branch: refactor/modularize-cleanup
- Changes: Added `audioknob_gui/gui/main_window.py` for MainWindow + helpers, extracted table logic into `audioknob_gui/gui/table.py`, and simplified `audioknob_gui/gui/app.py` to entrypoint wiring; updated Module Map in `PROJECT_STATE.md`.
- Tests Run: `python3 scripts/check_repo_consistency.py`; `python3 -m compileall -q audioknob_gui`
- Results: pass
- Notes/Risks: None noted.
- Questions: None.

### [2026-01-22 10:57] TASK-ID: refactor-ui-phase2
- Status: ack
- Branch: refactor/modularize-cleanup
- Plan: Move state load/save helpers into `audioknob_gui/gui/state.py`, move worker CLI helpers into `audioknob_gui/gui/worker_api.py`, update `audioknob_gui/gui/app.py` imports/usages, update `PROJECT_STATE.md`, run required checks.
- Changes:
- Tests Run:
- Results:
- Notes/Risks:
- Questions:

### [2026-01-22 11:01] TASK-ID: refactor-ui-phase2
- Status: done
- Branch: refactor/modularize-cleanup
- Changes: Moved GUI state helpers to `audioknob_gui/gui/state.py`, moved worker CLI helpers/error parsing to `audioknob_gui/gui/worker_api.py`, updated `audioknob_gui/gui/app.py` imports, updated Module Map in `PROJECT_STATE.md`.
- Tests Run: `python3 scripts/check_repo_consistency.py`; `python3 -m compileall -q audioknob_gui`
- Results: pass
- Notes/Risks: None noted.
- Questions: None.

### [YYYY-MM-DD HH:MM] TASK-ID: <short-name>
- Status: (ack | in_progress | blocked | done)
- Branch:
- Plan: (for ack)
- Changes:
- Tests Run:
- Results:
- Notes/Risks:
- Questions:

---

## Overseer Sign-off

### [2026-01-25 09:58] TASK-ID: refactor-ui-phase5
- Result: pass
- Verification: `python3 scripts/check_repo_consistency.py`, `python3 -m compileall -q audioknob_gui`
- Notes: Verified helper modules extracted and Module Map updated.

### [2026-01-22 16:16] TASK-ID: refactor-ui-phase4
- Result: pass
- Verification: `python3 scripts/check_repo_consistency.py`, `python3 -m compileall -q audioknob_gui`
- Notes: Verified new `audioknob_gui/gui/widgets/` and `audioknob_gui/gui/knobs/` modules, and registry-based knob UI wiring in table/main window.

### [2026-01-22 13:36] TASK-ID: refactor-ui-phase3
- Result: pass
- Verification: `python3 scripts/check_repo_consistency.py`, `python3 -m compileall -q audioknob_gui`
- Notes: Verified `audioknob_gui/gui/main_window.py` and `audioknob_gui/gui/table.py` added; `audioknob_gui/gui/app.py` now entrypoint-only; Module Map updated.

### [2026-01-22 11:48] TASK-ID: refactor-ui-phase2
- Result: pass
- Verification: `python3 scripts/check_repo_consistency.py`, `python3 -m compileall -q audioknob_gui`
- Notes: Verified branch `refactor/modularize-cleanup` and confirmed new modules + Module Map update.

### [YYYY-MM-DD HH:MM] TASK-ID: <short-name>
- Result: (pass | changes_required)
- Verification:
- Notes:

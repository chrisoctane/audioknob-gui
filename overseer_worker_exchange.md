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

### [2026-01-26 14:44] TASK-ID: refactor-ui-phase8
- Branch: refactor/modularize-cleanup
- Priority: P2
- Goal: Extract group/package requirement checks and install flows from `audioknob_gui/gui/main_window.py` into `audioknob_gui/gui/requirements.py` with no behavior/UX changes.
- Context: Read `AGENTS.md`, `PLAN.md`, `PROJECT_STATE.md`, `overseer.md`. Review recent Phase 6/7 modules.
- Scope:
  - Create `audioknob_gui/gui/requirements.py`.
  - Move group gating helpers: `_knob_group_ok`, group-join/leave flows, group status updates.
  - Move package requirement helpers: `_knob_commands_ok`, `_knob_missing_commands`, install handling + audit logging.
  - Update `main_window.py` to call into the new module with thin wrappers.
  - Update Module Map in `PROJECT_STATE.md` to mark Phase 8 complete.
- Out of scope:
  - No UI/UX changes.
  - No worker/backend changes.
  - No registry/schema edits.
- Constraints:
  - Preserve exact behavior, logging, and error handling.
  - Keep method signatures stable where possible; wrappers are fine.
- Acceptance Criteria:
  - Group and package gating behave identically.
  - Install button and join/leave groups flows unchanged.
  - `main_window.py` no longer contains the moved logic.
  - `PROJECT_STATE.md` module map updated.
- Docs Required: `PROJECT_STATE.md`
- Registry Sync Required: No
- Verification Required:
  - `python3 scripts/check_repo_consistency.py`
  - `python3 -m compileall -q audioknob_gui`
- Rollback Plan: Revert `requirements.py` and restore methods to `main_window.py`.
- Stop Conditions:
  - Missing/conflicting docs
  - Unexpected local changes
  - Behavior changes required to proceed

### [2026-01-25 14:05] TASK-ID: refactor-ui-phase7
- Branch: refactor/modularize-cleanup
- Priority: P2
- Goal: Extract baseline/status/scan helpers from `audioknob_gui/gui/main_window.py` into `audioknob_gui/gui/status.py` with no behavior/UX changes.
- Context: Read `AGENTS.md`, `PLAN.md`, `PROJECT_STATE.md`, `overseer.md`. Review Phase 6 actions module.
- Scope:
  - Create `audioknob_gui/gui/status.py` for baseline, status refresh, live checks, and CLI status dialog helpers.
  - Move baseline/state/status helpers out of `main_window.py` and keep thin wrappers.
  - Update Module Map in `PROJECT_STATE.md` to mark Phase 7 complete.
- Out of scope:
  - No UI/UX changes.
  - No worker/backend changes.
  - No registry/schema edits.
- Constraints:
  - Preserve exact behavior, logging, and error handling.
  - Keep method signatures stable; use thin wrappers in `MainWindow` if needed.
- Acceptance Criteria:
  - Baseline capture/import/export and status refresh behave identically.
  - `main_window.py` no longer contains moved status/baseline logic.
  - `PROJECT_STATE.md` module map updated.
- Docs Required: `PROJECT_STATE.md`
- Registry Sync Required: No
- Verification Required:
  - `python3 scripts/check_repo_consistency.py`
  - `python3 -m compileall -q audioknob_gui`
- Rollback Plan: Revert `status.py` and restore methods to `main_window.py`.
- Stop Conditions:
  - Missing/conflicting docs
  - Unexpected local changes
  - Behavior changes required to proceed

### [2026-01-25 12:48] TASK-ID: refactor-ui-phase6
- Branch: refactor/modularize-cleanup
- Priority: P2
- Goal: Extract action/queue/apply/reset logic from `audioknob_gui/gui/main_window.py` into `audioknob_gui/gui/actions.py` with no behavior/UX changes.
- Context: Read `AGENTS.md`, `PLAN.md`, `PROJECT_STATE.md`, `overseer.md`. Review recent refactor modules and Phase 5 helpers.
- Scope:
  - Create `audioknob_gui/gui/actions.py` with queue/apply/reset/force-reset helpers.
  - Move these methods (and any tightly-coupled helpers) out of `main_window.py`:
    - `_on_apply_knob`, `_on_queue_knob`, `_run_knob_task`, `_on_knob_task_finished`
    - `_restore_knob_internal`, `_restore_knob`, `_run_force_reset`, `_run_force_reset_many`
    - Reset All flow helpers (`_reset_defaults` / task worker + completion handler)
  - Update `main_window.py` to call the new module functions.
  - Update Module Map in `PROJECT_STATE.md` to mark Phase 6 complete.
- Out of scope:
  - No UI/UX changes.
  - No worker/backend changes.
  - No registry/schema edits.
- Constraints:
  - Preserve exact behavior, logging, and error handling.
  - Keep method signatures stable where possible; use thin wrappers in `MainWindow` if needed.
- Acceptance Criteria:
  - Queue/apply/reset flows behave identically.
  - `main_window.py` no longer contains the moved action logic.
  - `PROJECT_STATE.md` module map updated.
- Docs Required: `PROJECT_STATE.md`
- Registry Sync Required: No
- Verification Required:
  - `python3 scripts/check_repo_consistency.py`
  - `python3 -m compileall -q audioknob_gui`
- Rollback Plan: Revert `actions.py` and restore methods to `main_window.py`.
- Stop Conditions:
  - Missing/conflicting docs
  - Unexpected local changes
  - Behavior changes required to proceed

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

### [2026-01-26 14:46] TASK-ID: refactor-ui-phase8
- Status: ack
- Branch: refactor/modularize-cleanup
- Plan: Add `audioknob_gui/gui/requirements.py` for group/package requirement checks and install flows, move related helpers from `audioknob_gui/gui/main_window.py` with thin wrappers, update Module Map, run required checks.
- Changes:
- Tests Run:
- Results:
- Notes/Risks:
- Questions:

### [2026-01-26 14:51] TASK-ID: refactor-ui-phase8
- Status: done
- Branch: refactor/modularize-cleanup
- Changes: Added `audioknob_gui/gui/requirements.py` for group/package checks and install flows; moved group/package helpers and join/leave/install flows out of `audioknob_gui/gui/main_window.py` with thin wrappers; updated Module Map in `PROJECT_STATE.md`.
- Tests Run: `python3 scripts/check_repo_consistency.py`; `python3 -m compileall -q audioknob_gui`
- Results: pass
- Notes/Risks: None noted.
- Questions: None.

### [2026-01-25 14:08] TASK-ID: refactor-ui-phase7
- Status: ack
- Branch: refactor/modularize-cleanup
- Plan: Add `audioknob_gui/gui/status.py` for baseline/status/scan helpers, move related methods out of `audioknob_gui/gui/main_window.py`, update Module Map, run required checks.
- Changes:
- Tests Run:
- Results:
- Notes/Risks:
- Questions:

### [2026-01-25 14:32] TASK-ID: refactor-ui-phase7
- Status: done
- Branch: refactor/modularize-cleanup
- Changes: Added `audioknob_gui/gui/status.py` and moved baseline/status/scan logic out of `audioknob_gui/gui/main_window.py` with thin wrappers; updated Module Map in `PROJECT_STATE.md`.
- Tests Run: `python3 scripts/check_repo_consistency.py`; `python3 -m compileall -q audioknob_gui`
- Results: pass
- Notes/Risks: None noted.
- Questions: None.

### [2026-01-25 13:12] TASK-ID: refactor-ui-phase6
- Status: ack
- Branch: refactor/modularize-cleanup
- Plan: Add `audioknob_gui/gui/actions.py` for queue/apply/reset/force-reset helpers, move listed methods from `audioknob_gui/gui/main_window.py` into it, update Module Map, run required checks.
- Changes:
- Tests Run:
- Results:
- Notes/Risks:
- Questions:

### [2026-01-25 13:40] TASK-ID: refactor-ui-phase6
- Status: done
- Branch: refactor/modularize-cleanup
- Changes: Added `audioknob_gui/gui/actions.py` and moved queue/apply/reset/force-reset/reset-all logic out of `audioknob_gui/gui/main_window.py`; updated Module Map in `PROJECT_STATE.md`.
- Tests Run: `python3 scripts/check_repo_consistency.py`; `python3 -m compileall -q audioknob_gui`
- Results: pass
- Notes/Risks: None noted.
- Questions: None.

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

### [2026-01-26 15:21] TASK-ID: refactor-ui-phase8
- Result: pass
- Verification: `python3 scripts/check_repo_consistency.py`, `python3 -m compileall -q audioknob_gui`
- Notes: Verified `audioknob_gui/gui/requirements.py` extraction and Module Map update.

### [2026-01-26 11:20] TASK-ID: refactor-ui-phase7
- Result: pass
- Verification: `python3 scripts/check_repo_consistency.py`, `python3 -m compileall -q audioknob_gui`
- Notes: Verified `audioknob_gui/gui/status.py` extraction and Module Map update.

### [2026-01-26 11:20] TASK-ID: refactor-ui-phase6
- Result: pass
- Verification: `python3 scripts/check_repo_consistency.py`, `python3 -m compileall -q audioknob_gui`
- Notes: Verified `audioknob_gui/gui/actions.py` extraction and MainWindow wrappers.

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

# AGENTS.md — Agent Workflow Rules (audioknob-gui)

This file defines the required workflow for any AI agent working in this repo.
It is for agent control only and does not change public docs.

## Sources of truth
- Behavior: `audioknob_gui/**` (runtime code) is the source of truth.
- UX/process: `PLAN.md` is the user-facing contract.
- Architecture/constraints: `PROJECT_STATE.md` is the technical contract.
- Registry: `config/registry*.json` is canonical; `audioknob_gui/data/registry*.json` must be synced.

## Required reading (always)
- `AGENTS.md` (this file) — authoritative workflow rules.
- `PLAN.md` when touching UX/user workflows.
- `PROJECT_STATE.md` when touching behavior/architecture or release processes.
- `docs/KNOB_INTERACTIONS.md` before any IRQ/kernel/RT/power/CPU isolation changes.
- `docs/knobs.md` before adding or implementing new knobs.
- `CHANGELOG.md` for release work (must be updated per release).
- `overseer.md` only when acting in an overseer/audit role.

If any doc is stale or conflicts with code, update it before proceeding.

## Hard guardrails (no exceptions without explicit user approval)
- No background daemon/service, no auto-apply workflows, no hidden state machines.
- No silent system changes; every change must be user-initiated and visible in UI.
- Root operations must use pkexec via `/usr/libexec/audioknob-gui-worker`.
- If status cannot be proven, report "unknown"/not applied (conservative).

## Optimization mandate (always on)
- Keep the codebase minimal: remove dead code, avoid duplication, and reuse helpers.
- Prefer refactors that reduce LOC/complexity without changing behavior.
- If a refactor is broad or risky, ask before doing it.
- Treat improvement opportunities as valid work, even if discovered retroactively.
- Always consider the change in the context of nearby code and existing patterns.
- Optimize for clarity and consistency first; performance changes should be
  purposeful and behavior-preserving unless explicitly requested.

## Start-of-session checklist (before edits)
1) Read `AGENTS.md` and the docs required for the task (see Required reading).
2) Read `PLAN.md` and `PROJECT_STATE.md` if making behavior/UX changes.
3) Locate the relevant code path; do not invent new flows.
4) Scan for existing helpers before adding new logic.
5) If you see unexpected local changes, STOP and ask the user.

## Change rules (drift prevention)
- Any behavior or UX change MUST update `PROJECT_STATE.md`.
- Any user workflow change MUST update `PLAN.md`.
- Any registry/schema edit MUST sync:
  - `config/registry.json` → `audioknob_gui/data/registry.json`
  - `config/registry.schema.json` → `audioknob_gui/data/registry.schema.json`
- Any new knob or behavior change MUST update `docs/KNOB_INTERACTIONS.md` with
  conflicts, dependencies, or blockers.
- New knob kinds require preview/apply/status support in worker.
- Every knob must have a system_profile location entry (per-knob path/target map).
- For knobs that share a file (GRUB cmdline, sysctl.d, limits.d, pipewire.conf.d, udev rules, etc.):
  - Apply must be additive (append or edit only the knob’s lines/param).
  - Reset must be surgical (remove only the knob’s lines/param), never restore the full file,
    unless the knob owns the entire file by design.
  - If multiple knobs touch the same file, verify a reset of one does not revert the others.
- Prefer small, reversible changes; refactor when it makes the codebase cleaner
  or more consistent with existing patterns.
- Match existing style and structure; do not introduce new patterns unless they
  simplify the codebase and reduce future drift.
- If you spot safe optimization or deduplication, implement it in the same change.

## Research gate (complex changes)
Before making changes that affect IRQs, kernel cmdline, RT scheduling, power
management, or CPU isolation:
- Read `docs/KNOB_INTERACTIONS.md` first and align changes with the conflict map.
- Add short research notes with sources to `docs/KNOB_INTERACTIONS.md`
  (or a linked doc) if behavior is non-obvious or distro-specific.
- If sources conflict or behavior is unclear, STOP and ask the user.

## Definition of done (minimum)
- Consistency gate passes:
  - `python3 scripts/check_repo_consistency.py`
  - `python3 -m compileall -q audioknob_gui`
- Docs updated when required (per rules above).
- No unaddressed TODOs or debug prints left in code.

## Stop conditions (ask the user before proceeding)
- Missing or unreadable referenced files.
- Conflicting instructions between docs or system constraints.
- A change would violate guardrails or require new UX not in docs.

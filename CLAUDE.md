# CLAUDE.md — Claude Code Project Instructions

This file is automatically loaded by Claude Code at session start.

## Mandatory first step

Read `AGENTS.md` before making any changes. It defines the authoritative workflow
rules, guardrails, scope controls, and quality gate requirements for this repo.

## Quick reference

- **Agent rules**: `AGENTS.md` (sources of truth, hard guardrails, change rules, stop conditions)
- **User-facing contract**: `PLAN.md` (UX, install, workflows)
- **Technical contract**: `PROJECT_STATE.md` (architecture, decisions, operator contract)
- **Conflict map**: `docs/KNOB_INTERACTIONS.md` (knob conflicts, dependencies, blockers)
- **Quality gates**: `docs/internal/audit/QUALITY_GATE.md` (G0–G3 gate definitions)
- **Scope control**: `docs/internal/audit/STABILIZATION_STATE.md` (allowed paths, file-count cap)
- **Consistency enforcer**: `python3 scripts/check_repo_consistency.py`
- **Quality gate runner**: `python3 scripts/run_quality_gate.py --gate <g1|g2|g3|ci>`

## Key constraints (from AGENTS.md)

- No background daemons, auto-apply, or hidden state machines.
- Every system change must be user-initiated and visible in UI.
- Root operations use pkexec via `/usr/libexec/audioknob-gui-worker` only.
- If status cannot be proven, report "unknown" / not applied (conservative).
- Any behavior change must update `PROJECT_STATE.md`.
- Any user workflow change must update `PLAN.md`.
- Registry edits must sync `config/` to `audioknob_gui/data/`.
- Run `python3 scripts/check_repo_consistency.py` before marking work complete.

## Build and test

```bash
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install -e .[dev]
python3 -m pytest -q                              # full test suite
python3 scripts/check_repo_consistency.py          # G1 consistency
python3 scripts/run_quality_gate.py --gate g1      # change gate
python3 scripts/run_quality_gate.py --gate g3 --release-version vX.Y.Z  # release gate
```

## Packaging

```bash
./packaging/opensuse/build-rpm.sh    # RPM for openSUSE Tumbleweed
./packaging/debian/build-deb.sh      # DEB for Debian/Ubuntu
```

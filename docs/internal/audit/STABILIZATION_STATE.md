# Stabilization State

Purpose:
- Keep remediation work bounded, reproducible, and non-expansive.
- Prevent open-ended audit/fix loops and uncontrolled file churn.
- Act as a persistent guardrail for AI agents: scope-limit every session
  so agents cannot silently expand beyond the approved work area.

Mode: ON
Batch ID: STAB-MAINT-001
Objective: General maintenance — bug fixes, documentation updates, refactoring, and incremental improvements. Packaging and CI workflow changes require explicit user approval.
Max changed files: 80

Allowed paths:
- `AGENTS.md`
- `CLAUDE.md`
- `PLAN.md`
- `PROJECT_STATE.md`
- `CHANGELOG.md`
- `README.md`
- `pyproject.toml`
- `audioknob_gui/__init__.py`
- `audioknob_gui/knob_ids.py`
- `audioknob_gui/registry.py`
- `audioknob_gui/gui/`
- `audioknob_gui/worker/`
- `audioknob_gui/testing/`
- `audioknob_gui/data/registry.json`
- `audioknob_gui/data/registry.schema.json`
- `config/registry.json`
- `config/registry.schema.json`
- `tests/`
- `docs/`
- `scripts/`
- `packaging/opensuse/build-rpm.sh`
- `packaging/opensuse/README.md`

Excluded (require explicit user approval to modify):
- `packaging/` (build scripts, spec files, debian control, desktop entries)
- `.github/workflows/` (CI/CD pipelines)
- `polkit/` (privilege escalation policy)
- `bin/` (entry point scripts)

Approved exception for this batch:
- 2026-03-17: user approved changes to `packaging/opensuse/build-rpm.sh` and `packaging/opensuse/README.md`
  to ensure local RPM builds include the current tracked working tree for launcher testing.

Batch protocol:
1. Use read-only audit -> approved-fix batch -> read-only verification (no mixed passes).
2. Fix only approved finding IDs for the active batch.
3. If a new issue is discovered mid-batch, log it and defer unless it blocks current batch exit criteria.
4. Keep edits within allowlisted paths and file-count cap.
5. Waive only with explicit commit tag `stabilization-waiver:` and user approval.

## Batch history

### STAB-DEV-001 (closed)
- Objective: Dev-tab expansion for advanced RT/audio tuning knobs and config paths.
- Outcome: All dev-tab knobs implemented; merged as v0.7.10.
- Max changed files: 200

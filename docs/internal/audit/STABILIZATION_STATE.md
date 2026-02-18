# Stabilization State

Purpose:
- Keep remediation work bounded, reproducible, and non-expansive.
- Prevent open-ended audit/fix loops and uncontrolled file churn.

Mode: ON
Batch ID: STAB-DEV-001
Objective: Dev-tab expansion for advanced RT/audio tuning knobs and config paths.
Max changed files: 200

Allowed paths:
- `AGENTS.md`
- `PLAN.md`
- `PROJECT_STATE.md`
- `docs/KNOB_INTERACTIONS.md`
- `docs/internal/audit/QUALITY_GATE.md`
- `docs/internal/audit/STABILIZATION_STATE.md`
- `docs/internal/audit/MULTI_AGENT_CONTROL_SYSTEM.md`
- `docs/internal/audit/releases/`
- `CHANGELOG.md`
- `pyproject.toml`
- `audioknob_gui/gui/main_window.py`
- `audioknob_gui/gui/simple_mode.py`
- `audioknob_gui/gui/app_info.py`
- `audioknob_gui/gui/table.py`
- `audioknob_gui/gui/state.py`
- `audioknob_gui/gui/status.py`
- `audioknob_gui/gui/conflicts.py`
- `audioknob_gui/gui/dialogs/pipewire.py`
- `audioknob_gui/gui/knobs/irq.py`
- `audioknob_gui/gui/knobs/kernel.py`
- `audioknob_gui/gui/knobs/pipewire.py`
- `audioknob_gui/gui/knobs/qjackctl.py`
- `audioknob_gui/gui/knobs/registry.py`
- `audioknob_gui/worker/cli.py`
- `audioknob_gui/worker/ops.py`
- `audioknob_gui/data/registry.json`
- `config/registry.json`
- `docs/KNOB_SYSTEM_AUDIT_MAP.md`
- `docs/knobs.md`
- `audioknob_gui/__init__.py`
- `scripts/check_repo_consistency.py`
- `tests/test_gate_scripts.py`
- `tests/test_simple_mode.py`
- `tests/test_cli_commands.py`
- `tests/test_conflicts.py`
- `tests/test_core_plan_linking.py`
- `tests/test_kernel_cmdline.py`
- `tests/test_pipewire_config.py`
- `tests/test_status_baseline.py`
- `tests/test_sysfs_status.py`

Batch protocol:
1. Use read-only audit -> approved-fix batch -> read-only verification (no mixed passes).
2. Fix only approved finding IDs for the active batch.
3. If a new issue is discovered mid-batch, log it and defer unless it blocks current batch exit criteria.
4. Keep edits within allowlisted paths and file-count cap.
5. Waive only with explicit commit tag `stabilization-waiver:` and user approval.

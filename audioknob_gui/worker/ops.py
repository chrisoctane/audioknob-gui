from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from audioknob_gui.core.diffutil import unified_diff
from audioknob_gui.core.runner import run


@dataclass(frozen=True)
class FileChange:
    path: str
    action: str  # create|modify|delete
    diff: str


@dataclass(frozen=True)
class PreviewItem:
    knob_id: str
    title: str
    description: str
    requires_root: bool
    requires_reboot: bool
    risk_level: str
    action: str  # apply|restore
    file_changes: list[FileChange]
    would_run: list[list[str]]
    would_write: list[dict[str, Any]]
    notes: list[str]


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _pam_limits_preview(params: dict[str, Any]) -> list[FileChange]:
    path = str(params["path"])
    wanted_lines = [str(x) for x in params.get("lines", [])]

    before = _read_text(path)
    before_lines = before.splitlines()
    after_lines = list(before_lines)

    for line in wanted_lines:
        if line not in after_lines:
            after_lines.append(line)

    after = "\n".join(after_lines).rstrip("\n") + "\n"

    action = "create" if (before == "" and not Path(path).exists()) else "modify"
    return [FileChange(path=path, action=action, diff=unified_diff(path, before, after))]


def _systemd_unit_preview(params: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    unit = str(params["unit"])
    action = str(params.get("action", ""))
    if action == "disable_now":
        return [["systemctl", "disable", "--now", unit]], []
    return [], [f"Unsupported systemd action: {action}"]


def _sysfs_glob_preview(params: dict[str, Any]) -> list[dict[str, Any]]:
    g = str(params["glob"])
    value = str(params["value"])
    matches = sorted(glob.glob(g))
    return [{"path": p, "value": value} for p in matches]


def preview(knob: Any, action: str) -> PreviewItem:
    file_changes: list[FileChange] = []
    would_run: list[list[str]] = []
    would_write: list[dict[str, Any]] = []
    notes: list[str] = []

    if knob.impl is None:
        notes.append("No implementation for this knob yet.")
        return PreviewItem(
            knob_id=knob.id,
            title=knob.title,
            description=knob.description,
            requires_root=bool(knob.requires_root),
            requires_reboot=bool(knob.requires_reboot),
            risk_level=str(knob.risk_level),
            action=action,
            file_changes=[],
            would_run=[],
            would_write=[],
            notes=notes,
        )

    kind = knob.impl.kind
    params = knob.impl.params

    if action == "apply":
        if kind == "pam_limits_audio_group":
            file_changes.extend(_pam_limits_preview(params))
        elif kind == "systemd_unit_toggle":
            cmds, more_notes = _systemd_unit_preview(params)
            would_run.extend(cmds)
            notes.extend(more_notes)
        elif kind == "sysfs_glob_kv":
            would_write.extend(_sysfs_glob_preview(params))
        elif kind == "read_only":
            notes.append("Read-only knob; nothing to apply.")
        else:
            notes.append(f"Unsupported kind: {kind}")

    elif action == "restore":
        notes.append("Restore is transaction-based and uses txid (handled by worker restore command).")
    else:
        notes.append(f"Unknown action: {action}")

    return PreviewItem(
        knob_id=knob.id,
        title=knob.title,
        description=knob.description,
        requires_root=bool(knob.requires_root),
        requires_reboot=bool(knob.requires_reboot),
        risk_level=str(knob.risk_level),
        action=action,
        file_changes=file_changes,
        would_run=would_run,
        would_write=would_write,
        notes=notes,
    )


# Apply/restore primitives used by the worker.

def systemd_disable_now(unit: str) -> dict[str, Any]:
    pre_enabled = run(["systemctl", "is-enabled", unit]).stdout.strip()
    pre_active = run(["systemctl", "is-active", unit]).stdout.strip()

    r = run(["systemctl", "disable", "--now", unit])
    return {
        "kind": "systemd_unit_toggle",
        "unit": unit,
        "pre": {"enabled": pre_enabled, "active": pre_active},
        "result": {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr},
    }


def systemd_restore(effect: dict[str, Any]) -> None:
    unit = str(effect["unit"])
    pre = effect.get("pre", {})
    pre_enabled = str(pre.get("enabled", ""))
    pre_active = str(pre.get("active", ""))

    if pre_enabled == "enabled":
        run(["systemctl", "enable", unit])
    elif pre_enabled == "disabled":
        run(["systemctl", "disable", unit])

    if pre_active == "active":
        run(["systemctl", "start", unit])
    elif pre_active == "inactive":
        run(["systemctl", "stop", unit])


def write_sysfs_values(glob_pat: str, value: str) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for p in sorted(glob.glob(glob_pat)):
        path = Path(p)
        try:
            before = path.read_text(encoding="utf-8").strip()
        except Exception:
            before = None
        path.write_text(value + "\n", encoding="utf-8")
        effects.append({"kind": "sysfs_write", "path": p, "before": before, "after": value})
    return effects


def restore_sysfs(effects: list[dict[str, Any]]) -> None:
    for e in effects:
        if e.get("kind") != "sysfs_write":
            continue
        before = e.get("before")
        if before is None:
            continue
        Path(str(e["path"])).write_text(str(before) + "\n", encoding="utf-8")

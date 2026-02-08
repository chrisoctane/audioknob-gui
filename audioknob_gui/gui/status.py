from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QTextEdit,
    QVBoxLayout,
)
from shiboken6 import isValid

from audioknob_gui.gui.actions import QueueTaskWorker
from audioknob_gui.gui.logging_utils import _get_gui_logger
from audioknob_gui.gui.knobs.registry import apply_info_param_overrides
from audioknob_gui.gui.state import save_state
from audioknob_gui.gui.system_info import _param_present
from audioknob_gui.gui.worker_api import (
    _PKEXEC_CANCELLED,
    _is_pkexec_cancel,
    _pick_root_worker_path,
    _pkexec_available,
    _registry_path,
)


REFERENCE_PRESET_LABEL = "Reference Preset"
FACTORY_PRESET_LABEL = "Factory Preset"
REFERENCE_PRESET_DOT_COLOR = "#4a90e2"
FACTORY_PRESET_DOT_COLOR = "#2fbf71"


def _status_for_preset_compare(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if value in ("sys_default", "deviated"):
        return "not_applied"
    if value.startswith("result:"):
        return None
    return value


def _preset_match_summary(ref_match: bool, factory_match: bool) -> str:
    if ref_match and factory_match:
        return "Matches Reference + Factory presets"
    if ref_match:
        return "Matches Reference preset"
    if factory_match:
        return "Matches Factory preset"
    return "Differs from saved presets"


def baseline_available(ui) -> bool:
    baseline = ui.state.get("baseline_statuses")
    return isinstance(baseline, dict) and bool(baseline)


def baseline_is_manual(ui) -> bool:
    return ui.state.get("baseline_source") in ("capture", "import")


def factory_available(ui) -> bool:
    factory = ui.state.get("factory_statuses")
    return isinstance(factory, dict) and bool(factory)


def factory_preset_locked(ui) -> bool:
    return factory_available(ui)


def _factory_lock_message(ui) -> str:
    captured_at = ui.state.get("factory_captured_at")
    when = captured_at if isinstance(captured_at, str) and captured_at else "unknown date"
    source = ui.state.get("factory_source")
    source_text = str(source) if isinstance(source, str) and source else "saved"
    return (
        f"{FACTORY_PRESET_LABEL} is immutable once set.\n\n"
        f"Captured: {when}\n"
        f"Source: {source_text}\n\n"
        "Use Export to copy it. To recreate it, remove the local app state and re-run first launch."
    )


def _profiles_dir() -> Path:
    docs = Path.home() / "Documents"
    base = docs if docs.exists() else Path.home()
    out = base / "audioknob"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _sanitize_label(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return cleaned or "import"


def _import_label(path: str | None, *, fallback: str) -> str:
    if path:
        try:
            return _sanitize_label(Path(path).stem)
        except Exception:
            pass
    return _sanitize_label(fallback)


def _profile_mismatch_notes(
    source_profile: dict[str, object] | None,
    current_profile: dict[str, object] | None,
) -> list[str]:
    mismatch_notes: list[str] = []
    if source_profile and current_profile:
        for key in ("distro_id", "version_id", "boot_system"):
            a = source_profile.get(key)
            b = current_profile.get(key)
            if a and b and a != b:
                mismatch_notes.append(f"{key}: {a} → {b}")
    elif source_profile or current_profile:
        mismatch_notes.append("Profile metadata is missing on one side.")
    return mismatch_notes


def _baseline_snapshot_payload(
    ui,
    statuses: dict[str, str],
    *,
    source: str,
    config: dict[str, object] | None,
    captured_at: str | None = None,
) -> dict[str, object]:
    from audioknob_gui import __version__

    if not isinstance(captured_at, str) or not captured_at:
        captured_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    profile = ui.state.get("system_profile")
    profile_payload = deepcopy(profile) if isinstance(profile, dict) else None
    return {
        "schema": 1,
        "baseline_statuses": dict(statuses),
        "baseline_checks": build_baseline_checks(ui, statuses),
        "baseline_captured_at": captured_at,
        "baseline_source": source,
        "baseline_config": dict(config or {}),
        "system_profile": profile_payload,
        "exported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "app_version": __version__,
    }


def _baseline_config_keys() -> list[str]:
    return [
        "qjackctl_cpu_cores",
        "kernel_isolcpus_cores",
        "kernel_nohz_full_cores",
        "kernel_rcu_nocbs_cores",
        "kernel_irqaffinity_cores",
        "irq_housekeeping_auto",
        "irq_pinning_devices",
        "irq_pinning_cpu_cores",
        "audio_core_plan_count",
        "pipewire_quantum",
        "pipewire_sample_rate",
        "pipewire_clock_allowed_rates",
        "pipewire_clock_min_quantum",
        "pipewire_clock_max_quantum",
        "pipewire_clock_quantum_limit",
        "pipewire_clock_quantum_floor",
        "pipewire_clock_power_of_two",
        "pipewire_mlock_allow",
        "pipewire_mlock_all",
        "pipewire_limits_group",
        "pipewire_limits_enabled",
        "pipewire_rt_prio",
        "pipewire_rt_time_soft",
        "pipewire_rt_time_hard",
        "pipewire_nice_level",
        "pipewire_rlimits_enabled",
        "pipewire_rtkit_enabled",
        "pipewire_rtportal_enabled",
        "pipewire_num_data_loops",
        "pipewire_data_loops",
        "wireplumber_alsa_period_size",
        "wireplumber_alsa_period_num",
        "wireplumber_alsa_headroom",
        "wireplumber_alsa_disable_batch",
        "pipewire_pro_audio_device_id",
        "power_profile_backend",
    ]


def _extract_baseline_config(ui) -> dict[str, object]:
    config: dict[str, object] = {}
    for key in _baseline_config_keys():
        if key in ui.state:
            config[key] = deepcopy(ui.state.get(key))
    return config


def _apply_baseline_config(ui, config: dict[str, object]) -> None:
    if not isinstance(config, dict):
        return
    for key in _baseline_config_keys():
        if key in config:
            ui.state[key] = deepcopy(config.get(key))
    save_state(ui.state)


def set_baseline_buttons_enabled(ui, enabled: bool) -> None:
    btn = getattr(ui, "btn_baseline_menu", None)
    if isinstance(btn, QToolButton):
        btn.setEnabled(enabled)
    for name in ("act_baseline_capture", "act_baseline_import", "act_baseline_export", "act_baseline_restore"):
        action = getattr(ui, name, None)
        if action is not None:
            action.setEnabled(enabled)
    factory_text = {
        "act_factory_capture": f"Capture {FACTORY_PRESET_LABEL}...",
        "act_factory_import": f"Import {FACTORY_PRESET_LABEL}...",
        "act_factory_export": f"Export {FACTORY_PRESET_LABEL}...",
        "act_factory_restore": f"Queue Restore {FACTORY_PRESET_LABEL}...",
        "act_factory_reset": f"{FACTORY_PRESET_LABEL} (Reset All)...",
    }
    for name, text in factory_text.items():
        action = getattr(ui, name, None)
        if action is not None:
            action.setEnabled(enabled)
            action.setText(text)
            action.setToolTip("")
    if factory_preset_locked(ui):
        lock_tip = _factory_lock_message(ui)
        for name in ("act_factory_capture", "act_factory_import"):
            action = getattr(ui, name, None)
            if action is None:
                continue
            action.setEnabled(enabled)
            action.setToolTip(lock_tip)
            action.setText(f"{factory_text[name]} (Locked)")


def set_baseline_state(
    ui,
    statuses: dict[str, str],
    *,
    checks: dict[str, list[str]] | None = None,
    captured_at: str | None = None,
    source: str = "initial",
    config: dict[str, object] | None = None,
    profile: dict[str, object] | None = None,
    import_path: str | None = None,
) -> None:
    if not isinstance(statuses, dict) or not statuses:
        return
    valid_ids = {k.id for k in ui.registry}
    cleaned = {k: str(v) for k, v in statuses.items() if k in valid_ids}
    if not cleaned:
        return
    if not isinstance(captured_at, str) or not captured_at:
        captured_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    ui.state["baseline_statuses"] = cleaned
    ui.state["baseline_captured_at"] = captured_at
    ui.state["baseline_txid_user"] = ui.state.get("last_user_txid")
    ui.state["baseline_txid_root"] = ui.state.get("last_root_txid")
    ui.state["baseline_source"] = source if source in ("initial", "capture", "import") else "initial"
    if not isinstance(profile, dict):
        profile = ui.state.get("system_profile") if isinstance(ui.state.get("system_profile"), dict) else None
    ui.state["baseline_profile"] = deepcopy(profile) if isinstance(profile, dict) else None
    if source == "import":
        ui.state["baseline_import_path"] = import_path if isinstance(import_path, str) else None
    else:
        ui.state["baseline_import_path"] = None
    if config is None and source != "import":
        ui.state["baseline_config"] = _extract_baseline_config(ui)
    elif isinstance(config, dict):
        ui.state["baseline_config"] = config
    elif source == "import":
        ui.state["baseline_config"] = {}
    if checks is None:
        ui.state["baseline_checks"] = build_baseline_checks(ui, cleaned)
    elif isinstance(checks, dict):
        clean_checks: dict[str, list[str]] = {}
        for knob_id, lines in checks.items():
            if knob_id not in valid_ids:
                continue
            if not isinstance(lines, list):
                continue
            clean_checks[knob_id] = [str(x) for x in lines]
        ui.state["baseline_checks"] = clean_checks
    else:
        ui.state["baseline_checks"] = {}
    save_state(ui.state)
    ui._baseline_ready = True
    ui._refresh_statuses()
    ui._populate()


def set_factory_state(
    ui,
    statuses: dict[str, str],
    *,
    checks: dict[str, list[str]] | None = None,
    captured_at: str | None = None,
    source: str | None = None,
    config: dict[str, object] | None = None,
    profile: dict[str, object] | None = None,
    import_path: str | None = None,
) -> None:
    if not isinstance(statuses, dict) or not statuses:
        return
    valid_ids = {k.id for k in ui.registry}
    cleaned = {k: str(v) for k, v in statuses.items() if k in valid_ids}
    if not cleaned:
        return
    ui.state["factory_statuses"] = cleaned
    if not isinstance(profile, dict):
        profile = ui.state.get("system_profile") if isinstance(ui.state.get("system_profile"), dict) else None
    ui.state["factory_profile"] = deepcopy(profile) if isinstance(profile, dict) else None
    if isinstance(checks, dict):
        clean_checks: dict[str, list[str]] = {}
        for knob_id, lines in checks.items():
            if knob_id not in valid_ids:
                continue
            if not isinstance(lines, list):
                continue
            clean_checks[knob_id] = [str(x) for x in lines]
        ui.state["factory_checks"] = clean_checks
    else:
        ui.state["factory_checks"] = {}
    if isinstance(captured_at, str) and captured_at:
        factory_captured_at = captured_at
    else:
        factory_captured_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    ui.state["factory_captured_at"] = factory_captured_at
    ui.state["factory_source"] = source if isinstance(source, str) and source else "capture"
    if source == "import":
        ui.state["factory_import_path"] = import_path if isinstance(import_path, str) else None
    else:
        ui.state["factory_import_path"] = None
    if isinstance(config, dict):
        ui.state["factory_config"] = config
    else:
        ui.state["factory_config"] = {}
    save_state(ui.state)


def baseline_snapshot(ui) -> dict[str, object]:
    from audioknob_gui import __version__

    profile = ui.state.get("baseline_profile")
    if not isinstance(profile, dict):
        profile = ui.state.get("system_profile")
    profile_payload = deepcopy(profile) if isinstance(profile, dict) else None
    return {
        "schema": 1,
        "baseline_statuses": dict(ui.state.get("baseline_statuses") or {}),
        "baseline_checks": dict(ui.state.get("baseline_checks") or {}),
        "baseline_captured_at": ui.state.get("baseline_captured_at"),
        "baseline_source": ui.state.get("baseline_source", "initial"),
        "baseline_config": dict(ui.state.get("baseline_config") or {}),
        "system_profile": profile_payload,
        "exported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "app_version": __version__,
    }


def factory_snapshot(ui) -> dict[str, object]:
    from audioknob_gui import __version__

    profile = ui.state.get("factory_profile")
    if not isinstance(profile, dict):
        profile = ui.state.get("system_profile")
    profile_payload = deepcopy(profile) if isinstance(profile, dict) else None
    return {
        "schema": 1,
        "factory_statuses": dict(ui.state.get("factory_statuses") or {}),
        "factory_checks": dict(ui.state.get("factory_checks") or {}),
        "factory_captured_at": ui.state.get("factory_captured_at"),
        "factory_source": ui.state.get("factory_source"),
        "factory_config": dict(ui.state.get("factory_config") or {}),
        "system_profile": profile_payload,
        "exported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "app_version": __version__,
    }


def write_baseline_snapshot(ui, path: str, snapshot: dict[str, object]) -> bool:
    try:
        payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
        Path(path).write_text(payload, encoding="utf-8")
    except Exception as exc:
        QMessageBox.warning(ui, REFERENCE_PRESET_LABEL, f"Failed to save {REFERENCE_PRESET_LABEL.lower()}:\n{exc}")
        return False
    return True


def write_factory_snapshot(ui, path: str, snapshot: dict[str, object]) -> bool:
    try:
        payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
        Path(path).write_text(payload, encoding="utf-8")
    except Exception as exc:
        QMessageBox.warning(ui, FACTORY_PRESET_LABEL, f"Failed to save {FACTORY_PRESET_LABEL.lower()}:\n{exc}")
        return False
    return True


def load_baseline_snapshot(ui, path: str) -> dict[str, object] | None:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        QMessageBox.warning(
            ui,
            REFERENCE_PRESET_LABEL,
            f"Failed to load {REFERENCE_PRESET_LABEL.lower()}:\n{exc}",
        )
        return None
    if not isinstance(raw, dict):
        QMessageBox.warning(ui, REFERENCE_PRESET_LABEL, f"{REFERENCE_PRESET_LABEL} file is not a JSON object.")
        return None
    statuses = raw.get("baseline_statuses")
    if not isinstance(statuses, dict) or not statuses:
        QMessageBox.warning(ui, REFERENCE_PRESET_LABEL, f"{REFERENCE_PRESET_LABEL} file is missing status data.")
        return None
    valid_ids = {k.id for k in ui.registry}
    cleaned = {k: str(v) for k, v in statuses.items() if k in valid_ids}
    if not cleaned:
        QMessageBox.warning(ui, REFERENCE_PRESET_LABEL, f"{REFERENCE_PRESET_LABEL} file has no known knob ids.")
        return None
    checks = raw.get("baseline_checks")
    clean_checks: dict[str, list[str]] | None = None
    if isinstance(checks, dict):
        clean_checks = {}
        for knob_id, lines in checks.items():
            if knob_id not in valid_ids:
                continue
            if not isinstance(lines, list):
                continue
            clean_checks[knob_id] = [str(x) for x in lines]
    captured_at = raw.get("baseline_captured_at")
    if not isinstance(captured_at, str) or not captured_at:
        captured_at = None
    config = raw.get("baseline_config")
    if not isinstance(config, dict):
        config = None
    profile = raw.get("system_profile")
    if not isinstance(profile, dict):
        profile = None
    return {
        "statuses": cleaned,
        "checks": clean_checks,
        "captured_at": captured_at,
        "config": config,
        "profile": profile,
    }


def load_factory_snapshot(ui, path: str) -> dict[str, object] | None:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        QMessageBox.warning(
            ui,
            FACTORY_PRESET_LABEL,
            f"Failed to load {FACTORY_PRESET_LABEL.lower()}:\n{exc}",
        )
        return None
    if not isinstance(raw, dict):
        QMessageBox.warning(ui, FACTORY_PRESET_LABEL, f"{FACTORY_PRESET_LABEL} file is not a JSON object.")
        return None
    statuses = raw.get("factory_statuses")
    if not isinstance(statuses, dict) or not statuses:
        QMessageBox.warning(ui, FACTORY_PRESET_LABEL, f"{FACTORY_PRESET_LABEL} file is missing status data.")
        return None
    valid_ids = {k.id for k in ui.registry}
    cleaned = {k: str(v) for k, v in statuses.items() if k in valid_ids}
    if not cleaned:
        QMessageBox.warning(ui, FACTORY_PRESET_LABEL, f"{FACTORY_PRESET_LABEL} file has no known knob ids.")
        return None
    checks = raw.get("factory_checks")
    clean_checks: dict[str, list[str]] | None = None
    if isinstance(checks, dict):
        clean_checks = {}
        for knob_id, lines in checks.items():
            if knob_id not in valid_ids:
                continue
            if not isinstance(lines, list):
                continue
            clean_checks[knob_id] = [str(x) for x in lines]
    captured_at = raw.get("factory_captured_at")
    if not isinstance(captured_at, str) or not captured_at:
        captured_at = None
    config = raw.get("factory_config")
    if not isinstance(config, dict):
        config = None
    profile = raw.get("system_profile")
    if not isinstance(profile, dict):
        profile = None
    return {
        "statuses": cleaned,
        "checks": clean_checks,
        "captured_at": captured_at,
        "config": config,
        "profile": profile,
    }


def confirm_baseline_overwrite(ui, summary: str) -> bool:
    if not ui._baseline_ready:
        return True
    msg = (
        f"{summary}\n\n"
        f"This will overwrite the current {REFERENCE_PRESET_LABEL.lower()}.\n\n"
        "This does not change system settings.\n\nContinue?"
    )
    return QMessageBox.question(ui, REFERENCE_PRESET_LABEL, msg) == QMessageBox.Yes


def confirm_factory_overwrite(ui, summary: str) -> bool:
    msg = (
        f"{summary}\n\n"
        f"This will update the active {FACTORY_PRESET_LABEL.lower()} in the app.\n"
        "Existing snapshot files are preserved on disk.\n\n"
        "This does not change system settings.\n\nContinue?"
    )
    return QMessageBox.question(ui, FACTORY_PRESET_LABEL, msg) == QMessageBox.Yes


def _baseline_profile_summary(profile: dict[str, object] | None) -> str:
    if not isinstance(profile, dict):
        return "unknown"
    parts: list[str] = []
    distro = profile.get("pretty_name") or profile.get("distro_id")
    boot = profile.get("boot_system")
    version = profile.get("version_id")
    if distro:
        parts.append(str(distro))
    if version:
        parts.append(f"version {version}")
    if boot:
        parts.append(f"boot {boot}")
    return ", ".join(parts) if parts else "unknown"


def _normalize_baseline_statuses(statuses: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in statuses.items():
        if value in ("unknown", "not_applicable", "partial", "pending_reboot"):
            normalized[key] = "not_applied"
        else:
            normalized[key] = value
    return normalized


def start_baseline_scan(
    ui,
    *,
    on_success,
    on_cancel_title: str = f"{REFERENCE_PRESET_LABEL} Required",
    on_cancel_message: str | None = None,
    on_error_title: str = REFERENCE_PRESET_LABEL,
    on_error_message: str | None = None,
) -> None:
    if ui._baseline_busy:
        return
    ui._baseline_busy = True
    set_baseline_buttons_enabled(ui, False)

    def _task() -> tuple[bool, object, str]:
        argv = [
            sys.executable,
            "-m",
            "audioknob_gui.worker.cli",
            "--registry",
            _registry_path(),
            "status",
        ]
        if _pkexec_available():
            worker = _pick_root_worker_path()
            argv = ["pkexec", worker, "--registry", _registry_path(), "status"]
        try:
            p = subprocess.run(argv, text=True, capture_output=True)
        except Exception as e:
            return False, {}, str(e)
        if not p.stdout.strip():
            err = p.stderr.strip() or f"{REFERENCE_PRESET_LABEL} scan failed"
            if _is_pkexec_cancel(err):
                return False, {}, _PKEXEC_CANCELLED
            return False, {}, err
        try:
            payload = json.loads(p.stdout)
        except Exception:
            err = p.stderr.strip() or p.stdout.strip() or f"{REFERENCE_PRESET_LABEL} parse failed"
            if _is_pkexec_cancel(err):
                return False, {}, _PKEXEC_CANCELLED
            return False, {}, err
        status_map: dict[str, str] = {}
        for item in payload.get("statuses", []):
            if isinstance(item, dict) and item.get("knob_id"):
                status_map[str(item["knob_id"])] = str(item.get("status", "unknown"))
        return True, {"statuses": status_map}, ""

    worker = QueueTaskWorker(_task, parent=ui)

    def _on_done(success: bool, payload: object, message: str) -> None:
        ui._baseline_busy = False
        set_baseline_buttons_enabled(ui, True)
        if not success:
            if message == _PKEXEC_CANCELLED:
                if on_cancel_message:
                    QMessageBox.information(ui, on_cancel_title, on_cancel_message)
                return
            if on_error_message:
                QMessageBox.warning(ui, on_error_title, on_error_message + f"\n\n{message}")
                return
            _get_gui_logger().warning("reference preset scan failed error=%s", message)
            return
        if not isinstance(payload, dict):
            return
        statuses = payload.get("statuses") or {}
        if not isinstance(statuses, dict) or not statuses:
            return
        on_success(statuses)

    worker.finished.connect(_on_done)
    worker.finished.connect(worker.deleteLater)
    ui._task_threads.append(worker)
    worker.start()


def ensure_baseline_state(ui) -> None:
    if ui._baseline_ready or ui._baseline_busy:
        return

    def _on_success(statuses: dict[str, str]) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        set_baseline_state(ui, statuses, source="initial", captured_at=now)
        if not factory_available(ui):
            config = _extract_baseline_config(ui)
            set_factory_state(
                ui,
                statuses,
                source="initial",
                config=config,
                captured_at=now,
            )
            _get_gui_logger().info("factory preset auto-captured on initial scan")
        _get_gui_logger().info("reference preset scan complete")

    start_baseline_scan(
        ui,
        on_success=_on_success,
        on_cancel_title=f"{REFERENCE_PRESET_LABEL} Required",
        on_cancel_message=(
            "Initial state capture was cancelled.\n\n"
            f"Run 'Re-check State' to capture {REFERENCE_PRESET_LABEL.lower()} before making changes."
        ),
    )


def build_baseline_checks(ui, statuses: dict[str, str]) -> dict[str, list[str]]:
    baseline_checks: dict[str, list[str]] = {}
    for knob in ui.registry:
        status = statuses.get(knob.id)
        if status is None:
            continue
        baseline_checks[knob.id] = collect_live_checks(ui, knob, status_override=status)
    return baseline_checks


def on_capture_baseline(ui) -> None:
    if ui._baseline_busy:
        return
    stamp = datetime.now().strftime("%Y%m%d")
    default_name = str(_profiles_dir() / f"ak-reference-{stamp}.json")
    path, _ = QFileDialog.getSaveFileName(
        ui,
        f"Save {REFERENCE_PRESET_LABEL}",
        default_name,
        "JSON Files (*.json)",
    )
    if not path:
        return
    if not path.lower().endswith(".json"):
        path = path + ".json"
    if not confirm_baseline_overwrite(ui, f"Capture {REFERENCE_PRESET_LABEL.lower()}"):
        return

    def _on_success(statuses: dict[str, str]) -> None:
        config = _extract_baseline_config(ui)
        set_baseline_state(ui, statuses, source="capture", config=config)
        snapshot = baseline_snapshot(ui)
        if write_baseline_snapshot(ui, path, snapshot):
            QMessageBox.information(ui, REFERENCE_PRESET_LABEL, f"{REFERENCE_PRESET_LABEL} saved to:\n{path}")

    start_baseline_scan(
        ui,
        on_success=_on_success,
        on_cancel_title=REFERENCE_PRESET_LABEL,
        on_cancel_message=f"{REFERENCE_PRESET_LABEL} capture was cancelled.",
        on_error_title=REFERENCE_PRESET_LABEL,
        on_error_message=f"Failed to capture {REFERENCE_PRESET_LABEL.lower()}.",
    )


def on_import_baseline(ui) -> None:
    if ui._baseline_busy:
        return
    path, _ = QFileDialog.getOpenFileName(
        ui,
        f"Import {REFERENCE_PRESET_LABEL}",
        str(_profiles_dir()),
        "JSON Files (*.json)",
    )
    if not path:
        return
    payload = load_baseline_snapshot(ui, path)
    if not payload:
        return
    captured_at = payload.get("captured_at") or "unknown"
    summary = f"Import {REFERENCE_PRESET_LABEL.lower()} from:\n{path}\nCaptured: {captured_at}"
    current_profile = ui.state.get("system_profile") if isinstance(ui.state.get("system_profile"), dict) else None
    baseline_profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else None
    mismatch_notes = _profile_mismatch_notes(baseline_profile, current_profile)

    use_portable = False
    if mismatch_notes:
        details = "\n".join(f"- {line}" for line in mismatch_notes)
        msg = (
            f"{summary}\n\n"
            f"The {REFERENCE_PRESET_LABEL.lower()} profile does not match this system:\n"
            f"{details}\n\n"
            "Import options:\n"
            "• Import (portable): drop config overrides and normalize unknown/partial to not_applied.\n"
            "• Import anyway: keep settings; restore will warn and create a pre-import backup.\n"
        )
        box = QMessageBox(ui)
        box.setWindowTitle(REFERENCE_PRESET_LABEL)
        box.setText(msg)
        portable_btn = box.addButton("Import (portable)", QMessageBox.AcceptRole)
        full_btn = box.addButton("Import anyway", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_btn:
            return
        use_portable = clicked == portable_btn
    else:
        if not confirm_baseline_overwrite(ui, summary):
            return
    statuses = payload.get("statuses")
    checks = payload.get("checks")
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    if not isinstance(statuses, dict):
        return
    if use_portable:
        statuses = _normalize_baseline_statuses(statuses)
        checks = None
        config = {}
    set_baseline_state(
        ui,
        statuses,
        checks=checks if isinstance(checks, dict) else None,
        captured_at=payload.get("captured_at"),
        source="import",
        config=config if isinstance(config, dict) else {},
        profile=baseline_profile,
        import_path=path,
    )
    QMessageBox.information(ui, REFERENCE_PRESET_LABEL, f"{REFERENCE_PRESET_LABEL} imported.")


def on_export_baseline(ui) -> None:
    if ui._baseline_busy:
        return
    if not baseline_available(ui):
        QMessageBox.information(ui, REFERENCE_PRESET_LABEL, f"No {REFERENCE_PRESET_LABEL.lower()} captured yet.")
        return
    stamp = datetime.now().strftime("%Y%m%d")
    default_name = str(_profiles_dir() / f"ak-reference-{stamp}.json")
    path, _ = QFileDialog.getSaveFileName(
        ui,
        f"Export {REFERENCE_PRESET_LABEL}",
        default_name,
        "JSON Files (*.json)",
    )
    if not path:
        return
    if not path.lower().endswith(".json"):
        path = path + ".json"
    snapshot = baseline_snapshot(ui)
    if write_baseline_snapshot(ui, path, snapshot):
        QMessageBox.information(ui, REFERENCE_PRESET_LABEL, f"{REFERENCE_PRESET_LABEL} exported to:\n{path}")


def on_restore_baseline(ui) -> None:
    if not baseline_available(ui):
        QMessageBox.information(ui, REFERENCE_PRESET_LABEL, f"No {REFERENCE_PRESET_LABEL.lower()} captured yet.")
        return
    baseline = ui.state.get("baseline_statuses") or {}
    if not isinstance(baseline, dict) or not baseline:
        QMessageBox.information(ui, REFERENCE_PRESET_LABEL, f"No {REFERENCE_PRESET_LABEL.lower()} captured yet.")
        return
    current_config_snapshot = _extract_baseline_config(ui)
    restore_config = ui.state.get("baseline_config")
    if isinstance(restore_config, dict) and restore_config:
        _apply_baseline_config(ui, restore_config)
    by_id = {k.id: k for k in ui.registry}
    apply_ids: list[str] = []
    reset_ids: list[str] = []
    skipped: list[str] = []
    partial_ids: list[str] = []
    for knob in ui.registry:
        base = baseline.get(knob.id)
        if base is None:
            continue
        if knob.impl is None or (knob.impl and knob.impl.kind == "read_only"):
            continue
        if knob.id == "audio_group_membership":
            skipped.append(f"{knob.title}: group changes require manual action")
            continue
        if base in ("applied", "pending_reboot"):
            desired = "apply"
        elif base in ("not_applied", "sys_default"):
            desired = "reset"
        elif base == "partial":
            desired = "apply"
            partial_ids.append(knob.title)
        else:
            skipped.append(f"{knob.title}: {REFERENCE_PRESET_LABEL.lower()} status '{base}' not actionable")
            continue
        current = ui._knob_statuses.get(knob.id, "unknown")
        if desired == "apply" and current in ("applied", "pending_reboot"):
            continue
        if desired == "reset" and current in ("not_applied", "sys_default", "not_applicable"):
            continue
        if desired == "apply":
            allowed, reason = ui._queue_apply_allowed(knob)
            if not allowed:
                skipped.append(f"{knob.title}: {reason}")
                continue
            apply_ids.append(knob.id)
        else:
            reset_ids.append(knob.id)

    if not apply_ids and not reset_ids:
        msg = f"{REFERENCE_PRESET_LABEL} matches current state; no changes queued."
        if skipped:
            msg += "\n\nSkipped:\n" + "\n".join(f"- {s}" for s in skipped)
        QMessageBox.information(ui, REFERENCE_PRESET_LABEL, msg)
        return

    mismatch_notes: list[str] = []
    if ui.state.get("baseline_source") == "import":
        baseline_profile = ui.state.get("baseline_profile") if isinstance(ui.state.get("baseline_profile"), dict) else None
        current_profile = ui.state.get("system_profile") if isinstance(ui.state.get("system_profile"), dict) else None
        mismatch_notes = _profile_mismatch_notes(baseline_profile, current_profile)

    summary: list[str] = []
    if apply_ids:
        summary.append("Will queue Apply for:")
        summary.extend(f"- {by_id[kid].title}" for kid in apply_ids if kid in by_id)
    if reset_ids:
        if summary:
            summary.append("")
        summary.append("Will queue Reset for:")
        summary.extend(f"- {by_id[kid].title}" for kid in reset_ids if kid in by_id)
    if skipped:
        summary.append("")
        summary.append("Skipped:")
        summary.extend(f"- {s}" for s in skipped)
    if partial_ids:
        summary.append("")
        summary.append(f"Note: {REFERENCE_PRESET_LABEL.lower()} was partial for:")
        summary.extend(f"- {t}" for t in partial_ids)
    if mismatch_notes:
        summary.append("")
        summary.append(f"Warning: imported {REFERENCE_PRESET_LABEL.lower()} does not match this system:")
        summary.extend(f"- {line}" for line in mismatch_notes)
        summary.append("")
        summary.append("A pre-import backup will be captured before queueing actions.")
    summary_text = "\n".join(summary)
    msg = f"Queue actions to restore the {REFERENCE_PRESET_LABEL.lower()}?\n\n" + summary_text
    if QMessageBox.question(ui, f"Restore {REFERENCE_PRESET_LABEL}", msg) != QMessageBox.Yes:
        return

    if mismatch_notes:
        import_path = ui.state.get("baseline_import_path")
        label = _import_label(import_path, fallback="baseline-import")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        pre_path = str(_profiles_dir() / f"ak-pre-{label}-{stamp}.json")

        def _on_success(statuses: dict[str, str]) -> None:
            snapshot = _baseline_snapshot_payload(
                ui,
                statuses,
                source="pre-import",
                config=current_config_snapshot if isinstance(current_config_snapshot, dict) else {},
            )
            if not write_baseline_snapshot(ui, pre_path, snapshot):
                return
            ui.state["baseline_preimport_path"] = pre_path
            save_state(ui.state)
            for kid in apply_ids:
                ui._queued_actions[kid] = "apply"
            for kid in reset_ids:
                ui._queued_actions[kid] = "reset"
            ui._save_queue()
            ui._update_queue_ui()
            QMessageBox.information(
                ui,
                f"Restore {REFERENCE_PRESET_LABEL}",
                "Restore actions queued.\n\n"
                f"Pre-import backup saved to:\n{pre_path}\n\n"
                "Undo: Tools → Presets → Reference Preset → Import / Queue Restore.",
            )

        start_baseline_scan(
            ui,
            on_success=_on_success,
            on_cancel_title=f"Restore {REFERENCE_PRESET_LABEL}",
            on_cancel_message="Pre-import backup was cancelled. No changes queued.",
            on_error_title=f"Restore {REFERENCE_PRESET_LABEL}",
            on_error_message="Failed to capture pre-import backup.",
        )
        return

    for kid in apply_ids:
        ui._queued_actions[kid] = "apply"
    for kid in reset_ids:
        ui._queued_actions[kid] = "reset"
    ui._save_queue()
    ui._update_queue_ui()


def on_capture_factory(ui) -> None:
    if ui._baseline_busy:
        return
    if factory_preset_locked(ui):
        QMessageBox.information(ui, FACTORY_PRESET_LABEL, _factory_lock_message(ui))
        return
    stamp = datetime.now().strftime("%Y%m%d")
    default_name = str(_profiles_dir() / f"ak-factory-{stamp}.json")
    path, _ = QFileDialog.getSaveFileName(
        ui,
        f"Save {FACTORY_PRESET_LABEL}",
        default_name,
        "JSON Files (*.json)",
    )
    if not path:
        return
    if not path.lower().endswith(".json"):
        path = path + ".json"
    if not confirm_factory_overwrite(ui, f"Capture {FACTORY_PRESET_LABEL.lower()}"):
        return

    def _on_success(statuses: dict[str, str]) -> None:
        config = _extract_baseline_config(ui)
        set_factory_state(ui, statuses, source="capture", config=config)
        snapshot = factory_snapshot(ui)
        if write_factory_snapshot(ui, path, snapshot):
            QMessageBox.information(ui, FACTORY_PRESET_LABEL, f"{FACTORY_PRESET_LABEL} saved to:\n{path}")

    start_baseline_scan(
        ui,
        on_success=_on_success,
        on_cancel_title=FACTORY_PRESET_LABEL,
        on_cancel_message=f"{FACTORY_PRESET_LABEL} capture was cancelled.",
        on_error_title=FACTORY_PRESET_LABEL,
        on_error_message=f"Failed to capture {FACTORY_PRESET_LABEL.lower()}.",
    )


def on_import_factory(ui) -> None:
    if ui._baseline_busy:
        return
    if factory_preset_locked(ui):
        QMessageBox.information(ui, FACTORY_PRESET_LABEL, _factory_lock_message(ui))
        return
    path, _ = QFileDialog.getOpenFileName(
        ui,
        f"Import {FACTORY_PRESET_LABEL}",
        str(_profiles_dir()),
        "JSON Files (*.json)",
    )
    if not path:
        return
    payload = load_factory_snapshot(ui, path)
    if not payload:
        return
    captured_at = payload.get("captured_at") or "unknown"
    summary = f"Import {FACTORY_PRESET_LABEL.lower()} from:\n{path}\nCaptured: {captured_at}"
    current_profile = ui.state.get("system_profile") if isinstance(ui.state.get("system_profile"), dict) else None
    factory_profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else None
    mismatch_notes = _profile_mismatch_notes(factory_profile, current_profile)

    use_portable = False
    if mismatch_notes:
        details = "\n".join(f"- {line}" for line in mismatch_notes)
        msg = (
            f"{summary}\n\n"
            f"The {FACTORY_PRESET_LABEL.lower()} profile does not match this system:\n"
            f"{details}\n\n"
            "Import options:\n"
            "• Import (portable): drop config overrides and normalize unknown/partial to not_applied.\n"
            "• Import anyway: keep settings; restore will warn and create a pre-import backup.\n"
        )
        box = QMessageBox(ui)
        box.setWindowTitle(FACTORY_PRESET_LABEL)
        box.setText(msg)
        portable_btn = box.addButton("Import (portable)", QMessageBox.AcceptRole)
        full_btn = box.addButton("Import anyway", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_btn:
            return
        use_portable = clicked == portable_btn
    else:
        if not confirm_factory_overwrite(ui, summary):
            return

    statuses = payload.get("statuses")
    checks = payload.get("checks")
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    if not isinstance(statuses, dict):
        return
    if use_portable:
        statuses = _normalize_baseline_statuses(statuses)
        checks = None
        config = {}
    set_factory_state(
        ui,
        statuses,
        checks=checks if isinstance(checks, dict) else None,
        captured_at=payload.get("captured_at"),
        source="import",
        config=config if isinstance(config, dict) else {},
        profile=factory_profile,
        import_path=path,
    )
    QMessageBox.information(ui, FACTORY_PRESET_LABEL, f"{FACTORY_PRESET_LABEL} imported.")


def on_export_factory(ui) -> None:
    if ui._baseline_busy:
        return
    if not factory_available(ui):
        QMessageBox.information(ui, FACTORY_PRESET_LABEL, f"No {FACTORY_PRESET_LABEL.lower()} captured yet.")
        return
    stamp = datetime.now().strftime("%Y%m%d")
    default_name = str(_profiles_dir() / f"ak-factory-{stamp}.json")
    path, _ = QFileDialog.getSaveFileName(
        ui,
        f"Export {FACTORY_PRESET_LABEL}",
        default_name,
        "JSON Files (*.json)",
    )
    if not path:
        return
    if not path.lower().endswith(".json"):
        path = path + ".json"
    snapshot = factory_snapshot(ui)
    if write_factory_snapshot(ui, path, snapshot):
        QMessageBox.information(ui, FACTORY_PRESET_LABEL, f"{FACTORY_PRESET_LABEL} exported to:\n{path}")


def on_restore_factory(ui) -> None:
    if not factory_available(ui):
        QMessageBox.information(ui, FACTORY_PRESET_LABEL, f"No {FACTORY_PRESET_LABEL.lower()} captured yet.")
        return
    factory = ui.state.get("factory_statuses") or {}
    if not isinstance(factory, dict) or not factory:
        QMessageBox.information(ui, FACTORY_PRESET_LABEL, f"No {FACTORY_PRESET_LABEL.lower()} captured yet.")
        return
    current_config_snapshot = _extract_baseline_config(ui)
    restore_config = ui.state.get("factory_config")
    if isinstance(restore_config, dict) and restore_config:
        _apply_baseline_config(ui, restore_config)
    by_id = {k.id: k for k in ui.registry}
    apply_ids: list[str] = []
    reset_ids: list[str] = []
    skipped: list[str] = []
    partial_ids: list[str] = []
    for knob in ui.registry:
        base = factory.get(knob.id)
        if base is None:
            continue
        if knob.impl is None or (knob.impl and knob.impl.kind == "read_only"):
            continue
        if knob.id == "audio_group_membership":
            skipped.append(f"{knob.title}: group changes require manual action")
            continue
        if base in ("applied", "pending_reboot"):
            desired = "apply"
        elif base in ("not_applied", "sys_default"):
            desired = "reset"
        elif base == "partial":
            desired = "apply"
            partial_ids.append(knob.title)
        else:
            skipped.append(f"{knob.title}: {FACTORY_PRESET_LABEL.lower()} status '{base}' not actionable")
            continue
        current = ui._knob_statuses.get(knob.id, "unknown")
        if desired == "apply" and current in ("applied", "pending_reboot"):
            continue
        if desired == "reset" and current in ("not_applied", "sys_default", "not_applicable"):
            continue
        if desired == "apply":
            allowed, reason = ui._queue_apply_allowed(knob)
            if not allowed:
                skipped.append(f"{knob.title}: {reason}")
                continue
            apply_ids.append(knob.id)
        else:
            reset_ids.append(knob.id)

    if not apply_ids and not reset_ids:
        msg = f"{FACTORY_PRESET_LABEL} matches current state; no changes queued."
        if skipped:
            msg += "\n\nSkipped:\n" + "\n".join(f"- {s}" for s in skipped)
        QMessageBox.information(ui, FACTORY_PRESET_LABEL, msg)
        return

    mismatch_notes: list[str] = []
    if ui.state.get("factory_source") == "import":
        factory_profile = ui.state.get("factory_profile") if isinstance(ui.state.get("factory_profile"), dict) else None
        current_profile = ui.state.get("system_profile") if isinstance(ui.state.get("system_profile"), dict) else None
        mismatch_notes = _profile_mismatch_notes(factory_profile, current_profile)

    summary: list[str] = []
    if apply_ids:
        summary.append("Will queue Apply for:")
        summary.extend(f"- {by_id[kid].title}" for kid in apply_ids if kid in by_id)
    if reset_ids:
        if summary:
            summary.append("")
        summary.append("Will queue Reset for:")
        summary.extend(f"- {by_id[kid].title}" for kid in reset_ids if kid in by_id)
    if skipped:
        summary.append("")
        summary.append("Skipped:")
        summary.extend(f"- {s}" for s in skipped)
    if partial_ids:
        summary.append("")
        summary.append(f"Note: {FACTORY_PRESET_LABEL.lower()} was partial for:")
        summary.extend(f"- {t}" for t in partial_ids)
    if mismatch_notes:
        summary.append("")
        summary.append(f"Warning: imported {FACTORY_PRESET_LABEL.lower()} does not match this system:")
        summary.extend(f"- {line}" for line in mismatch_notes)
        summary.append("")
        summary.append("A pre-import backup will be captured before queueing actions.")
    summary_text = "\n".join(summary)
    msg = f"Queue actions to restore {FACTORY_PRESET_LABEL.lower()}?\n\n" + summary_text
    if QMessageBox.question(ui, FACTORY_PRESET_LABEL, msg) != QMessageBox.Yes:
        return

    if mismatch_notes:
        import_path = ui.state.get("factory_import_path")
        label = _import_label(import_path, fallback="factory-import")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        pre_path = str(_profiles_dir() / f"ak-pre-{label}-{stamp}.json")

        def _on_success(statuses: dict[str, str]) -> None:
            snapshot = _baseline_snapshot_payload(
                ui,
                statuses,
                source="pre-import",
                config=current_config_snapshot if isinstance(current_config_snapshot, dict) else {},
            )
            if not write_baseline_snapshot(ui, pre_path, snapshot):
                return
            ui.state["factory_preimport_path"] = pre_path
            save_state(ui.state)
            for kid in apply_ids:
                ui._queued_actions[kid] = "apply"
            for kid in reset_ids:
                ui._queued_actions[kid] = "reset"
            ui._save_queue()
            ui._update_queue_ui()
            ui._refresh_statuses()
            ui._populate()
            QMessageBox.information(
                ui,
                FACTORY_PRESET_LABEL,
                "Restore actions queued.\n\n"
                f"Pre-import backup saved to:\n{pre_path}\n\n"
                "Undo: Tools → Presets → Reference Preset → Import / Queue Restore.",
            )

        start_baseline_scan(
            ui,
            on_success=_on_success,
            on_cancel_title=FACTORY_PRESET_LABEL,
            on_cancel_message="Pre-import backup was cancelled. No changes queued.",
            on_error_title=FACTORY_PRESET_LABEL,
            on_error_message="Failed to capture pre-import backup.",
        )
        return

    for kid in apply_ids:
        ui._queued_actions[kid] = "apply"
    for kid in reset_ids:
        ui._queued_actions[kid] = "reset"
    ui._save_queue()
    ui._update_queue_ui()
    ui._refresh_statuses()
    ui._populate()


def prune_queue_from_statuses(ui) -> None:
    if not ui._queued_actions:
        return
    keep: dict[str, str] = {}
    for kid, action in ui._queued_actions.items():
        status = ui._knob_statuses.get(kid)
        if action == "apply" and status in ("applied", "pending_reboot"):
            continue
        if action == "reset" and status in ("not_applied", "not_applicable", "sys_default"):
            continue
        keep[kid] = action
    if keep != ui._queued_actions:
        ui._queued_actions = keep
        ui._save_queue()


def on_recheck_state(ui) -> None:
    if ui._status_busy:
        return
    _get_gui_logger().info("state recheck requested")
    if not ui._baseline_ready:
        ensure_baseline_state(ui)
        return
    refresh_statuses(ui)


def refresh_statuses(ui) -> None:
    """Fetch current status of all knobs (async)."""
    if ui._status_busy:
        return
    ui._status_busy = True

    def _task() -> tuple[bool, object, str]:
        try:
            statuses: dict[str, str] = {}
            argv = [
                sys.executable,
                "-m",
                "audioknob_gui.worker.cli",
                "--registry",
                _registry_path(),
                "status",
            ]
            p = subprocess.run(argv, text=True, capture_output=True, timeout=15)
            if p.returncode == 0:
                data = json.loads(p.stdout)
                for item in data.get("statuses", []):
                    statuses[item["knob_id"]] = item["status"]
            return True, statuses, ""
        except Exception as exc:
            return False, {}, str(exc)

    worker = QueueTaskWorker(_task, parent=ui)

    def _on_done(success: bool, payload: object, message: str) -> None:
        ui._status_busy = False
        if success and isinstance(payload, dict):
            ui._knob_statuses = payload
        else:
            ui._knob_statuses = {}
        apply_session_dependent_statuses(ui)
        ui._update_reboot_banner()
        prune_queue_from_statuses(ui)
        ui._update_queue_ui()
        ui._populate()

    worker.finished.connect(_on_done)
    worker.finished.connect(worker.deleteLater)
    ui._task_threads.append(worker)
    worker.start()


def apply_session_dependent_statuses(ui) -> None:
    status = ui._knob_statuses.get("rt_limits_audio_group")
    if status == "applied" and not rt_limits_active(ui):
        ui._knob_statuses["rt_limits_audio_group"] = "pending_reboot"
    status = ui._knob_statuses.get("audio_group_membership")
    if status == "applied" and not audio_groups_active(ui):
        ui._knob_statuses["audio_group_membership"] = "pending_reboot"
    _apply_pipewire_rt_setup_status(ui)
    apply_baseline_statuses(ui)


def _pipewire_rt_module_configured(ui) -> bool:
    state_keys = (
        "pipewire_rt_prio",
        "pipewire_rt_time_soft",
        "pipewire_rt_time_hard",
        "pipewire_nice_level",
        "pipewire_rlimits_enabled",
        "pipewire_rtkit_enabled",
        "pipewire_rtportal_enabled",
    )
    return any(ui.state.get(key) is not None for key in state_keys)


def _apply_pipewire_rt_setup_status(ui) -> None:
    if "pipewire_rt_setup" not in ui._knob_statuses and not any(
        k.id == "pipewire_rt_setup" for k in ui.registry
    ):
        return
    limits = ui._knob_statuses.get("pipewire_rt_limits_group", "unknown")
    module = ui._knob_statuses.get("pipewire_rt_module_tuning", "unknown")
    module_configured = _pipewire_rt_module_configured(ui)
    limits_enabled = ui.state.get("pipewire_limits_enabled")
    if limits_enabled is False:
        if module_configured:
            if module in ("running", "pending_reboot"):
                ui._knob_statuses["pipewire_rt_setup"] = module
            elif module in ("applied",):
                ui._knob_statuses["pipewire_rt_setup"] = "applied"
            elif module in ("not_applied", "sys_default"):
                ui._knob_statuses["pipewire_rt_setup"] = "not_applied"
            elif module == "unknown":
                ui._knob_statuses["pipewire_rt_setup"] = "unknown"
            else:
                ui._knob_statuses["pipewire_rt_setup"] = "partial"
        else:
            ui._knob_statuses["pipewire_rt_setup"] = "not_applied"
        return

    if limits in ("running", "pending_reboot"):
        ui._knob_statuses["pipewire_rt_setup"] = limits
        return
    if module_configured and module in ("running", "pending_reboot"):
        ui._knob_statuses["pipewire_rt_setup"] = module
        return
    if module_configured:
        if limits in ("applied",) and module in ("applied",):
            ui._knob_statuses["pipewire_rt_setup"] = "applied"
            return
        if limits in ("not_applied", "sys_default") and module in ("not_applied", "sys_default"):
            ui._knob_statuses["pipewire_rt_setup"] = "not_applied"
            return
        if limits == "unknown" or module == "unknown":
            ui._knob_statuses["pipewire_rt_setup"] = "unknown"
            return
        ui._knob_statuses["pipewire_rt_setup"] = "partial"
        return

    if limits in ("applied", "pending_reboot"):
        ui._knob_statuses["pipewire_rt_setup"] = limits
        return
    if limits in ("not_applied", "sys_default"):
        ui._knob_statuses["pipewire_rt_setup"] = "not_applied"
        return
    ui._knob_statuses["pipewire_rt_setup"] = limits


def apply_baseline_statuses(ui) -> None:
    baseline = ui.state.get("baseline_statuses")
    factory = ui.state.get("factory_statuses")
    baseline_map = baseline if isinstance(baseline, dict) else {}
    factory_map = factory if isinstance(factory, dict) else {}
    matches: dict[str, str] = {}
    flags: dict[str, dict[str, bool]] = {}
    for knob in ui.registry:
        current = _status_for_preset_compare(ui._knob_statuses.get(knob.id))
        if current is None:
            continue

        ref_match = False
        if baseline_map:
            ref_status = _status_for_preset_compare(baseline_map.get(knob.id))
            if ref_status and ref_status not in ("unknown", "not_applicable", "partial", "pending_reboot"):
                ref_match = current == ref_status

        factory_match = False
        if factory_map:
            factory_status = _status_for_preset_compare(factory_map.get(knob.id))
            if factory_status and factory_status not in ("unknown", "not_applicable", "partial", "pending_reboot"):
                factory_match = current == factory_status

        if ref_match or factory_match:
            matches[knob.id] = _preset_match_summary(ref_match, factory_match)
            flags[knob.id] = {"reference": ref_match, "factory": factory_match}
    ui._knob_preset_matches = matches
    ui._knob_preset_flags = flags


def rt_limits_active(ui) -> bool:
    try:
        import resource
    except Exception:
        return False

    try:
        rt_soft, _ = resource.getrlimit(resource.RLIMIT_RTPRIO)
        mem_soft, _ = resource.getrlimit(resource.RLIMIT_MEMLOCK)
    except Exception:
        return False

    rt_ok = rt_soft == resource.RLIM_INFINITY or rt_soft >= 95
    mem_ok = mem_soft == resource.RLIM_INFINITY
    return rt_ok and mem_ok


def audio_groups_active(ui) -> bool:
    try:
        from audioknob_gui.platform.detect import get_missing_groups
    except Exception:
        return True

    try:
        return len(get_missing_groups()) == 0
    except Exception:
        return True


def _cpu_governor_partial_reason(
    *,
    total: int,
    match: int,
    unreadable: int,
    expected_val: str,
    cfg_ok: bool,
    cfg_read_error: str | None,
    service: str | None,
    service_enabled: str | None,
) -> str | None:
    runtime_ok = (
        total > 0
        and unreadable == 0
        and (not expected_val or match == total)
    )
    issues: list[str] = []
    if not runtime_ok:
        issues.append(
            f"runtime governor matches {match}/{total} CPUs (unreadable={unreadable}, expected={expected_val or 'n/a'})"
        )
    if not cfg_ok:
        if cfg_read_error:
            issues.append(f"cpupower config unreadable ({cfg_read_error})")
        else:
            issues.append("cpupower config is missing GOVERNOR=performance")
    if service:
        if service_enabled not in ("enabled", "static", "indirect"):
            issues.append(f"{service} is not enabled ({service_enabled or 'unknown'})")
    if not issues:
        return None
    if runtime_ok:
        return "runtime governor is performance, but persistent setup is incomplete: " + "; ".join(issues) + "."
    return "runtime and persistent governor state do not fully match: " + "; ".join(issues) + "."


def _sysfs_selected_value(raw: str) -> str:
    text = raw.strip()
    if "[" in text and "]" in text:
        match = re.search(r"\[([^\]]+)\]", text)
        if match:
            selected = match.group(1).strip()
            if selected:
                return selected
    return text


def _sysfs_partial_reason(
    *,
    total: int,
    match: int,
    mismatch: int,
    unreadable: int,
    expected_val: str,
) -> str | None:
    if total <= 0:
        return None
    parts = [f"matched {match}/{total} paths"]
    if expected_val:
        parts[0] += f" (expected {expected_val})"
    if mismatch:
        parts.append(f"mismatched={mismatch}")
    if unreadable:
        parts.append(f"unreadable={unreadable}")
    return "sysfs values are mixed: " + ", ".join(parts) + "."


def _config_partial_reason(expected_lines: list[str], current_lines: list[str]) -> str:
    expected_norm = {line.strip() for line in expected_lines if line.strip()}
    current_norm = {line.strip() for line in current_lines if line.strip()}
    missing = [line.strip() for line in expected_lines if line.strip() and line.strip() not in current_norm]
    if missing:
        snippet = ", ".join(missing[:6])
        suffix = "..." if len(missing) > 6 else ""
        return f"missing lines: {snippet}{suffix}"
    if expected_norm == current_norm:
        return "config contains expected values but formatting/order differs (re-apply to normalize)."
    return "config differs from expected (re-apply to rewrite)."


def collect_live_checks(ui, knob, *, status_override: str | None = None) -> list[str]:
    def _read_file(path: str, *, max_lines: int = 40) -> list[str]:
        p = Path(path).expanduser()
        if not p.exists():
            return [f"{path}: missing"]
        try:
            content = p.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            return [f"{path}: unreadable: {e}"]
        if len(content) > max_lines:
            content = content[:max_lines] + ["... (truncated)"]
        return [f"{path}:"] + content

    def _find_pids_by_comm(name: str) -> list[int]:
        pids: list[int] = []
        proc = Path("/proc")
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                comm = (entry / "comm").read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if comm == name:
                pids.append(int(entry.name))
        return pids

    def _read_proc_cmdline(pid: int) -> str:
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except Exception:
            return ""
        return " ".join(x for x in raw.decode("utf-8", errors="replace").split("\0") if x)

    def _read_proc_cpu_allowed_list(pid: int) -> str | None:
        try:
            text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        except Exception:
            return None
        for line in text.splitlines():
            if line.startswith("Cpus_allowed_list:"):
                _, _, value = line.partition(":")
                return value.strip()
        return None

    def _read_jackd_rt_summary(pids: list[int]) -> tuple[int, int, list[int]]:
        total_threads = 0
        rt_threads = 0
        rt_priorities: list[int] = []
        for pid in pids:
            task_dir = Path(f"/proc/{pid}/task")
            try:
                entries = list(task_dir.iterdir())
            except Exception:
                continue
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                total_threads += 1
                tid = int(entry.name)
                try:
                    policy = os.sched_getscheduler(tid)
                except Exception:
                    continue
                if policy in (os.SCHED_FIFO, os.SCHED_RR):
                    rt_threads += 1
                    try:
                        prio = os.sched_getparam(tid).sched_priority
                    except Exception:
                        prio = None
                    if prio is not None:
                        rt_priorities.append(prio)
        return total_threads, rt_threads, sorted(set(rt_priorities))

    lines: list[str] = []
    lines.append(f"knob_id: {knob.id}")
    lines.append(f"title: {knob.title}")
    status = status_override or ui._knob_statuses.get(knob.id, "unknown")
    lines.append(f"status: {status}")
    preset_matches = getattr(ui, "_knob_preset_matches", {})
    if isinstance(preset_matches, dict):
        match = preset_matches.get(knob.id)
        if isinstance(match, str) and match:
            lines.append(f"preset_match: {match}")
    preset_flags = getattr(ui, "_knob_preset_flags", {})
    if isinstance(preset_flags, dict):
        flag_item = preset_flags.get(knob.id)
        if isinstance(flag_item, dict):
            lines.append(f"reference_preset_match: {'yes' if flag_item.get('reference') else 'no'}")
            lines.append(f"factory_preset_match: {'yes' if flag_item.get('factory') else 'no'}")
    baseline_statuses = ui.state.get("baseline_statuses")
    if isinstance(baseline_statuses, dict) and knob.id in baseline_statuses:
        lines.append(f"reference_preset_status: {baseline_statuses.get(knob.id)}")
    factory_statuses = ui.state.get("factory_statuses")
    if isinstance(factory_statuses, dict) and knob.id in factory_statuses:
        lines.append(f"factory_preset_status: {factory_statuses.get(knob.id)}")
    lines.append("")

    kind = knob.impl.kind if knob.impl else ""
    params = dict(knob.impl.params) if knob.impl else {}
    try:
        apply_info_param_overrides(ui, knob, params)
    except Exception:
        pass
    if knob.id == "pipewire_rt_setup":
        kind = "composite"
    lines.append(f"kind: {kind}")
    if knob.id == "power_profile_performance":
        params["backend"] = ui._power_profile_backend_from_state()

    if knob.id == "pipewire_rt_setup":
        limits_status = ui._knob_statuses.get("pipewire_rt_limits_group", "unknown")
        module_status = ui._knob_statuses.get("pipewire_rt_module_tuning", "unknown")
        module_configured = _pipewire_rt_module_configured(ui)
        limits_enabled = ui.state.get("pipewire_limits_enabled")
        limits_label = limits_status
        if limits_enabled is False:
            limits_label = "disabled"
        lines.append("components:")
        lines.append(f"  pipewire_rt_limits_group: {limits_label}")
        lines.append(f"  pipewire_rt_module_tuning: {module_status}")
        if limits_enabled is False:
            lines.append("  note: RT limits disabled in config; status reflects module-rt only.")
        elif not module_configured:
            lines.append("  note: module-rt not configured; status reflects RT limits only.")
        if status == "partial":
            if limits_enabled is not False and limits_status not in ("applied", "pending_reboot"):
                lines.append("partial_reason: RT limits are not fully applied.")
            if module_configured and module_status not in ("applied", "pending_reboot"):
                lines.append("partial_reason: module-rt config does not match configured values.")
        lines.append("")
        lines.append("component checks:")
        for sub_id in ("pipewire_rt_limits_group", "pipewire_rt_module_tuning"):
            sub = next((k for k in ui.registry if k.id == sub_id), None)
            if not sub:
                lines.append(f"  {sub_id}: missing from registry")
                continue
            sub_status = ui._knob_statuses.get(sub_id, "unknown")
            sub_lines = collect_live_checks(ui, sub, status_override=sub_status)
            for entry in sub_lines:
                lines.append(f"  {entry}")
            lines.append("")
        return lines

    if kind == "qjackctl_server_prefix":
        path = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
        lines.append("")
        lines.append("qjackctl_config:")
        cfg = None
        try:
            from audioknob_gui.core.qjackctl import read_config, resolve_server_config_path

            cfg = read_config(Path(path).expanduser())
        except Exception:
            cfg = None
        if cfg is not None:
            active_preset = cfg.def_preset if cfg.def_preset else "(default)"
            lines.append(f"active_preset: {active_preset}")
            cmd = cfg.server_cmd or ""
            tokens = cmd.split()
            ensure_rt = bool(params.get("ensure_rt", True))
            ensure_prio = bool(params.get("ensure_priority", False))
            expected_prio = 90 if ensure_prio else None
            rt_cfg_ok = True
            prio_cfg_ok = True
            if ensure_rt:
                rt_cfg_ok = cfg.realtime is True or any(
                    t in ("-R", "--realtime") or t.startswith("--realtime") for t in tokens
                )
            if ensure_prio:
                prio_cfg_ok = (cfg.priority == expected_prio) or any(t.startswith("-P") for t in tokens)
            expected_cores = ui._qjackctl_cpu_cores_from_state()
            if expected_cores is None:
                cpu_cores = params.get("cpu_cores")
                if cpu_cores is not None:
                    try:
                        from audioknob_gui.core.irq import parse_cpu_list

                        expected_cores = sorted(parse_cpu_list(str(cpu_cores)))
                    except Exception:
                        expected_cores = None
            config_pin_ok = True
            runtime_pin_ok = None
            if expected_cores is not None:
                expected_list = ",".join(str(c) for c in expected_cores)
                if expected_list:
                    try:
                        from audioknob_gui.core.qjackctl import (
                            build_post_start_script,
                            default_post_start_script_path,
                        )

                        expected_script = build_post_start_script(expected_list)
                        expected_path = str(default_post_start_script_path())
                        config_pin_ok = cfg.post_startup_enabled and cfg.post_startup_shell == expected_path
                        if config_pin_ok:
                            try:
                                script_text = Path(expected_path).read_text(encoding="utf-8")
                                config_pin_ok = script_text == expected_script
                            except Exception:
                                config_pin_ok = False
                    except Exception:
                        config_pin_ok = False
                    try:
                        from audioknob_gui.core.irq import parse_cpu_list

                        expected_set = set(expected_cores)
                        runtime_pin_ok = True
                        for pid in _find_pids_by_comm("jackd"):
                            allowed = _read_proc_cpu_allowed_list(pid)
                            if not allowed:
                                continue
                            if parse_cpu_list(allowed) != expected_set:
                                runtime_pin_ok = False
                                break
                    except Exception:
                        runtime_pin_ok = None
                else:
                    config_pin_ok = not cfg.post_startup_enabled and not cfg.post_startup_shell

            if status == "partial":
                if cfg.server_config_enabled:
                    lines.append("partial_reason: ServerConfig enabled; QjackCtl may override GUI settings.")
                if ensure_rt and not rt_cfg_ok:
                    lines.append("partial_reason: Realtime not enabled in QjackCtl config.")
                if ensure_prio and not prio_cfg_ok:
                    lines.append("partial_reason: Priority not set to expected value in QjackCtl config.")
                if expected_cores is not None and not config_pin_ok:
                    lines.append("partial_reason: Post-start script missing or mismatched for CPU pinning.")
                if runtime_pin_ok is False:
                    lines.append("partial_reason: running jackd not pinned to selected cores.")
        include_preset_lines = cfg is not None and bool(cfg.def_preset)
        base_keys = (
            "ServerConfig",
            "ServerConfigName",
            "PostStartupScript",
            "PostStartupScriptShell",
            "\\Server",
            "\\ServerPrefix",
            "Realtime",
            "Priority",
        )
        if include_preset_lines:
            keys = ("Preset", "DefPreset", *base_keys)
        else:
            keys = base_keys
        for line in _read_file(path, max_lines=200):
            if line.strip().startswith("OldPreset"):
                continue
            if any(key in line for key in keys):
                lines.append(line)
        if cfg is not None and cfg.server_config_enabled:
            lines.append("")
            if cfg.server_config_name:
                lines.append(f"server_config: {cfg.server_config_name}")
                server_path = resolve_server_config_path(cfg.server_config_name)
                if server_path is None:
                    lines.append("server_config_path: unknown")
                else:
                    lines.extend(_read_file(str(server_path), max_lines=40))
            else:
                lines.append("server_config: enabled (missing ServerConfigName)")
        lines.append("")
        pids = _find_pids_by_comm("jackd")
        if not pids:
            lines.append("jackd: not running")
        else:
            lines.append(f"jackd_pids: {', '.join(str(p) for p in pids)}")
            for pid in pids:
                cmdline = _read_proc_cmdline(pid)
                if cmdline:
                    lines.append(f"jackd_cmd[{pid}]: {cmdline}")
                allowed = _read_proc_cpu_allowed_list(pid)
                if allowed:
                    lines.append(f"jackd_cpus_allowed_list[{pid}]: {allowed}")
            total_threads, rt_threads, rt_priorities = _read_jackd_rt_summary(pids)
            if total_threads:
                lines.append(f"jackd_threads: {total_threads}")
                lines.append(f"jackd_rt_threads: {rt_threads}")
                if rt_priorities:
                    lines.append(f"jackd_rt_priorities: {', '.join(str(p) for p in rt_priorities)}")
    elif kind == "irq_affinity":
        from audioknob_gui.core.irq import collect_target_irqs, resolve_selected_devices

        def _read_irq_affinity(irq: int) -> str | None:
            p = Path(f"/proc/irq/{irq}/smp_affinity_list")
            if not p.exists():
                return None
            try:
                return p.read_text(encoding="utf-8").strip()
            except Exception:
                return None

        lines.append("")
        lines.append("irq_pinning:")
        device_keys = ui._irq_pinning_devices_from_state()
        cores = ui._irq_pinning_cpu_cores_from_state()
        cpu_list = ",".join(str(c) for c in (cores or []))
        lines.append(f"cpu_cores: {cpu_list or 'unset'}")
        lines.append(f"device_keys: {', '.join(device_keys) if device_keys else 'unset'}")
        auto_housekeeping = bool(ui.state.get("irq_housekeeping_auto", True))
        lines.append(f"housekeeping_auto: {auto_housekeeping}")
        if auto_housekeeping:
            try:
                from audioknob_gui.core.irq import read_cpu_present

                audio_set = set(cores or [])
                housekeeping = sorted(read_cpu_present() - audio_set)
                hk_list = ",".join(str(c) for c in housekeeping)
                lines.append(f"housekeeping_cores: {hk_list or 'unset'}")
            except Exception:
                lines.append("housekeeping_cores: unknown")
        else:
            manual = ui._kernel_cores_from_state("kernel_irqaffinity") or []
            manual_list = ",".join(str(c) for c in manual)
            lines.append(f"housekeeping_cores: {manual_list or 'unset'}")

        selected, missing = resolve_selected_devices(device_keys)
        if missing:
            lines.append(f"missing_devices: {', '.join(missing)}")
        if selected:
            for device in selected:
                label = str(device.get("label") or device.get("key"))
                bus = str(device.get("bus") or "unknown")
                irqs = device.get("irqs") or []
                lines.append(
                    f"device: {label} [{bus}] irqs={','.join(str(i) for i in irqs) if irqs else 'none'}"
                )
                warning = device.get("warning")
                if warning:
                    lines.append(f"warning: {warning}")
        else:
            lines.append("device: none")

        target_irqs = collect_target_irqs(selected)
        mismatched: list[int] = []
        if target_irqs:
            for irq in target_irqs:
                current = _read_irq_affinity(irq)
                if current is None:
                    lines.append(f"irq[{irq}]: missing")
                else:
                    lines.append(f"irq[{irq}] affinity: {current}")
                    try:
                        from audioknob_gui.core.irq import parse_cpu_list

                        if cores and parse_cpu_list(current) != set(cores):
                            mismatched.append(irq)
                    except Exception:
                        pass
        persist_state_path = str(params.get("persist_state_path", "")).strip()
        persist_state_exists: bool | None = None
        if persist_state_path:
            persist_state_exists = Path(persist_state_path).exists()
            lines.append(f"persist_state_path: {persist_state_path}")
            lines.append(f"persist_state_present: {persist_state_exists}")

        persist_unit = str(params.get("persist_unit", "")).strip()
        persist_enabled: str | None = None
        if persist_unit:
            lines.append(f"persist_unit: {persist_unit}")
            try:
                r = subprocess.run(
                    ["systemctl", "is-enabled", persist_unit],
                    capture_output=True,
                    text=True,
                )
                persist_enabled = r.stdout.strip() or r.stderr.strip() or None
                lines.append(f"persist_unit_enabled: {persist_enabled or 'unknown'}")
            except Exception:
                lines.append("persist_unit_enabled: unknown")
            try:
                r = subprocess.run(
                    ["systemctl", "is-active", persist_unit],
                    capture_output=True,
                    text=True,
                )
                persist_active = r.stdout.strip() or r.stderr.strip() or None
                lines.append(f"persist_unit_active: {persist_active or 'unknown'}")
            except Exception:
                lines.append("persist_unit_active: unknown")
        if status == "partial" and mismatched:
            lines.append(
                f"partial_reason: IRQs not on selected cores: {', '.join(str(i) for i in mismatched)}"
            )
        if status == "partial" and missing:
            lines.append("partial_reason: missing devices (selection not found); check device list.")
        if status == "partial":
            persistence_issues: list[str] = []
            if persist_state_path and persist_state_exists is False:
                persistence_issues.append("persist state file is missing")
            if persist_unit and persist_enabled not in ("enabled", "static", "indirect"):
                persistence_issues.append(
                    f"{persist_unit} is not enabled ({persist_enabled or 'unknown'})"
                )
            if persistence_issues:
                lines.append(
                    "partial_reason: persistence setup incomplete: "
                    + "; ".join(persistence_issues)
                    + "."
                )
        if status == "partial" and cores:
            try:
                from audioknob_gui.core.irq import list_irqs, parse_cpu_list, read_irq_affinity_list

                audio_set = set(cores)
                sweep_ok = True
                for irq in list_irqs():
                    if irq in target_irqs:
                        continue
                    current = read_irq_affinity_list(irq)
                    if current is None:
                        continue
                    if parse_cpu_list(current) & audio_set:
                        sweep_ok = False
                        break
                if not sweep_ok:
                    lines.append(
                        "partial_reason: some non-audio IRQs still target audio cores (housekeeping sweep)."
                    )
            except Exception:
                pass
    elif kind == "rtirq_config":
        from audioknob_gui.core.rtirq import normalize_rtirq_list, rtirq_block_present
        from audioknob_gui.worker.ops import read_os_release, resolve_rtirq_config_path

        distro_id = read_os_release().get("ID", "")
        cfg_path = resolve_rtirq_config_path(distro_id)
        lines.append(f"rtirq_config: {cfg_path}")
        name_list = normalize_rtirq_list(params.get("name_list", ["snd", "usb"]))
        high_list = normalize_rtirq_list(params.get("high_list", name_list))
        prio_high = int(params.get("prio_high", 90))
        prio_decr = int(params.get("prio_decr", 5))
        cfg_ok = False
        try:
            content = Path(cfg_path).read_text(encoding="utf-8")
            cfg_ok = rtirq_block_present(
                content,
                name_list=name_list,
                high_list=high_list,
                prio_high=prio_high,
                prio_decr=prio_decr,
            )
        except Exception:
            cfg_ok = False
        lines.append(f"rtirq_block: {cfg_ok}")
        unit = str(params.get("unit", "rtirq.service"))
        enabled = None
        active = None
        try:
            enabled = subprocess.run(
                ["systemctl", "is-enabled", unit],
                capture_output=True,
                text=True,
            ).stdout.strip() or None
        except Exception:
            enabled = None
        try:
            active = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
            ).stdout.strip() or None
        except Exception:
            active = None
        if enabled is not None:
            lines.append(f"service_enabled: {enabled}")
        if active is not None:
            lines.append(f"service_active: {active}")
        if status == "partial":
            if cfg_ok and active != "active":
                lines.append("partial_reason: config present but rtirq service not active.")
            elif not cfg_ok and active == "active":
                lines.append("partial_reason: rtirq service active but config block missing.")
            elif cfg_ok and enabled not in ("enabled", "static", "indirect"):
                lines.append(
                    f"partial_reason: config present but {unit} is not enabled ({enabled or 'unknown'})."
                )
            else:
                lines.append(
                    "partial_reason: mixed rtirq state "
                    f"(config={cfg_ok}, service_enabled={enabled or 'unknown'}, service_active={active or 'unknown'})."
                )
    elif kind == "power_profile":
        try:
            from audioknob_gui.worker.ops import read_power_profile, select_power_profile_backend
        except Exception:
            read_power_profile = None
            select_power_profile_backend = None
        pref = ui._power_profile_backend_from_state()
        params_local = dict(params)
        params_local["backend"] = pref
        lines.append("")
        lines.append(f"backend_preference: {pref}")
        backend = select_power_profile_backend(params_local) if select_power_profile_backend else None
        if not backend:
            lines.append("resolved_backend: none")
            lines.append("note: powerprofilesctl or tuned-adm required")
        else:
            lines.append(f"resolved_backend: {backend.get('backend')}")
            cmd = backend.get("cmd") or ""
            if cmd:
                lines.append(f"cmd: {cmd}")
            unit = backend.get("service")
            if unit:
                try:
                    r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
                    lines.append(f"service_active: {r.stdout.strip() or r.stderr.strip()}")
                except Exception:
                    pass
            if read_power_profile:
                current = read_power_profile(backend["backend"], backend["cmd"])
                if backend["backend"] == "powerprofilesctl":
                    target = str(params.get("ppd_profile", "performance")).strip() or "performance"
                else:
                    target = str(params.get("tuned_profile", "latency-performance")).strip() or "latency-performance"
                lines.append(f"current: {current or 'unknown'}")
                lines.append(f"target: {target}")
            try:
                if backend["backend"] == "powerprofilesctl":
                    r = subprocess.run([backend["cmd"], "list"], capture_output=True, text=True)
                    output = (r.stdout or r.stderr or "").strip()
                    if output:
                        lines.append("available_profiles:")
                        lines.extend(output.splitlines()[:20])
                elif backend["backend"] == "tuned":
                    r = subprocess.run([backend["cmd"], "list"], capture_output=True, text=True)
                    output = (r.stdout or r.stderr or "").strip()
                    if output:
                        lines.append("available_profiles:")
                        lines.extend(output.splitlines()[:20])
            except Exception:
                pass
    elif kind == "systemd_unit_toggle":
        unit = str(params.get("unit", ""))
        if unit:
            lines.append(f"unit: {unit}")
            for label, cmd in (
                ("is-enabled", ["systemctl", "is-enabled", unit]),
                ("is-active", ["systemctl", "is-active", unit]),
            ):
                r = subprocess.run(cmd, capture_output=True, text=True)
                lines.append(f"{label}: {r.stdout.strip() or r.stderr.strip()}")
    elif kind == "user_service_mask":
        services: list[str] = []
        raw_services = params.get("services")
        if isinstance(raw_services, list):
            try:
                from audioknob_gui.worker.ops import resolve_user_services

                services = resolve_user_services([str(s) for s in raw_services if s])
            except Exception:
                services = [str(s) for s in raw_services if s]
        else:
            unit = str(params.get("unit", "")).strip()
            if unit:
                services = [unit]

        if services:
            lines.append(f"user_services: {', '.join(services)}")
        else:
            lines.append("user units: [no matches]")

        service_states: list[tuple[str, str | None, str | None]] = []
        for svc in services:
            lines.append(f"user unit: {svc}")
            enabled_state: str | None = None
            active_state: str | None = None
            for label, cmd in (
                ("user is-enabled", ["systemctl", "--user", "is-enabled", svc]),
                ("user is-active", ["systemctl", "--user", "is-active", svc]),
            ):
                r = subprocess.run(cmd, capture_output=True, text=True)
                value = r.stdout.strip() or r.stderr.strip() or None
                lines.append(f"{label}: {value or 'unknown'}")
                if label == "user is-enabled":
                    enabled_state = value
                else:
                    active_state = value
            service_states.append((svc, enabled_state, active_state))

        if status == "partial" and service_states:
            masked = [svc for svc, enabled, _ in service_states if enabled == "masked"]
            unmasked = [
                f"{svc} (enabled={enabled or 'unknown'}, active={active or 'unknown'})"
                for svc, enabled, active in service_states
                if enabled != "masked"
            ]
            if unmasked:
                snippet = ", ".join(unmasked[:4])
                suffix = "..." if len(unmasked) > 4 else ""
                lines.append(
                    f"partial_reason: masked {len(masked)}/{len(service_states)} user services; "
                    f"still unmasked: {snippet}{suffix}."
                )
            else:
                lines.append(
                    f"partial_reason: masked {len(masked)}/{len(service_states)} user services; "
                    "some unit states could not be verified."
                )
    elif kind == "sysctl_conf":
        path = str(params.get("path", ""))
        if path:
            lines.extend(_read_file(path))
            if status == "partial":
                wanted_lines = [str(x) for x in params.get("lines", [])]
                try:
                    content = Path(path).read_text(encoding="utf-8")
                    missing = [line for line in wanted_lines if line not in content]
                except Exception:
                    missing = []
                if missing:
                    lines.append(f"partial_reason: missing lines: {', '.join(missing)}")
        keys: list[str] = []
        expected: dict[str, str] = {}
        for line in params.get("lines", []) or []:
            raw = str(line).strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, _, value = raw.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in keys:
                keys.append(key)
                expected[key] = value
        if keys:
            try:
                from audioknob_gui.platform.packages import which_command
            except Exception:
                which_command = None
            sysctl_cmd = None
            if which_command:
                sysctl_cmd = which_command("sysctl")
            if not sysctl_cmd:
                sysctl_cmd = shutil.which("sysctl") or "sysctl"
            for key in keys:
                try:
                    r = subprocess.run([sysctl_cmd, "-n", key], capture_output=True, text=True)
                    current = r.stdout.strip() or r.stderr.strip() or "unknown"
                except Exception as e:
                    current = f"error: {e}"
                exp = expected.get(key)
                if exp is not None:
                    lines.append(f"sysctl {key}: {current} (expected: {exp})")
                else:
                    lines.append(f"sysctl {key}: {current}")
    elif kind == "sysfs_glob_kv":
        pattern = str(params.get("glob", ""))
        if pattern:
            paths = sorted(glob.glob(pattern))
            expected_val = str(params.get("value", "")).strip()
            total = len(paths)
            match = 0
            unreadable = 0
            for p in paths:
                try:
                    raw_val = Path(p).read_text(encoding="utf-8").strip()
                    current_val = _sysfs_selected_value(raw_val)
                    if expected_val and current_val == expected_val:
                        match += 1
                except Exception:
                    unreadable += 1
            mismatch = max(0, total - match - unreadable)
            if expected_val:
                lines.append(
                    f"sysfs_summary: total={total} match={match} mismatch={mismatch} unreadable={unreadable} "
                    f"(expected: {expected_val})"
                )
            else:
                lines.append(f"sysfs_summary: total={total} unreadable={unreadable}")
            for p in paths[:8]:
                try:
                    raw_val = Path(p).read_text(encoding="utf-8").strip()
                    current_val = _sysfs_selected_value(raw_val)
                    if current_val != raw_val:
                        lines.append(f"{p}: {raw_val} (selected: {current_val})")
                    else:
                        lines.append(f"{p}: {raw_val}")
                except Exception as e:
                    lines.append(f"{p}: unreadable: {e}")
            if status == "partial" and knob.id != "cpu_governor_performance_persistent":
                reason = _sysfs_partial_reason(
                    total=total,
                    match=match,
                    mismatch=mismatch,
                    unreadable=unreadable,
                    expected_val=expected_val,
                )
                if reason:
                    lines.append(f"partial_reason: {reason}")
            if knob.id == "cpu_governor_performance_persistent":
                cfg_ok = False
                cfg_read_error: str | None = None
                service: str | None = None
                service_enabled: str | None = None
                try:
                    from audioknob_gui.worker.ops import (
                        read_os_release,
                        resolve_cpupower_config_path,
                        resolve_cpu_governor_service,
                    )

                    os_release = read_os_release()
                    distro_id = os_release.get("ID", "")
                    cfg_path = resolve_cpupower_config_path(distro_id)
                    lines.append(f"cpupower_config: {cfg_path}")
                    try:
                        cfg_text = Path(cfg_path).read_text(encoding="utf-8")
                    except Exception as e:
                        cfg_text = None
                        cfg_read_error = str(e)
                        lines.append(f"cpupower_config_read_error: {e}")
                    if cfg_text:
                        cfg_ok = bool(
                            re.search(
                                r'^\s*GOVERNOR\s*=\s*"?performance"?\s*$',
                                cfg_text,
                                flags=re.MULTILINE,
                            )
                        )
                        for line in cfg_text.splitlines():
                            if "GOVERNOR" in line:
                                lines.append(f"cpupower_config_governor: {line.strip()}")
                                break
                    service = resolve_cpu_governor_service(distro_id)
                    if service:
                        for label, cmd in (
                            ("service_enabled", ["systemctl", "is-enabled", service]),
                            ("service_active", ["systemctl", "is-active", service]),
                        ):
                            r = subprocess.run(cmd, capture_output=True, text=True)
                            value = r.stdout.strip() or r.stderr.strip()
                            if label == "service_enabled":
                                service_enabled = value
                            lines.append(f"{label}: {value}")
                    if status == "partial":
                        reason = _cpu_governor_partial_reason(
                            total=total,
                            match=match,
                            unreadable=unreadable,
                            expected_val=expected_val,
                            cfg_ok=cfg_ok,
                            cfg_read_error=cfg_read_error,
                            service=service,
                            service_enabled=service_enabled,
                        )
                        if reason:
                            lines.append(f"partial_reason: {reason}")
                except Exception:
                    pass
    elif kind == "kernel_cmdline":
        param = str(params.get("param", ""))
        override = ui._kernel_cmdline_param_for_state(knob.id)
        if override:
            param = override
        running_has = None
        boot_has = None
        if param:
            try:
                running = Path("/proc/cmdline").read_text(encoding="utf-8").strip()
                lines.append(f"/proc/cmdline: {running}")
                tokens = running.split()
                running_has = _param_present(tokens, param)
                lines.append(f"/proc/cmdline has {param}: {running_has}")
            except Exception as e:
                lines.append(f"/proc/cmdline read error: {e}")
            try:
                from audioknob_gui.worker.ops import detect_distro
                import shlex

                distro = detect_distro()
                boot_path = distro.kernel_cmdline_file
                if boot_path:
                    boot_text = Path(boot_path).read_text(encoding="utf-8")
                    in_boot = False
                    if distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                        in_boot = _param_present(boot_text.split(), param)
                    elif distro.boot_system == "grub2":
                        for line in boot_text.splitlines():
                            if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                                _, _, rhs = line.partition("=")
                                rhs = rhs.strip().strip('"')
                                try:
                                    tokens = shlex.split(rhs)
                                except Exception:
                                    tokens = rhs.split()
                                in_boot = _param_present(tokens, param)
                                break
                    boot_has = in_boot
                    lines.append(f"{boot_path} has {param}: {in_boot}")
            except Exception as e:
                lines.append(f"boot config read error: {e}")
        if status == "partial" and param and running_has is not None and boot_has is not None:
            if boot_has and not running_has:
                lines.append("partial_reason: boot config set but reboot not applied yet.")
            elif running_has and not boot_has:
                lines.append("partial_reason: running kernel has param but boot config missing.")
            else:
                lines.append("partial_reason: running/boot config mismatch; verify bootloader updates.")
    elif kind == "udev_rule":
        path = str(params.get("path", ""))
        if path:
            lines.extend(_read_file(path))
            expected = str(params.get("content", "")).strip()
            if expected:
                try:
                    current = Path(path).read_text(encoding="utf-8")
                    present = expected in current
                except Exception:
                    present = False
                lines.append(f"expected_rule_present: {present}")
    elif kind == "pipewire_conf":
        path = str(params.get("path", "~/.config/pipewire/pipewire.conf.d/99-audioknob.conf"))
        lines.extend(_read_file(path))
        if status == "partial":
            try:
                from audioknob_gui.worker.ops import build_pipewire_conf_content

                expected = build_pipewire_conf_content(params).splitlines()
                current = Path(path).read_text(encoding="utf-8").splitlines()
                lines.append(f"partial_reason: {_config_partial_reason(expected, current)}")
            except Exception as exc:
                lines.append(f"partial_reason: unable to compare expected config ({exc})")
        try:
            for label, cmd in (
                ("pipewire_active", ["systemctl", "--user", "is-active", "pipewire"]),
                ("wireplumber_active", ["systemctl", "--user", "is-active", "wireplumber"]),
                ("pipewire_pulse_active", ["systemctl", "--user", "is-active", "pipewire-pulse"]),
            ):
                r = subprocess.run(cmd, capture_output=True, text=True)
                lines.append(f"{label}: {r.stdout.strip() or r.stderr.strip()}")
        except Exception:
            pass
        try:
            if shutil.which("pw-metadata"):
                r = subprocess.run(
                    ["pw-metadata", "-n", "settings", "0"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                output = (r.stdout or r.stderr or "").strip()
                if output:
                    clock_rate = None
                    clock_quantum = None
                    for line in output.splitlines():
                        if "clock.rate" in line:
                            match = re.search(r"clock\\.rate\\s*=\\s*(\\d+)", line)
                            if match:
                                clock_rate = match.group(1)
                        if "clock.quantum" in line:
                            match = re.search(r"clock\\.quantum\\s*=\\s*(\\d+)", line)
                            if match:
                                clock_quantum = match.group(1)
                    if clock_rate or clock_quantum:
                        lines.append(
                            f"pipewire_runtime: rate={clock_rate or 'unknown'} "
                            f"quantum={clock_quantum or 'unknown'}"
                        )
        except Exception:
            pass
    elif kind == "wireplumber_conf":
        path = str(
            params.get(
                "path",
                "~/.config/wireplumber/wireplumber.conf.d/90-audioknob-alsa.conf",
            )
        )
        lines.extend(_read_file(path))
        if status == "partial":
            try:
                from audioknob_gui.worker.ops import build_wireplumber_conf_content

                expected = build_wireplumber_conf_content(params).splitlines()
                current = Path(path).read_text(encoding="utf-8").splitlines()
                lines.append(f"partial_reason: {_config_partial_reason(expected, current)}")
            except Exception as exc:
                lines.append(f"partial_reason: unable to compare expected config ({exc})")
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", "wireplumber"],
                capture_output=True,
                text=True,
            )
            lines.append(f"wireplumber_active: {r.stdout.strip() or r.stderr.strip()}")
        except Exception:
            pass
    elif kind == "group_membership":
        r = subprocess.run(["id"], capture_output=True, text=True)
        lines.append(f"id: {r.stdout.strip()}")
        required_groups = params.get("groups", ["audio", "realtime"])
        if isinstance(required_groups, str):
            required_groups = [required_groups]
        required_groups = [str(g) for g in required_groups if str(g).strip()]
        if required_groups:
            lines.append(f"required_groups: {', '.join(required_groups)}")
        try:
            from audioknob_gui.platform.detect import get_missing_groups

            missing = get_missing_groups()
            if missing:
                lines.append(f"missing_groups: {', '.join(missing)}")
            else:
                lines.append("missing_groups: none")
        except Exception:
            pass
        try:
            import grp
            import os
            import pwd

            user_gids = set(os.getgroups())
            user_name = pwd.getpwuid(os.getuid()).pw_name
            primary_gid = os.getgid()
            existing: list[str] = []
            active: list[str] = []
            configured: list[str] = []
            for group_name in required_groups:
                try:
                    gr = grp.getgrnam(group_name)
                except KeyError:
                    continue
                existing.append(group_name)
                if gr.gr_gid in user_gids:
                    active.append(group_name)
                if user_name in gr.gr_mem or gr.gr_gid == primary_gid:
                    configured.append(group_name)

            if existing:
                lines.append(f"existing_groups: {', '.join(existing)}")
                lines.append(f"session_active_groups: {', '.join(active) if active else 'none'}")
                lines.append(f"configured_groups: {', '.join(configured) if configured else 'none'}")

                if status == "partial":
                    missing_active = [g for g in existing if g not in active]
                    missing_configured = [g for g in existing if g not in configured]
                    reason_parts: list[str] = [
                        f"session active for {len(active)}/{len(existing)} groups",
                        f"account configured for {len(configured)}/{len(existing)} groups",
                    ]
                    if missing_active:
                        reason_parts.append(f"missing active groups: {', '.join(missing_active)}")
                    if missing_configured:
                        reason_parts.append(
                            f"missing configured groups: {', '.join(missing_configured)}"
                        )
                    lines.append("partial_reason: " + "; ".join(reason_parts) + ".")
            elif status == "partial":
                lines.append("partial_reason: required groups were not found on this system.")
        except Exception as e:
            lines.append(f"group_check_error: {e}")
    elif kind == "pam_limits_audio_group":
        path = str(params.get("path", ""))
        if path:
            lines.extend(_read_file(path))
            if status == "partial":
                wanted_lines = [str(x) for x in params.get("lines", [])]
                try:
                    content = Path(path).read_text(encoding="utf-8")
                    missing = [line for line in wanted_lines if line not in content]
                except Exception:
                    missing = []
                if missing:
                    lines.append(f"partial_reason: missing lines: {', '.join(missing)}")
        try:
            import resource

            rt_soft, rt_hard = resource.getrlimit(resource.RLIMIT_RTPRIO)
            mem_soft, mem_hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)
            lines.append(f"rtprio: {rt_soft}/{rt_hard}")
            lines.append(f"memlock: {mem_soft}/{mem_hard}")
        except Exception as e:
            lines.append(f"limits read error: {e}")
    elif kind == "baloo_disable":
        cmd = "balooctl6" if shutil.which("balooctl6") else "balooctl"
        lines.append(f"command: {cmd}")
        if shutil.which(cmd):
            r = subprocess.run([cmd, "status"], capture_output=True, text=True)
            lines.append(r.stdout.strip() or r.stderr.strip())
        else:
            lines.append("balooctl not found")
    elif kind == "read_only":
        what = str(params.get("what", "")).strip()
        if what:
            lines.append(f"read_only: {what}")
        if knob.id == "scheduler_jitter_test":
            last = ui.state.get("jitter_test_last")
            if isinstance(last, dict):
                max_us = last.get("max_us")
                threads = last.get("threads")
                lines.append("last_jitter_test:")
                if isinstance(max_us, int):
                    lines.append(f"  max_us: {max_us}")
                if isinstance(threads, list):
                    lines.append(f"  threads: {len(threads)}")

    if status == "partial" and not any(str(line).startswith("partial_reason:") for line in lines):
        lines.append(
            "partial_reason: mixed state detected; one or more live checks above differ from expected values."
        )
    return lines


def show_cli_status(ui, knob_id: str) -> None:
    k = next((k for k in ui.registry if k.id == knob_id), None)
    if not k:
        return

    def _cli_status() -> str:
        try:
            status_data = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        "-m",
                        "audioknob_gui.worker.cli",
                        "--registry",
                        _registry_path(),
                        "status",
                    ],
                    text=True,
                )
            )
            item = next((s for s in status_data.get("statuses", []) if s.get("knob_id") == k.id), None)
            if item:
                return str(item.get("status", "unknown"))
            return "not found"
        except Exception as e:
            return f"error: {e}"

    dialog = QDialog(ui)
    dialog.setWindowTitle(f"{k.title} Status Check")
    dialog.resize(640, 460)
    layout = QVBoxLayout(dialog)

    header = QLabel(f"<b>{k.title}</b>")
    layout.addWidget(header)

    gui_status_label = QLabel(f"GUI status: {ui._knob_statuses.get(k.id, 'unknown')}")
    layout.addWidget(gui_status_label)

    cli_status_label = QLabel("CLI status: (not run yet)")
    layout.addWidget(cli_status_label)

    text = QTextEdit()
    text.setReadOnly(True)
    text.setPlainText("Click Refresh to run CLI status and preview checks.")
    layout.addWidget(text)

    btn_row = QHBoxLayout()
    refresh_btn = QPushButton("Refresh")
    refresh_btn.setFocusPolicy(Qt.NoFocus)
    btn_row.addWidget(refresh_btn)
    btn_row.addStretch(1)
    close_btn = QPushButton("Close")
    close_btn.setFocusPolicy(Qt.NoFocus)
    close_btn.clicked.connect(dialog.reject)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    def _render(payload: dict) -> None:
        gui_status_label.setText(f"GUI status: {ui._knob_statuses.get(k.id, 'unknown')}")
        cli_status_label.setText(f"CLI status: {payload.get('cli_status', 'unknown')}")

        checks = payload.get("live_checks") or []
        baseline_checks = ui.state.get("baseline_checks", {})
        if isinstance(baseline_checks, dict) and baseline_checks.get(k.id):
            checks = list(checks)
            checks.append("")
            checks.append(f"{REFERENCE_PRESET_LABEL.lower()} snapshot:")
            checks.extend(str(x) for x in baseline_checks[k.id])
        text.setPlainText("\n".join(checks))

    def _run_checks() -> None:
        refresh_btn.setEnabled(False)
        cli_status_label.setText("CLI status: running...")
        text.setPlainText("Running CLI checks...")

        def _task():
            return True, {"cli_status": _cli_status(), "live_checks": collect_live_checks(ui, k)}, ""

        worker = QueueTaskWorker(_task, parent=ui)

        def _on_done(success: bool, payload: object, message: str) -> None:
            if not isValid(dialog) or not dialog.isVisible():
                return
            refresh_btn.setEnabled(True)
            if not success:
                cli_status_label.setText(f"CLI status: error: {message or 'unknown'}")
                text.setPlainText(message or "CLI check failed")
                return
            if isinstance(payload, dict):
                _render(payload)
            else:
                text.setPlainText("CLI check returned no data.")

        worker.finished.connect(_on_done)
        worker.finished.connect(worker.deleteLater)
        ui._task_threads.append(worker)
        worker.start()

    refresh_btn.clicked.connect(_run_checks)
    _run_checks()

    dialog.exec()

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QMessageBox, QTextEdit, QVBoxLayout, QPushButton

from audioknob_gui.gui.logging_utils import _get_gui_logger
from audioknob_gui.gui.state import save_state
from audioknob_gui.gui.worker_api import (
    _PKEXEC_CANCELLED,
    _is_force_reset_error,
    _is_no_transaction_error,
    _is_pkexec_cancel,
    _pick_root_worker_path,
    _run_worker_apply_pkexec,
    _run_worker_apply_user,
    _run_worker_force_reset_pkexec,
    _run_worker_force_reset_user,
)


class KnobTaskWorker(QThread):
    finished = Signal(str, str, bool, object, str)

    def __init__(self, knob_id: str, action: str, fn, parent=None) -> None:
        super().__init__(parent)
        self._knob_id = knob_id
        self._action = action
        self._fn = fn

    def run(self) -> None:
        try:
            success, payload, message = self._fn()
        except Exception as e:
            success, payload, message = False, None, str(e)
        self.finished.emit(self._knob_id, self._action, bool(success), payload, message or "")


class QueueTaskWorker(QThread):
    finished = Signal(bool, object, str)

    def __init__(self, fn, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            success, payload, message = self._fn()
        except Exception as e:
            success, payload, message = False, None, str(e)
        self.finished.emit(bool(success), payload, message or "")


def on_apply_knob(ui, knob_id: str) -> None:
    """Apply a single knob optimization."""
    k = next((k for k in ui.registry if k.id == knob_id), None)
    if not k:
        return
    if knob_id in ("kernel_clocksource_tsc", "kernel_tsc_reliable"):
        if not _confirm_tsc_preflight(ui, knob_id):
            return
    if knob_id == "qjackctl_server_prefix_rt" and ui._is_process_running(["qjackctl", "qjackctl6"]):
        QMessageBox.information(
            ui,
            "Close QjackCtl First",
            "Quit QjackCtl before applying QjackCtl RT.\n\n"
            "QjackCtl rewrites its config on exit, which can undo changes.",
        )
        return

    def _task():
        if knob_id == "qjackctl_server_prefix_rt":
            ui._prime_qjackctl_preset()
        if k.requires_root:
            result = _run_worker_apply_pkexec([knob_id])
            return True, {"result": result, "requires_root": True}, ""
        result = _run_worker_apply_user([knob_id])
        return True, {"result": result, "requires_root": False}, ""

    run_knob_task(ui, knob_id, "apply", _task)


def on_queue_knob(ui, knob_id: str, action: str) -> None:
    if knob_id in ui._busy_knobs:
        return
    if action == "apply" and knob_id in ("kernel_clocksource_tsc", "kernel_tsc_reliable"):
        if not _confirm_tsc_preflight(ui, knob_id):
            return
    if ui._queued_actions.get(knob_id) == action:
        ui._queued_actions.pop(knob_id, None)
    else:
        ui._queued_actions[knob_id] = action
    ui._save_queue()
    ui._update_queue_ui()
    ui._populate()


def run_knob_task(ui, knob_id: str, action: str, fn) -> None:
    if knob_id in ui._busy_knobs:
        return
    ui._busy_knobs.add(knob_id)
    ui._knob_statuses[knob_id] = "running"
    ui._populate()

    worker = KnobTaskWorker(knob_id, action, fn, parent=ui)
    worker.finished.connect(ui._on_knob_task_finished)
    worker.finished.connect(worker.deleteLater)
    ui._task_threads.append(worker)
    worker.start()


def on_knob_task_finished(
    ui, knob_id: str, action: str, success: bool, payload: object, message: str
) -> None:
    ui._busy_knobs.discard(knob_id)
    ui._prune_task_threads()

    if success and action == "apply":
        try:
            if isinstance(payload, dict):
                result = payload.get("result", {})
                if payload.get("requires_root"):
                    ui.state["last_root_txid"] = result.get("txid")
                else:
                    ui.state["last_user_txid"] = result.get("txid")
                save_state(ui.state)
        except Exception:
            pass
        if isinstance(payload, dict):
            ui._handle_apply_followups(payload.get("result", {}))

    if not success:
        if message == _PKEXEC_CANCELLED:
            ui._queue_needs_reboot = False
            ui._refresh_statuses()
            ui._populate()
            _get_gui_logger().info("apply queue cancelled")
            return
        if action == "reset" and (_is_no_transaction_error(message) or _is_force_reset_error(message)):
            reason = "reset_no_effect" if _is_force_reset_error(message) else None
            if ui._confirm_force_reset(knob_id, reason=reason):
                ui._run_force_reset(knob_id)
            else:
                ui._refresh_statuses()
                ui._populate()
            return
        if action == "apply":
            _get_gui_logger().error("apply knob failed id=%s error=%s", knob_id, message)
            QMessageBox.critical(ui, "Failed", message or "Unknown error")
        else:
            QMessageBox.warning(ui, "Reset Failed", message or "Unknown error")

    ui._refresh_statuses()
    if success and action == "apply" and knob_id == "rt_limits_audio_group":
        if not ui._rt_limits_active():
            ui._knob_statuses["rt_limits_audio_group"] = "pending_reboot"
            ui._update_reboot_banner()
            QMessageBox.information(
                ui,
                "Reboot Required",
                "RT Limits were applied, but your session does not have them yet.\n\n"
                "Log out/in or reboot to activate.",
            )
    ui._populate()


def _confirm_tsc_preflight(ui, knob_id: str) -> bool:
    current = ""
    available = ""
    flags: set[str] = set()
    dmesg_note = ""
    dmesg_warn = ""

    try:
        current = Path("/sys/devices/system/clocksource/clocksource0/current_clocksource").read_text(
            encoding="utf-8"
        ).strip()
    except Exception:
        current = ""
    try:
        available = Path("/sys/devices/system/clocksource/clocksource0/available_clocksource").read_text(
            encoding="utf-8"
        ).strip()
    except Exception:
        available = ""
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("flags"):
                _, _, raw = line.partition(":")
                flags = set(raw.strip().split())
                break
    except Exception:
        flags = set()
    try:
        result = subprocess.run(["dmesg"], capture_output=True, text=True, check=False, timeout=2)
        if result.stdout:
            dmesg_text = result.stdout.lower()
            if "tsc unstable" in dmesg_text or "marking tsc unstable" in dmesg_text:
                dmesg_warn = "Kernel reported TSC instability."
            else:
                dmesg_note = "No TSC instability warnings found."
        else:
            dmesg_note = "Kernel log not available (permission restricted)."
    except Exception:
        dmesg_note = "Kernel log not available (permission restricted)."

    issues: list[str] = []
    info: list[str] = []

    if not current:
        issues.append("Current clocksource: unknown (could not read).")
    else:
        info.append(f"Current clocksource: {current}")
        if current != "tsc":
            issues.append("Current clocksource is not TSC.")

    if not available:
        issues.append("Available clocksources: unknown (could not read).")
    else:
        info.append(f"Available clocksources: {available}")
        if "tsc" not in available.split():
            issues.append("TSC is not listed as an available clocksource.")

    needs_flags = knob_id == "kernel_tsc_reliable"
    if needs_flags:
        if "constant_tsc" not in flags:
            issues.append("CPU flag missing: constant_tsc")
        if "nonstop_tsc" not in flags:
            issues.append("CPU flag missing: nonstop_tsc")
        if flags:
            present = sorted(f for f in flags if f in {"constant_tsc", "nonstop_tsc"})
            if present:
                info.append("CPU flags include: " + " ".join(present))
        else:
            issues.append("CPU flags could not be read.")

    if dmesg_warn:
        issues.append(dmesg_warn)
    elif dmesg_note:
        info.append(dmesg_note)

    if not issues:
        return True

    label = "TSC pre-flight check warnings"
    if knob_id == "kernel_tsc_reliable":
        label = "TSC reliable pre-flight check warnings"

    msg = label + ":\n\n" + "\n".join(f"• {i}" for i in issues)
    if info:
        msg += "\n\nDetails:\n" + "\n".join(f"- {i}" for i in info)
    msg += "\n\nProceed anyway?"

    box = QMessageBox(ui)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("TSC pre-flight warning")
    box.setText(msg)
    proceed = box.addButton("Proceed", QMessageBox.DestructiveRole)
    box.addButton(QMessageBox.Cancel)
    box.exec()
    return box.clickedButton() == proceed


def run_force_reset(ui, knob_id: str) -> None:
    k = next((k for k in ui.registry if k.id == knob_id), None)
    if not k:
        return

    def _task():
        if k.requires_root:
            result = _run_worker_force_reset_pkexec(knob_id)
        else:
            result = _run_worker_force_reset_user(knob_id)
        return True, {"result": result}, result.get("message", "")

    run_knob_task(ui, knob_id, "force_reset", _task)


def run_force_reset_many(ui, knob_ids: list[str]) -> None:
    by_id = {k.id: k for k in ui.registry}
    for kid in knob_ids:
        ui._busy_knobs.add(kid)
        ui._knob_statuses[kid] = "running"
    ui._populate()
    _get_gui_logger().info("force reset start knobs=%s", ",".join(knob_ids))

    def _task():
        results = []
        errors: list[str] = []
        for kid in knob_ids:
            k = by_id.get(kid)
            if not k:
                errors.append(f"{kid}: unknown knob")
                continue
            try:
                if k.requires_root:
                    result = _run_worker_force_reset_pkexec(kid)
                else:
                    result = _run_worker_force_reset_user(kid)
                results.append(result)
                if not result.get("success", True):
                    msg = result.get("message") or result.get("error") or "force reset failed"
                    errors.append(f"{kid}: {msg}")
            except Exception as e:
                errors.append(f"{kid}: {e}")
        return len(errors) == 0, {"results": results, "errors": errors}, "\n".join(errors)

    worker = QueueTaskWorker(_task, parent=ui)

    def _on_done(success: bool, payload: object, message: str) -> None:
        for kid in knob_ids:
            ui._busy_knobs.discard(kid)
        ui._refresh_statuses()
        ui._populate()
        if success:
            _get_gui_logger().info("force reset done knobs=%s", ",".join(knob_ids))
        else:
            _get_gui_logger().error("force reset failed error=%s", message)
        if not success:
            QMessageBox.warning(
                ui,
                "Force reset incomplete",
                message or "Some knobs failed to reset.",
            )

    worker.finished.connect(_on_done)
    worker.finished.connect(worker.deleteLater)
    ui._task_threads.append(worker)
    worker.start()


def restore_knob_internal(ui, knob_id: str, requires_root: bool) -> tuple[bool, str]:
    """Restore a single knob to its original state."""
    if requires_root:
        try:
            worker = _pick_root_worker_path()
            argv = ["pkexec", worker, "restore-knob", knob_id]
            p = subprocess.run(argv, text=True, capture_output=True)
            if not p.stdout.strip():
                err = p.stderr.strip() or "Unknown error"
                if _is_pkexec_cancel(err):
                    return False, _PKEXEC_CANCELLED
                return False, err
            try:
                result = json.loads(p.stdout)
            except Exception:
                err = p.stderr.strip() or p.stdout.strip() or "Unknown error"
                if _is_pkexec_cancel(err):
                    return False, _PKEXEC_CANCELLED
                return False, err
            if result.get("success"):
                return True, f"Reset {knob_id}"
            errors = result.get("errors") or []
            if errors:
                return False, "\n".join(str(e) for e in errors)
            return False, result.get("error", "Unknown error")
        except Exception as e:
            return False, str(e)
    else:
        try:
            argv = [
                sys.executable,
                "-m",
                "audioknob_gui.worker.cli",
                "restore-knob",
                knob_id,
            ]
            p = subprocess.run(argv, text=True, capture_output=True)
            if not p.stdout.strip():
                err = p.stderr.strip() or "Unknown error"
                if _is_pkexec_cancel(err):
                    return False, _PKEXEC_CANCELLED
                return False, err
            try:
                result = json.loads(p.stdout)
            except Exception:
                err = p.stderr.strip() or p.stdout.strip() or "Unknown error"
                if _is_pkexec_cancel(err):
                    return False, _PKEXEC_CANCELLED
                return False, err
            if result.get("success"):
                return True, f"Reset {knob_id}"
            errors = result.get("errors") or []
            if errors:
                return False, "\n".join(str(e) for e in errors)
            return False, result.get("error", "Unknown error")
        except Exception as e:
            return False, str(e)


def restore_knob(ui, knob_id: str, requires_root: bool) -> tuple[bool, str]:
    """Legacy wrapper for batch restore."""
    return restore_knob_internal(ui, knob_id, requires_root)


def on_reset_defaults(ui) -> None:
    """Reset ALL audioknob-gui changes to system defaults."""
    def _set_reset_ui(busy: bool) -> None:
        btn = getattr(ui, "btn_reset", None)
        action = getattr(ui, "act_factory_reset", None)
        if isinstance(btn, QPushButton):
            btn.setEnabled(not busy)
            btn.setText("Working..." if busy else "Reset All")
        if action is not None:
            action.setEnabled(not busy)
            action.setText("Factory Preset (Working...)" if busy else "Factory Preset (Reset All)...")
    # First, show what will be reset
    _get_gui_logger().info("reset defaults requested")
    try:
        argv = [
            sys.executable,
            "-m",
            "audioknob_gui.worker.cli",
            "list-pending",
        ]
        p = subprocess.run(argv, text=True, capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip() or "list-pending failed")
        changes = json.loads(p.stdout)
    except Exception as e:
        QMessageBox.critical(ui, "Failed", f"Could not list changes: {e}")
        return

    file_count = changes.get("count", 0)
    effects_count = changes.get("effects_count", 0)
    has_root_effects = changes.get("has_root_effects", False)
    has_user_effects = changes.get("has_user_effects", False)

    # Check if there's anything to reset (files OR effects)
    if file_count == 0 and effects_count == 0:
        QMessageBox.information(
            ui,
            "Nothing to reset",
            "No audioknob-gui changes found.\n\n"
            "Either no changes have been applied, or they've already been reset.",
        )
        return

    # Show summary and confirm
    files = changes.get("files", [])
    effects = changes.get("effects", [])
    summary_lines = []

    # List files
    for f in files[:10]:  # Show first 10
        strategy = f.get("reset_strategy", "backup")
        pkg = f.get("package", "")
        line = f"• {f['path']}"
        if strategy == "delete":
            line += " [will delete]"
        elif strategy == "package" and pkg:
            line += f" [restore from {pkg}]"
        else:
            line += " [restore backup]"
        summary_lines.append(line)
    if len(files) > 10:
        summary_lines.append(f"... and {len(files) - 10} more files")

    # List effects
    if effects:
        summary_lines.append("")
        summary_lines.append("Effects to restore:")
        effect_kinds = {}
        for e in effects:
            kind = e.get("kind", "unknown")
            effect_kinds[kind] = effect_kinds.get(kind, 0) + 1
        for kind, count in effect_kinds.items():
            if kind == "sysfs_write":
                summary_lines.append(f"• {count} sysfs value(s)")
            elif kind == "systemd_unit_toggle":
                summary_lines.append(f"• {count} systemd service(s)")
            elif kind == "user_service_mask":
                summary_lines.append(f"• {count} user service mask(s)")
            elif kind == "baloo_disable":
                summary_lines.append("• Baloo indexer")
            elif kind == "kernel_cmdline":
                summary_lines.append(f"• {count} kernel cmdline change(s)")
            else:
                summary_lines.append(f"• {count} {kind} effect(s)")

    confirm_dialog = QDialog(ui)
    confirm_dialog.setWindowTitle("Factory Preset")
    confirm_dialog.resize(600, 350)
    layout = QVBoxLayout(confirm_dialog)

    total_changes = file_count + effects_count
    layout.addWidget(
        QLabel(
            f"<b>Reset {total_changes} change(s) to system defaults?</b><br/><br/>"
            "<i>You'll be prompted for your password if root access is needed.</i>"
        )
    )

    text_widget = QTextEdit()
    text_widget.setReadOnly(True)
    text_widget.setPlainText("\n".join(summary_lines))
    layout.addWidget(text_widget)

    btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
    layout.addWidget(btns)

    confirmed = [False]

    def on_ok() -> None:
        confirmed[0] = True
        confirm_dialog.accept()

    btns.accepted.connect(on_ok)
    btns.rejected.connect(confirm_dialog.reject)

    confirm_dialog.exec()
    if not confirmed[0]:
        return

    # Execute reset in two phases: user-scope first, then root-scope
    root_files = [f for f in files if f.get("scope") == "root"]
    needs_root = bool(root_files) or has_root_effects

    _set_reset_ui(True)

    def _task() -> tuple[bool, object, str]:
        results_text: list[str] = []
        errors: list[str] = []
        needs_reboot = False

        # Phase 1: User-scope reset (no pkexec needed)
        try:
            argv = [
                sys.executable,
                "-m",
                "audioknob_gui.worker.cli",
                "reset-defaults",
                "--scope",
                "user",
            ]
            p = subprocess.run(argv, text=True, capture_output=True, timeout=120)
            parsed = None
            stdout_text = (p.stdout or "").strip()
            if stdout_text:
                try:
                    parsed = json.loads(stdout_text)
                except json.JSONDecodeError:
                    parsed = None
            if parsed is not None:
                if parsed.get("reset_count", 0) > 0:
                    results_text.append(f"Reset {parsed['reset_count']} user file(s)")
                errors.extend(parsed.get("errors", []))
                needs_reboot = bool(parsed.get("needs_reboot", False)) or needs_reboot
            elif p.returncode != 0:
                err_msg = p.stderr.strip() or stdout_text or f"Exit code {p.returncode}"
                errors.append(f"User reset failed: {err_msg}")
            elif stdout_text:
                errors.append("User reset: invalid response")
        except Exception as e:
            errors.append(f"User reset failed: {e}")

        # Phase 2: Root-scope reset (needs pkexec)
        if needs_root:
            try:
                worker = _pick_root_worker_path()
                argv = [
                    "pkexec",
                    worker,
                    "reset-defaults",
                    "--scope",
                    "root",
                ]
                p = subprocess.run(argv, text=True, capture_output=True, timeout=300)
                parsed = None
                stdout_text = (p.stdout or "").strip()
                if stdout_text:
                    try:
                        parsed = json.loads(stdout_text)
                    except json.JSONDecodeError:
                        parsed = None
                if parsed is not None:
                    if parsed.get("reset_count", 0) > 0:
                        results_text.append(f"Reset {parsed['reset_count']} system file(s)")
                    errors.extend(parsed.get("errors", []))
                    needs_reboot = bool(parsed.get("needs_reboot", False)) or needs_reboot
                elif p.returncode != 0:
                    err_msg = p.stderr.strip() or stdout_text or f"Exit code {p.returncode}"
                    errors.append(f"Root reset failed: {err_msg}")
                elif stdout_text:
                    errors.append("Root reset: invalid response")
            except Exception as e:
                errors.append(f"Root reset failed: {e}")

        return True, {"results_text": results_text, "errors": errors, "needs_reboot": needs_reboot}, ""

    worker = QueueTaskWorker(_task, parent=ui)

    def _on_done(success: bool, payload: object, message: str) -> None:
        _set_reset_ui(False)

        results_text: list[str] = []
        errors: list[str] = []
        needs_reboot = False
        if isinstance(payload, dict):
            results_text = payload.get("results_text") or []
            errors = payload.get("errors") or []
            needs_reboot = bool(payload.get("needs_reboot", False))
        elif message:
            errors = [message]

        # Clear all stored txids
        ui.state["last_txid"] = None
        ui.state["last_user_txid"] = None
        ui.state["last_root_txid"] = None
        ui._queued_actions = {}
        ui.state["queued_actions"] = {}
        save_state(ui.state)
        ui._update_queue_ui()

        # Refresh the UI to show updated status
        ui._refresh_statuses()
        ui._populate()

        # Show results
        if errors:
            _get_gui_logger().error("reset defaults failed error=%s", "; ".join(errors))
            reboot_note = (
                "\n\nReboot required to finish kernel cmdline resets." if needs_reboot else ""
            )
            QMessageBox.warning(
                ui,
                "Factory Preset (with errors)",
                "\n".join(results_text)
                + "\n\nErrors:\n"
                + "\n".join(errors[:5])
                + reboot_note,
            )
        else:
            _get_gui_logger().info("reset defaults done")
            reboot_note = (
                "\n\nReboot required to finish kernel cmdline resets." if needs_reboot else ""
            )
            QMessageBox.information(
                ui,
                "Factory Preset complete",
                "All audioknob-gui changes have been reset to system defaults.\n\n"
                + "\n".join(results_text)
                + reboot_note,
            )

    worker.finished.connect(_on_done)
    worker.finished.connect(worker.deleteLater)
    ui._task_threads.append(worker)
    worker.start()

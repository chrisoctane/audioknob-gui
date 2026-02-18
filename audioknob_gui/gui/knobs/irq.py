from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton

from audioknob_gui.gui.dialogs.irq_pinning import IrqPinningDialog
from audioknob_gui.gui.state import save_state


def build_config_button(ui, knob_id: str) -> QPushButton:
    btn = ui._make_action_button("Devices")
    btn.setToolTip("Configure devices and CPU cores")
    btn.setFocusPolicy(Qt.NoFocus)
    btn.clicked.connect(lambda _, kid=knob_id: ui.on_configure_knob(kid))
    return btn


def configure_dialog(ui) -> None:
    from audioknob_gui.core.irq import list_audio_devices
    from audioknob_gui.platform.detect import get_cpu_count
    from audioknob_gui.gui.logging_utils import _get_gui_logger

    devices = list_audio_devices()
    if not devices:
        QMessageBox.warning(
            ui,
            "No audio devices",
            "No audio devices were detected. Connect a device and try again.",
        )
        return

    cpu_count = get_cpu_count()
    selected_devices = set(ui._irq_pinning_devices_from_state())
    selected_cores = set(ui._irq_pinning_cpu_cores_from_state() or [])

    dialog = IrqPinningDialog(
        cpu_count=cpu_count,
        selected_cores=selected_cores,
        devices=devices,
        selected_devices=selected_devices,
        parent=ui,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    chosen_devices = dialog.selected_device_keys()
    chosen_cores = dialog.selected_core_list()
    ui.state["irq_pinning_devices"] = chosen_devices
    role = None
    role_fn = getattr(ui, "_core_plan_role_for_knob", None)
    if callable(role_fn):
        role = role_fn("irq_pinning")
    linked_apply = getattr(ui, "_apply_linked_core_plan", None)
    linked = bool(ui.state.get("core_plan_linked", True))
    linked_used = False
    if linked and role in ("audio", "housekeeping") and callable(linked_apply):
        linked_apply(source=role, cores=chosen_cores)
        linked_used = True
    else:
        ui.state["irq_pinning_cpu_cores"] = chosen_cores
    save_state(ui.state)
    ui._sync_core_plan_controls()

    status = ui._knob_statuses.get("irq_pinning")
    if status in ("applied", "pending_reboot"):
        _get_gui_logger().info("irq pinning config updated; reapplying")
        ui._on_apply_knob("irq_pinning")
        return
    QMessageBox.information(
        ui,
        "Saved",
        ("Saved linked core plan from IRQ pinning." if linked_used else "Saved IRQ pinning configuration.")
        + (f" Devices: {len(chosen_devices)}" if chosen_devices else " (no devices)")
        + (f" Cores: {','.join(map(str, chosen_cores))}" if chosen_cores else " (no cores)"),
    )


def info_extra_html(ui, helpers) -> str:
    extra = ""
    try:
        active = subprocess.run(
            ["systemctl", "is-active", "irqbalance.service"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        if active == "active":
            extra += "<hr/><p><b>Warning:</b> irqbalance is active and can override IRQ pinning.</p>"
        device_keys = ui._irq_pinning_devices_from_state()
        if device_keys:
            try:
                from audioknob_gui.core.irq import collect_target_irqs, resolve_selected_devices

                selected, _missing = resolve_selected_devices(device_keys)
                target_irqs = collect_target_irqs(selected)
            except Exception:
                target_irqs = []
            if target_irqs:
                irq_lines = helpers.read_interrupts_map()
                extra += "<hr/><p><b>IRQ lines (from /proc/interrupts):</b></p><pre>"
                for irq in sorted(set(target_irqs)):
                    line = irq_lines.get(irq, "")
                    if line:
                        shared = " (shared?)" if "," in line else ""
                        extra += f"IRQ {irq}: {helpers.html_escape(line)}{shared}\n"
                    else:
                        extra += f"IRQ {irq}: not found\n"
                extra += "</pre>"
                extra += "<p>If a line lists multiple devices (comma-separated), the IRQ is shared.</p>"
    except Exception:
        pass
    return extra


def apply_param_overrides(ui, params: dict) -> None:
    devices = ui._irq_pinning_devices_from_state()
    cores = ui._irq_pinning_cpu_cores_from_state()
    if devices:
        params["device_keys"] = devices
    if cores is not None:
        params["cpu_cores"] = ",".join(str(c) for c in cores)


def add_info_buttons(ui, knob, dialog, layout) -> None:
    config_btn = QPushButton("Configure IRQ Pinning...")
    config_btn.clicked.connect(lambda: (dialog.accept(), ui.on_configure_knob(knob.id)))
    layout.addWidget(config_btn)

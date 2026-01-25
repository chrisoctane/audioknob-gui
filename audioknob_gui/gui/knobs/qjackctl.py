from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPushButton

from audioknob_gui.gui.dialogs.cpu_cores import CpuCoreDialog
from audioknob_gui.gui.state import save_state


def build_config_button(ui, knob_id: str) -> QPushButton:
    btn = ui._make_action_button("Cores")
    btn.setToolTip("Configure CPU cores for pinning")
    btn.setFocusPolicy(Qt.NoFocus)
    btn.clicked.connect(lambda _, kid=knob_id: ui.on_configure_knob(kid))
    return btn


def configure_dialog(ui) -> None:
    from audioknob_gui.platform.detect import get_cpu_count
    from audioknob_gui.gui.logging_utils import _get_gui_logger

    cpu_count = get_cpu_count()
    selected = set(ui._qjackctl_cpu_cores_from_state() or [])
    lines = [
        "Select CPU cores to pin JACK to (taskset -c).",
        "Tip: cores 0-1 are often busiest (IRQs/system tasks).",
    ]
    smt_line = ui._smt_hint_line()
    if smt_line:
        lines.append(smt_line)
    dialog = CpuCoreDialog(cpu_count=cpu_count, selected=selected, lines=lines, parent=ui)
    if dialog.exec() != dialog.Accepted:
        return

    chosen = dialog.selected_cores()
    # Empty selection means "no pinning" (remove taskset prefix).
    # None (unset) means "don't override existing pinning".
    ui.state["qjackctl_cpu_cores"] = chosen
    save_state(ui.state)
    status = ui._knob_statuses.get("qjackctl_server_prefix_rt")
    if status in ("applied", "pending_reboot"):
        _get_gui_logger().info("qjackctl cores updated; reapplying")
        ui._on_apply_knob("qjackctl_server_prefix_rt")
        return
    QMessageBox.information(
        ui,
        "Saved",
        "Saved CPU core selection for QjackCtl."
        + (f" Cores: {','.join(map(str, chosen))}" if chosen else " (no pinning)"),
    )


def info_extra_html(ui) -> str:
    extra = ""
    if ui._is_process_running(["qjackctl", "qjackctl6"]):
        extra += (
            "<hr/><p><b>Note:</b> Quit QjackCtl before applying this knob. "
            "QjackCtl rewrites its config on exit.</p>"
        )
    extra += (
        "<hr/><p><b>Buffer math:</b> total buffer = frames/period × periods/buffer. "
        "Lower values reduce latency but increase xrun risk. "
        "Periods/buffer = 2 is typical; 3 is safer; 1 is often unstable.</p>"
    )
    return extra


def add_info_buttons(ui, knob, dialog, layout) -> None:
    config_btn = QPushButton("Configure CPU Cores...")
    config_btn.clicked.connect(lambda: (dialog.accept(), ui.on_configure_knob(knob.id)))
    layout.addWidget(config_btn)

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton

from audioknob_gui.gui.dialogs.cpu_cores import CpuCoreDialog
from audioknob_gui.gui.state import save_state


def build_config_button(ui, knob_id: str) -> QPushButton:
    btn = ui._make_action_button("Cores")
    btn.setToolTip("Configure CPU cores")
    btn.setFocusPolicy(Qt.NoFocus)
    btn.clicked.connect(lambda _, kid=knob_id: ui.on_configure_knob(kid))
    return btn


def configure_core_dialog(ui, knob_id: str) -> None:
    from audioknob_gui.platform.detect import get_cpu_count
    from audioknob_gui.gui.logging_utils import _get_gui_logger

    cpu_count = get_cpu_count()
    allow_auto = knob_id == "kernel_irqaffinity"
    auto_enabled = bool(ui.state.get("irq_housekeeping_auto", True))
    selected = set(ui._kernel_cores_from_state(knob_id) or [])
    titles = {
        "kernel_isolcpus": "Configure isolcpus cores",
        "kernel_nohz_full": "Configure nohz_full cores",
        "kernel_rcu_nocbs": "Configure rcu_nocbs cores",
        "kernel_irqaffinity": "Configure irqaffinity cores",
    }
    lines = {
        "kernel_isolcpus": [
            "Select CPU cores to isolate from the scheduler.",
            "These cores should be reserved for audio workloads.",
        ],
        "kernel_nohz_full": [
            "Select CPU cores for full tickless mode.",
            "Use the same isolated cores for best results.",
        ],
        "kernel_rcu_nocbs": [
            "Select CPU cores to offload RCU callbacks.",
            "Use the same isolated cores for best results.",
        ],
        "kernel_irqaffinity": [
            "Select housekeeping cores for default IRQ handling.",
            "Use non-isolated cores to keep IRQs off audio cores.",
        ],
    }
    dialog_lines = list(lines.get(knob_id) or [])
    smt_line = ui._smt_hint_line()
    if smt_line:
        dialog_lines.append(smt_line)
    auto_hint = None
    auto_label = None
    if allow_auto:
        audio_cores = set(ui._irq_pinning_cpu_cores_from_state() or [])
        auto_label = "Auto housekeeping (invert audio cores)"
        auto_hint = "Auto uses IRQ Pinning audio cores to remove them from housekeeping."
        if audio_cores:
            audio_list = ",".join(str(c) for c in sorted(audio_cores))
            auto_hint += f" Audio cores: {audio_list}."
            housekeeping = sorted(set(range(cpu_count)) - audio_cores)
            if housekeeping:
                hk_list = ",".join(str(c) for c in housekeeping)
                auto_hint += f" Housekeeping: {hk_list}."
        if auto_enabled:
            if audio_cores:
                selected = set(range(cpu_count)) - audio_cores
            else:
                selected = set(range(cpu_count))
    dialog = CpuCoreDialog(
        cpu_count=cpu_count,
        selected=selected,
        allow_auto=allow_auto,
        auto_enabled=auto_enabled,
        auto_label=auto_label,
        auto_hint=auto_hint,
        title=titles.get(knob_id, "Configure CPU cores"),
        lines=dialog_lines,
        parent=ui,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    chosen = dialog.selected_cores()
    if allow_auto:
        ui.state["irq_housekeeping_auto"] = dialog.auto_enabled()
    key = ui._kernel_core_key(knob_id)
    if key:
        ui.state[key] = chosen
        save_state(ui.state)
        ui._sync_core_plan_controls()

    status = ui._knob_statuses.get(knob_id)
    if status in ("applied", "pending_reboot"):
        _get_gui_logger().info("%s cores updated; reapplying", knob_id)
        ui._on_apply_knob(knob_id)
        return
    if allow_auto and ui.state.get("irq_housekeeping_auto"):
        QMessageBox.information(ui, "Saved", "Saved IRQ housekeeping configuration (auto).")
        return
    QMessageBox.information(
        ui,
        "Saved",
        "Saved CPU core selection."
        + (f" Cores: {','.join(map(str, chosen))}" if chosen else " (no cores)"),
    )


def apply_param_overrides(ui, knob, params: dict) -> None:
    if knob.id in ("kernel_isolcpus", "kernel_nohz_full", "kernel_rcu_nocbs", "kernel_irqaffinity"):
        override = ui._kernel_cmdline_param_for_state(knob.id)
        if override:
            params["param"] = override


def cpu_layout_extra_html(ui, helpers) -> str:
    extra = ""
    try:
        from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups

        groups = read_thread_sibling_groups()
        logical = len(read_cpu_present() or [])
        physical = len(groups)
        smt = any(len(g) > 1 for g in groups)
        group_chunks: list[str] = []
        for group in groups[:8]:
            group_chunks.append("(" + ",".join(str(c) for c in group) + ")")
        if len(groups) > 8:
            group_chunks.append(f"(+{len(groups) - 8} more)")
        layout_line = ""
        if group_chunks:
            layout_line = "Sibling groups: " + " ".join(group_chunks)
        extra += "<hr/><p><b>CPU core layout:</b></p>"
        if smt and logical:
            extra += (
                f"<p>SMT detected: {physical} physical / {logical} logical cores.</p>"
                "<p>For best isolation, select both siblings from a physical core.</p>"
            )
        else:
            extra += "<p>SMT/Hyper-Threading not detected.</p>"
        if layout_line:
            extra += f"<p>{layout_line}</p>"
    except Exception:
        pass
    return extra


def threadirqs_extra_html(helpers) -> str:
    extra = ""
    extra += (
        "<p>Note: threadirqs makes IRQ handlers schedulable threads "
        "but does not change CPU topology.</p>"
    )
    extra += (
        "<p>Pairing tip: Enable RTIRQ to raise IRQ thread priorities once IRQs are threaded.</p>"
    )
    return extra


def rtirq_extra_html(helpers) -> str:
    extra = ""
    tokens = helpers.kernel_cmdline_tokens()
    threaded = helpers.param_present(tokens, "threadirqs")
    rt_kernel = helpers.kernel_is_rt()
    if threaded or rt_kernel:
        extra += "<p>Threaded IRQs detected; RTIRQ can raise IRQ thread priorities.</p>"
    else:
        extra += (
            "<p><b>Warning:</b> RTIRQ only affects threaded IRQs. "
            "Enable Threaded IRQs or use an RT kernel for RTIRQ to take effect.</p>"
        )
    return extra


def rt_throttling_extra_html() -> str:
    from pathlib import Path
    import html as html_lib

    extra = ""
    try:
        value = Path("/proc/sys/kernel/sched_rt_runtime_us").read_text(encoding="utf-8").strip()
        extra += (
            "<hr/><p><b>Current sched_rt_runtime_us:</b> "
            f"{html_lib.escape(value)}</p>"
        )
        extra += (
            "<p><b>Warning:</b> disabling RT throttling can let runaway RT tasks "
            "starve the system and may block suspend. Reset before sleep if needed.</p>"
        )
    except Exception:
        pass
    return extra


def cstate_extra_html(ui, knob_id: str) -> str:
    from pathlib import Path
    import html as html_lib

    extra = ""
    driver = None
    try:
        driver = Path("/sys/devices/system/cpu/cpu0/cpuidle/current_driver").read_text(encoding="utf-8").strip()
    except Exception:
        driver = None
    extra += "<hr/><p><b>CPU idle driver:</b> "
    extra += html_lib.escape(driver) if driver else "unknown"
    extra += "</p>"
    if knob_id == "kernel_cstate_limit" and driver == "intel_idle":
        extra += "<p><b>Note:</b> intel_idle is active. The Intel C-States knob may be more effective.</p>"
    if knob_id == "kernel_intel_idle_cstate_limit" and driver and driver != "intel_idle":
        extra += "<p><b>Note:</b> intel_idle is not active on this system.</p>"
    extra += "<p>Limiting C-states can increase power draw and heat. Reset if needed.</p>"
    extra += "<p><b>Warning:</b> limiting C-states can keep fans running and may affect suspend behavior.</p>"
    return extra

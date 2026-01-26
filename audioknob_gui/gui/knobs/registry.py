from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import QPushButton

from audioknob_gui.gui.knobs import irq, kernel, pipewire, power_profile, qjackctl, testing


@dataclass(frozen=True)
class RowContext:
    row: int
    status: str
    busy: bool
    locked: bool
    row_dim: bool
    lock_reason: str
    not_applicable: bool
    not_applicable_reason: str
    group_pending_lock: bool
    reboot_dep_lock: bool
    reboot_gate_lock: bool
    advanced_gate_lock: bool
    commands_ok: bool
    missing_cmds: list[str]


@dataclass(frozen=True)
class InfoHelpers:
    kernel_cmdline_tokens: Callable[[], list[str]]
    param_present: Callable[[list[str], str], bool]
    kernel_is_rt: Callable[[], bool]
    read_interrupts_map: Callable[[], dict[int, str]]
    fmt_jitter_value: Callable[[object], str]
    html_escape: Callable[[str], str]


_KERNEL_CORE_KNOBS = {
    "kernel_isolcpus",
    "kernel_nohz_full",
    "kernel_rcu_nocbs",
    "kernel_irqaffinity",
}


def get_action_override(knob_id: str):
    if knob_id == "audio_group_membership":
        return ("pre_lock", _action_group_membership)
    if knob_id == "stack_detect":
        return ("post_lock", _action_stack_detect)
    if knob_id == "scheduler_jitter_test":
        return ("post_lock", testing.build_test_action)
    if knob_id == "pipewire_xrun_monitor":
        return ("post_lock", pipewire.build_xrun_monitor_action)
    if knob_id == "rtkit_daemon_tuning":
        return ("post_lock", pipewire.build_rtkit_info_action)
    if knob_id == "blocker_check":
        return ("post_lock", _action_blocker_check)
    return (None, None)


def get_config_widget_builder(knob_id: str):
    if knob_id == "pipewire_quantum":
        return pipewire.build_quantum_combo
    if knob_id == "pipewire_sample_rate":
        return pipewire.build_sample_rate_combo
    if knob_id == "pipewire_clock_constraints":
        return lambda ui, knob, ctx: pipewire.build_config_button(ui, knob.id, "Configure...")
    if knob_id == "pipewire_mlock_policy":
        return lambda ui, knob, ctx: pipewire.build_config_button(ui, knob.id, "Configure...")
    if knob_id == "pipewire_rt_module_tuning":
        return lambda ui, knob, ctx: pipewire.build_config_button(ui, knob.id, "Configure...")
    if knob_id == "pipewire_data_loop_affinity":
        return lambda ui, knob, ctx: pipewire.build_config_button(ui, knob.id, "Configure...")
    if knob_id == "pipewire_rt_limits_group":
        return lambda ui, knob, ctx: pipewire.build_config_button(ui, knob.id, "Select Group...")
    if knob_id == "wireplumber_alsa_usb_tuning":
        return lambda ui, knob, ctx: pipewire.build_config_button(ui, knob.id, "Configure...")
    if knob_id == "pipewire_pro_audio_profile":
        return lambda ui, knob, ctx: pipewire.build_config_button(ui, knob.id, "Select Device...")
    if knob_id == "power_profile_performance":
        return power_profile.build_backend_combo
    if knob_id == "qjackctl_server_prefix_rt":
        return lambda ui, knob, ctx: qjackctl.build_config_button(ui, knob.id)
    if knob_id == "irq_pinning":
        return lambda ui, knob, ctx: irq.build_config_button(ui, knob.id)
    if knob_id in _KERNEL_CORE_KNOBS:
        return lambda ui, knob, ctx: kernel.build_config_button(ui, knob.id)
    return None


def allow_config_when_row_dim(knob_id: str, ctx: RowContext) -> bool:
    if knob_id == "power_profile_performance":
        return power_profile.allow_config_when_row_dim(ctx)
    return False


def handle_configure_knob(ui, knob_id: str) -> bool:
    if knob_id == "qjackctl_server_prefix_rt":
        qjackctl.configure_dialog(ui)
        return True
    if knob_id == "irq_pinning":
        irq.configure_dialog(ui)
        return True
    if knob_id in _KERNEL_CORE_KNOBS:
        kernel.configure_core_dialog(ui, knob_id)
        return True
    if knob_id == "pipewire_quantum":
        pipewire.configure_quantum_dialog(ui)
        return True
    if knob_id == "pipewire_sample_rate":
        pipewire.configure_sample_rate_dialog(ui)
        return True
    if knob_id == "pipewire_clock_constraints":
        pipewire.configure_clock_constraints_dialog(ui)
        return True
    if knob_id == "pipewire_mlock_policy":
        pipewire.configure_mlock_dialog(ui)
        return True
    if knob_id == "pipewire_rt_limits_group":
        pipewire.configure_rt_limits_group_dialog(ui)
        return True
    if knob_id == "pipewire_rt_module_tuning":
        pipewire.configure_rt_module_dialog(ui)
        return True
    if knob_id == "pipewire_data_loop_affinity":
        pipewire.configure_data_loops_dialog(ui)
        return True
    if knob_id == "wireplumber_alsa_usb_tuning":
        pipewire.configure_wireplumber_alsa_dialog(ui)
        return True
    if knob_id == "pipewire_pro_audio_profile":
        pipewire.configure_pro_audio_dialog(ui)
        return True
    return False


def apply_info_param_overrides(ui, knob, params: dict) -> None:
    if knob.id in (
        "pipewire_quantum",
        "pipewire_sample_rate",
        "pipewire_clock_constraints",
        "pipewire_mlock_policy",
        "pipewire_rt_limits_group",
        "pipewire_rt_module_tuning",
        "pipewire_data_loop_affinity",
        "wireplumber_alsa_usb_tuning",
        "pipewire_pro_audio_profile",
    ):
        pipewire.apply_param_overrides(ui, knob, params)
    if knob.id == "irq_pinning":
        irq.apply_param_overrides(ui, params)
    if knob.id == "power_profile_performance":
        power_profile.apply_param_overrides(ui, params)
    if knob.id in _KERNEL_CORE_KNOBS:
        kernel.apply_param_overrides(ui, knob, params)


def build_info_extra_html(ui, knob, helpers: InfoHelpers) -> str:
    parts: list[str] = []
    if knob.id == "scheduler_jitter_test":
        parts.append(testing.info_extra_html(ui, helpers))
    if knob.id == "qjackctl_server_prefix_rt":
        parts.append(qjackctl.info_extra_html(ui))
    if knob.id in (
        "qjackctl_server_prefix_rt",
        "irq_pinning",
        "kernel_isolcpus",
        "kernel_nohz_full",
        "kernel_rcu_nocbs",
        "kernel_irqaffinity",
        "kernel_threadirqs",
        "rtirq_enable",
    ):
        parts.append(kernel.cpu_layout_extra_html(ui, helpers))
        if knob.id == "kernel_threadirqs":
            parts.append(kernel.threadirqs_extra_html(helpers))
        if knob.id == "rtirq_enable":
            parts.append(kernel.rtirq_extra_html(helpers))
    if knob.id == "irq_pinning":
        parts.append(irq.info_extra_html(ui, helpers))
    if knob.id == "rt_limits_audio_group":
        parts.append(_rt_limits_extra_html())
    if knob.id == "kernel_rt_throttling_off":
        parts.append(kernel.rt_throttling_extra_html())
    if knob.id in ("kernel_cstate_limit", "kernel_intel_idle_cstate_limit"):
        parts.append(kernel.cstate_extra_html(ui, knob.id))
    if knob.id == "power_profile_performance":
        parts.append(power_profile.info_extra_html(ui, knob))
    return "".join(parts)


def add_info_buttons(ui, knob, dialog, layout) -> None:
    if knob.id == "qjackctl_server_prefix_rt":
        qjackctl.add_info_buttons(ui, knob, dialog, layout)
    if knob.id in (
        "pipewire_quantum",
        "pipewire_sample_rate",
        "pipewire_clock_constraints",
        "pipewire_mlock_policy",
        "pipewire_rt_limits_group",
        "pipewire_rt_module_tuning",
        "pipewire_data_loop_affinity",
        "wireplumber_alsa_usb_tuning",
        "pipewire_pro_audio_profile",
    ):
        pipewire.add_info_buttons(ui, knob, dialog, layout)
    if knob.id == "irq_pinning":
        irq.add_info_buttons(ui, knob, dialog, layout)
    if knob.id in _KERNEL_CORE_KNOBS:
        _add_kernel_core_button(ui, knob, dialog, layout)
    if knob.id == "scheduler_jitter_test":
        testing.add_info_buttons(ui, knob, dialog, layout)


def _action_group_membership(ui, knob, ctx: RowContext) -> QPushButton:
    label = "Leave" if ctx.status == "applied" else "Join"
    btn = ui._make_reset_button(label) if label == "Leave" else ui._make_apply_button(label)
    if label == "Leave":
        btn.clicked.connect(ui._on_leave_groups)
    else:
        btn.clicked.connect(ui._on_join_groups)
    ui._apply_busy_state(btn, busy=ctx.busy)
    return btn


def _action_stack_detect(ui, knob, ctx: RowContext) -> QPushButton:
    btn = ui._make_action_button("View")
    btn.clicked.connect(ui.on_view_stack)
    return btn


def _action_blocker_check(ui, knob, ctx: RowContext) -> QPushButton:
    btn = ui._make_action_button("Scan")
    btn.clicked.connect(ui.on_check_blockers)
    return btn


def _add_kernel_core_button(ui, knob, dialog, layout) -> None:
    config_btn = QPushButton("Configure CPU Cores...")
    config_btn.clicked.connect(lambda: (dialog.accept(), ui.on_configure_knob(knob.id)))
    layout.addWidget(config_btn)


def _rt_limits_extra_html() -> str:
    try:
        import resource
    except Exception:
        return ""

    try:
        rt_soft, rt_hard = resource.getrlimit(resource.RLIMIT_RTPRIO)
        mem_soft, mem_hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)
    except Exception:
        return ""

    def _limit_str(value: int) -> str:
        if value == resource.RLIM_INFINITY:
            return "unlimited"
        return str(value)

    extra = "<hr/><p><b>Session limits (ulimit):</b></p>"
    extra += (
        f"<p>rtprio: {_limit_str(rt_soft)} (soft), {_limit_str(rt_hard)} (hard)<br/>"
        f"memlock: {_limit_str(mem_soft)} (soft), {_limit_str(mem_hard)} (hard)</p>"
    )
    extra += "<p>Note: limits apply after log out/in or reboot.</p>"
    return extra

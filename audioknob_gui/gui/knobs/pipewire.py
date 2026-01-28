from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QMessageBox, QPushButton, QSizePolicy, QWidget

from audioknob_gui.gui.dialogs.pipewire import (
    PipeWireClockConstraintsDialog,
    PipeWireDataLoopsDialog,
    PipeWireMlockDialog,
    PipeWireQuantumDialog,
    PipeWireRtLimitsGroupDialog,
    PipeWireRtSetupDialog,
    PipeWireRtModuleDialog,
    PipeWireSampleRateDialog,
    ProAudioProfileDialog,
    WirePlumberAlsaDialog,
)
from audioknob_gui.gui.state import save_state


def build_config_button(ui, knob_id: str, label: str = "Configure...") -> QPushButton:
    btn = QPushButton(label)
    btn.clicked.connect(lambda: ui.on_configure_knob(knob_id))
    btn.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
    return btn


def build_quantum_combo(ui, knob, ctx) -> QComboBox | None:
    if ctx.locked:
        return None
    combo = QComboBox()
    combo.setMinimumWidth(0)
    combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
    values = [32, 64, 128, 256, 512, 1024]
    for v in values:
        combo.addItem(str(v), v)

    current = ui._pipewire_quantum_from_state()
    if current is None and knob.impl:
        try:
            current = int(knob.impl.params.get("quantum")) if knob.impl.params.get("quantum") is not None else None
        except Exception:
            current = None
    combo.blockSignals(True)
    if current in values:
        combo.setCurrentIndex(values.index(int(current)))
    combo.blockSignals(False)

    def _on_change(_: int, *, _combo: QComboBox = combo) -> None:
        # Capture the correct combo; otherwise a later reassignment can cause late-binding bugs.
        ui.state["pipewire_quantum"] = int(_combo.currentData())
        save_state(ui.state)
        # Optimistic UI: config changed, so action should become Apply until proven otherwise.
        ui._knob_statuses["pipewire_quantum"] = "not_applied"
        ui._refresh_statuses()
        ui._populate()

    combo.currentIndexChanged.connect(_on_change)
    return combo


def build_sample_rate_combo(ui, knob, ctx) -> QComboBox | None:
    if ctx.locked:
        return None
    combo = QComboBox()
    combo.setMinimumWidth(0)
    combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
    values = [44100, 48000, 88200, 96000, 192000]
    for v in values:
        combo.addItem(f"{v} Hz", v)

    current = ui._pipewire_sample_rate_from_state()
    if current is None and knob.impl:
        try:
            current = int(knob.impl.params.get("rate")) if knob.impl.params.get("rate") is not None else None
        except Exception:
            current = None
    combo.blockSignals(True)
    if current in values:
        combo.setCurrentIndex(values.index(int(current)))
    combo.blockSignals(False)

    def _on_change(_: int, *, _combo: QComboBox = combo) -> None:
        ui.state["pipewire_sample_rate"] = int(_combo.currentData())
        save_state(ui.state)
        ui._knob_statuses["pipewire_sample_rate"] = "not_applied"
        ui._refresh_statuses()
        ui._populate()

    combo.currentIndexChanged.connect(_on_change)
    return combo


def configure_quantum_dialog(ui) -> None:
    current = ui._pipewire_quantum_from_state() or 256
    dialog = PipeWireQuantumDialog(current=current, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    chosen = dialog.selected_value()
    ui.state["pipewire_quantum"] = chosen
    save_state(ui.state)
    QMessageBox.information(
        ui,
        "Saved",
        f"Saved PipeWire quantum = {chosen}. Apply the PipeWire knob to take effect.",
    )


def configure_sample_rate_dialog(ui) -> None:
    current = ui._pipewire_sample_rate_from_state() or 48000
    dialog = PipeWireSampleRateDialog(current=current, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    chosen = dialog.selected_value()
    ui.state["pipewire_sample_rate"] = chosen
    save_state(ui.state)
    QMessageBox.information(
        ui,
        "Saved",
        f"Saved PipeWire sample rate = {chosen} Hz. Apply the PipeWire knob to take effect.",
    )


def configure_clock_constraints_dialog(ui) -> None:
    current = {
        "allowed_rates": ui.state.get("pipewire_clock_allowed_rates"),
        "min_quantum": ui.state.get("pipewire_clock_min_quantum"),
        "max_quantum": ui.state.get("pipewire_clock_max_quantum"),
        "quantum_limit": ui.state.get("pipewire_clock_quantum_limit"),
        "quantum_floor": ui.state.get("pipewire_clock_quantum_floor"),
        "power_of_two": ui.state.get("pipewire_clock_power_of_two"),
    }
    dialog = PipeWireClockConstraintsDialog(current=current, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    try:
        values = dialog.values()
    except ValueError as exc:
        QMessageBox.warning(ui, "Invalid values", str(exc))
        return
    ui.state["pipewire_clock_allowed_rates"] = values.get("allowed_rates")
    ui.state["pipewire_clock_min_quantum"] = values.get("min_quantum")
    ui.state["pipewire_clock_max_quantum"] = values.get("max_quantum")
    ui.state["pipewire_clock_quantum_limit"] = values.get("quantum_limit")
    ui.state["pipewire_clock_quantum_floor"] = values.get("quantum_floor")
    ui.state["pipewire_clock_power_of_two"] = values.get("power_of_two")
    save_state(ui.state)
    QMessageBox.information(ui, "Saved", "Saved PipeWire clock constraints. Apply to take effect.")


def configure_mlock_dialog(ui) -> None:
    current = {
        "allow_mlock": ui.state.get("pipewire_mlock_allow"),
        "mlock_all": ui.state.get("pipewire_mlock_all"),
    }
    dialog = PipeWireMlockDialog(current=current, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    values = dialog.values()
    ui.state["pipewire_mlock_allow"] = values.get("allow_mlock")
    ui.state["pipewire_mlock_all"] = values.get("mlock_all")
    save_state(ui.state)
    QMessageBox.information(ui, "Saved", "Saved PipeWire memory locking options. Apply to take effect.")


def configure_rt_limits_group_dialog(ui) -> None:
    candidates = ["pipewire", "audio", "realtime"]
    current = ui.state.get("pipewire_limits_group")
    dialog = PipeWireRtLimitsGroupDialog(current_group=current, candidates=candidates, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    group = dialog.selected_group()
    ui.state["pipewire_limits_group"] = group
    save_state(ui.state)
    QMessageBox.information(ui, "Saved", "Saved PipeWire RT limits group. Apply to take effect.")


def configure_rt_module_dialog(ui) -> None:
    current = {
        "rt_prio": ui.state.get("pipewire_rt_prio"),
        "rt_time_soft": ui.state.get("pipewire_rt_time_soft"),
        "rt_time_hard": ui.state.get("pipewire_rt_time_hard"),
        "nice_level": ui.state.get("pipewire_nice_level"),
        "rlimits_enabled": ui.state.get("pipewire_rlimits_enabled"),
        "rtkit_enabled": ui.state.get("pipewire_rtkit_enabled"),
        "rtportal_enabled": ui.state.get("pipewire_rtportal_enabled"),
    }
    dialog = PipeWireRtModuleDialog(current=current, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    try:
        values = dialog.values()
    except ValueError as exc:
        QMessageBox.warning(ui, "Invalid values", str(exc))
        return
    ui.state["pipewire_rt_prio"] = values.get("rt_prio")
    ui.state["pipewire_rt_time_soft"] = values.get("rt_time_soft")
    ui.state["pipewire_rt_time_hard"] = values.get("rt_time_hard")
    ui.state["pipewire_nice_level"] = values.get("nice_level")
    ui.state["pipewire_rlimits_enabled"] = values.get("rlimits_enabled")
    ui.state["pipewire_rtkit_enabled"] = values.get("rtkit_enabled")
    ui.state["pipewire_rtportal_enabled"] = values.get("rtportal_enabled")
    save_state(ui.state)
    QMessageBox.information(ui, "Saved", "Saved RT module tuning. Apply to take effect.")


def configure_rt_setup_dialog(ui) -> None:
    limits_current = {
        "group": ui.state.get("pipewire_limits_group") or "pipewire",
        "rtprio": ui.state.get("pipewire_limits_rtprio") or 95,
        "nice": ui.state.get("pipewire_limits_nice") or -19,
        "memlock": ui.state.get("pipewire_limits_memlock") or 4194304,
    }
    module_current = {
        "rt_prio": ui.state.get("pipewire_rt_prio") or 88,
        "rt_time_soft": ui.state.get("pipewire_rt_time_soft"),
        "rt_time_hard": ui.state.get("pipewire_rt_time_hard"),
        "nice_level": ui.state.get("pipewire_nice_level") or -11,
        "rlimits_enabled": (
            ui.state.get("pipewire_rlimits_enabled")
            if ui.state.get("pipewire_rlimits_enabled") is not None
            else True
        ),
        "rtkit_enabled": (
            ui.state.get("pipewire_rtkit_enabled")
            if ui.state.get("pipewire_rtkit_enabled") is not None
            else True
        ),
        "rtportal_enabled": (
            ui.state.get("pipewire_rtportal_enabled")
            if ui.state.get("pipewire_rtportal_enabled") is not None
            else True
        ),
    }
    dialog = PipeWireRtSetupDialog(
        limits_current=limits_current,
        module_current=module_current,
        parent=ui,
    )
    if dialog.exec() != QDialog.Accepted:
        return
    try:
        limits = dialog.limits_values()
        module = dialog.module_values()
    except ValueError as exc:
        QMessageBox.warning(ui, "Invalid values", str(exc))
        return

    ui.state["pipewire_limits_group"] = limits.get("group")
    ui.state["pipewire_limits_rtprio"] = limits.get("rtprio")
    ui.state["pipewire_limits_nice"] = limits.get("nice")
    ui.state["pipewire_limits_memlock"] = limits.get("memlock")

    ui.state["pipewire_rt_prio"] = module.get("rt_prio")
    ui.state["pipewire_rt_time_soft"] = module.get("rt_time_soft")
    ui.state["pipewire_rt_time_hard"] = module.get("rt_time_hard")
    ui.state["pipewire_nice_level"] = module.get("nice_level")
    ui.state["pipewire_rlimits_enabled"] = module.get("rlimits_enabled")
    ui.state["pipewire_rtkit_enabled"] = module.get("rtkit_enabled")
    ui.state["pipewire_rtportal_enabled"] = module.get("rtportal_enabled")

    ui.state["pipewire_rt_setup_dirty"] = True
    ui._knob_statuses["pipewire_rt_limits_group"] = "not_applied"
    ui._knob_statuses["pipewire_rt_module_tuning"] = "not_applied"
    ui._knob_statuses["pipewire_rt_setup"] = "not_applied"
    save_state(ui.state)
    QMessageBox.information(ui, "Saved", "Saved PipeWire RT setup. Apply to take effect.")


def configure_data_loops_dialog(ui) -> None:
    current = {
        "num_data_loops": ui.state.get("pipewire_num_data_loops"),
        "data_loops": ui.state.get("pipewire_data_loops"),
    }
    dialog = PipeWireDataLoopsDialog(current=current, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    try:
        values = dialog.values()
    except ValueError as exc:
        QMessageBox.warning(ui, "Invalid values", str(exc))
        return
    ui.state["pipewire_num_data_loops"] = values.get("num_data_loops")
    ui.state["pipewire_data_loops"] = values.get("data_loops")
    save_state(ui.state)
    QMessageBox.information(ui, "Saved", "Saved PipeWire data loop settings. Apply to take effect.")


def configure_wireplumber_alsa_dialog(ui) -> None:
    current = {
        "period_size": ui.state.get("wireplumber_alsa_period_size"),
        "period_num": ui.state.get("wireplumber_alsa_period_num"),
        "headroom": ui.state.get("wireplumber_alsa_headroom"),
        "disable_batch": ui.state.get("wireplumber_alsa_disable_batch"),
    }
    dialog = WirePlumberAlsaDialog(current=current, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    try:
        values = dialog.values()
    except ValueError as exc:
        QMessageBox.warning(ui, "Invalid values", str(exc))
        return
    ui.state["wireplumber_alsa_period_size"] = values.get("period_size")
    ui.state["wireplumber_alsa_period_num"] = values.get("period_num")
    ui.state["wireplumber_alsa_headroom"] = values.get("headroom")
    ui.state["wireplumber_alsa_disable_batch"] = values.get("disable_batch")
    save_state(ui.state)
    QMessageBox.information(ui, "Saved", "Saved WirePlumber ALSA tuning. Apply to take effect.")


def configure_pro_audio_dialog(ui) -> None:
    current_device = ui.state.get("pipewire_pro_audio_device_id")
    dialog = ProAudioProfileDialog(current_device=str(current_device) if current_device else None, parent=ui)
    if dialog.exec() != QDialog.Accepted:
        return
    device_id = dialog.selected_device_id()
    if not device_id:
        QMessageBox.warning(ui, "No device", "No device selected.")
        return
    ui.state["pipewire_pro_audio_device_id"] = device_id
    save_state(ui.state)
    QMessageBox.information(ui, "Saved", f"Selected device {device_id}. Apply to switch to Pro Audio.")


def apply_param_overrides(ui, knob, params: dict) -> None:
    if knob.id == "pipewire_quantum":
        quantum = ui._pipewire_quantum_from_state()
        if quantum is not None:
            params["quantum"] = quantum
    if knob.id == "pipewire_sample_rate":
        rate = ui._pipewire_sample_rate_from_state()
        if rate is not None:
            params["rate"] = rate
    if knob.id == "pipewire_clock_constraints":
        props = dict(params.get("properties") or {})
        allowed = ui.state.get("pipewire_clock_allowed_rates")
        if isinstance(allowed, list) and allowed:
            props["default.clock.allowed-rates"] = allowed
        min_q = ui.state.get("pipewire_clock_min_quantum")
        if isinstance(min_q, int):
            props["default.clock.min-quantum"] = min_q
        max_q = ui.state.get("pipewire_clock_max_quantum")
        if isinstance(max_q, int):
            props["default.clock.max-quantum"] = max_q
        q_limit = ui.state.get("pipewire_clock_quantum_limit")
        if isinstance(q_limit, int):
            props["default.clock.quantum-limit"] = q_limit
        q_floor = ui.state.get("pipewire_clock_quantum_floor")
        if isinstance(q_floor, int):
            props["default.clock.quantum-floor"] = q_floor
        pow2 = ui.state.get("pipewire_clock_power_of_two")
        if isinstance(pow2, bool):
            props["clock.power-of-two-quantum"] = pow2
        params["properties"] = props
    if knob.id == "pipewire_mlock_policy":
        props = dict(params.get("properties") or {})
        allow = ui.state.get("pipewire_mlock_allow")
        if isinstance(allow, bool):
            props["mem.allow-mlock"] = allow
        mlock_all = ui.state.get("pipewire_mlock_all")
        if isinstance(mlock_all, bool):
            props["mem.mlock-all"] = mlock_all
        params["properties"] = props
    if knob.id == "pipewire_rt_limits_group":
        group = ui.state.get("pipewire_limits_group")
        if isinstance(group, str) and group.strip():
            params["group"] = group.strip()
        rtprio = ui.state.get("pipewire_limits_rtprio")
        nice = ui.state.get("pipewire_limits_nice")
        memlock = ui.state.get("pipewire_limits_memlock")
        rtprio_val = int(rtprio) if isinstance(rtprio, int) else 95
        nice_val = int(nice) if isinstance(nice, int) else -19
        memlock_val = int(memlock) if isinstance(memlock, int) else 4194304
        group_label = group.strip() if isinstance(group, str) and group.strip() else "pipewire"
        params["lines"] = [
            f"@{group_label}   -  rtprio     {rtprio_val}",
            f"@{group_label}   -  nice      {nice_val}",
            f"@{group_label}   -  memlock   {memlock_val}",
        ]
    if knob.id == "pipewire_rt_module_tuning":
        args = dict(params.get("module_rt_args") or {})
        for key, state_key in (
            ("rt.prio", "pipewire_rt_prio"),
            ("rt.time.soft", "pipewire_rt_time_soft"),
            ("rt.time.hard", "pipewire_rt_time_hard"),
            ("nice.level", "pipewire_nice_level"),
        ):
            val = ui.state.get(state_key)
            if isinstance(val, int):
                args[key] = val
        for key, state_key in (
            ("rlimits.enabled", "pipewire_rlimits_enabled"),
            ("rtkit.enabled", "pipewire_rtkit_enabled"),
            ("rtportal.enabled", "pipewire_rtportal_enabled"),
        ):
            val = ui.state.get(state_key)
            if isinstance(val, bool):
                args[key] = val
        params["module_rt_args"] = args
    if knob.id == "pipewire_data_loop_affinity":
        context = dict(params.get("context") or {})
        num = ui.state.get("pipewire_num_data_loops")
        if isinstance(num, int):
            context["num-data-loops"] = num
        loops = ui.state.get("pipewire_data_loops")
        if isinstance(loops, list) and all(isinstance(x, dict) for x in loops):
            context["data-loops"] = loops
        params["context"] = context
    if knob.id == "wireplumber_alsa_usb_tuning":
        props = dict(params.get("props") or {})
        period_size = ui.state.get("wireplumber_alsa_period_size")
        if isinstance(period_size, int):
            props["api.alsa.period-size"] = period_size
        period_num = ui.state.get("wireplumber_alsa_period_num")
        if isinstance(period_num, int):
            props["api.alsa.period-num"] = period_num
        headroom = ui.state.get("wireplumber_alsa_headroom")
        if isinstance(headroom, int):
            props["api.alsa.headroom"] = headroom
        disable = ui.state.get("wireplumber_alsa_disable_batch")
        if isinstance(disable, bool):
            props["api.alsa.disable-batch"] = disable
        params["props"] = props
    if knob.id == "pipewire_pro_audio_profile":
        device_id = ui.state.get("pipewire_pro_audio_device_id")
        if device_id is not None:
            params["device_id"] = device_id


def add_info_buttons(ui, knob, dialog: QWidget, layout) -> None:
    if knob.id == "pipewire_quantum":
        config_btn = QPushButton("Configure Buffer Size...")
        config_btn.clicked.connect(lambda: (dialog.accept(), ui.on_configure_knob(knob.id)))
        layout.addWidget(config_btn)


def _status_label(status: str) -> str:
    mapping = {
        "applied": "Applied",
        "not_applied": "Not applied",
        "partial": "Partial",
        "pending_reboot": "Reboot required",
        "read_only": "Read-only",
        "unknown": "Unknown",
        "not_applicable": "N/A",
        "sys_default": "System default",
        "running": "Updating",
    }
    return mapping.get(status, status)


def info_extra_html(ui, knob) -> str:
    kid = knob.id
    if kid == "pipewire_rt_setup":
        limits = _status_label(ui._knob_statuses.get("pipewire_rt_limits_group", "unknown"))
        module = _status_label(ui._knob_statuses.get("pipewire_rt_module_tuning", "unknown"))
        overall = _status_label(ui._knob_statuses.get("pipewire_rt_setup", "unknown"))
        return (
            "<h4>What this does</h4>"
            "<ul>"
            "<li>Sets RT limits (permissions) and module-rt behavior together.</li>"
            "<li>Limits are always applied using the values below.</li>"
            "<li>Module-rt settings apply only for fields you fill in.</li>"
            "</ul>"
            "<p><b>Status:</b></p>"
            "<ul>"
            f"<li>RT limits: {limits}</li>"
            f"<li>RT module: {module}</li>"
            f"<li>Overall: {overall}</li>"
            "</ul>"
            "<p><b>Tip:</b> Configure first, then Apply.</p>"
        )
    if kid == "pipewire_clock_constraints":
        return (
            "<h4>How it works</h4>"
            "<ul>"
            "<li>Writes clock/quantum limits into a PipeWire drop-in.</li>"
            "<li>Only the fields you set are applied.</li>"
            "</ul>"
            "<p><b>Tip:</b> Configure first, then Apply. Empty fields mean no change.</p>"
        )
    if kid == "pipewire_mlock_policy":
        return (
            "<h4>How it works</h4>"
            "<ul>"
            "<li>Enables PipeWire memory locking in a user drop-in.</li>"
            "<li>Requires RT limits (group memlock) to succeed.</li>"
            "</ul>"
            "<p><b>Tip:</b> Configure first, then Apply.</p>"
        )
    if kid == "pipewire_rt_limits_group":
        return (
            "<h4>How it works</h4>"
            "<ul>"
            "<li>Sets PAM limits for a selected group (rtprio/nice/memlock).</li>"
            "<li>Gives PipeWire permission to request realtime scheduling.</li>"
            "</ul>"
            "<p><b>Note:</b> Log out/in or reboot for limits to take effect.</p>"
        )
    if kid == "pipewire_rt_module_tuning":
        return (
            "<h4>How it works</h4>"
            "<ul>"
            "<li>Sets PipeWire module-rt arguments (rt.prio, nice.level, RTKit/portal).</li>"
            "<li>Only the fields you set are applied.</li>"
            "</ul>"
            "<p><b>Tip:</b> Configure first, then Apply. Empty fields mean no change.</p>"
        )
    if kid == "pipewire_data_loop_affinity":
        return (
            "<h4>How it works</h4>"
            "<ul>"
            "<li>Controls PipeWire data-loop configuration in a user drop-in.</li>"
            "<li>Useful for advanced CPU tuning; leave empty to keep defaults.</li>"
            "</ul>"
            "<p><b>Tip:</b> Configure first, then Apply.</p>"
        )
    if kid == "pipewire_pro_audio_profile":
        status = _status_label(ui._knob_statuses.get("pipewire_pro_audio_profile", "unknown"))
        device_id = ui.state.get("pipewire_pro_audio_device_id")
        device_text = str(device_id) if device_id else "none"
        return (
            "<h4>How it works</h4>"
            "<ul>"
            "<li>Uses wpctl/pactl to switch a device to the Pro Audio profile.</li>"
            "<li>Reset returns to the previous profile from the last apply.</li>"
            "</ul>"
            "<p><b>Status:</b></p>"
            "<ul>"
            f"<li>Selected device: {device_text}</li>"
            f"<li>Current state: {status}</li>"
            "</ul>"
        )
    return ""


def _rt_module_configured(ui) -> bool:
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


def build_rt_setup_action(ui, knob, ctx):
    status = ctx.status
    dirty = bool(ui.state.get("pipewire_rt_setup_dirty"))
    applied = status in ("applied", "pending_reboot") and not dirty
    btn = ui._make_reset_button() if applied else ui._make_apply_button()

    def _queue_apply() -> None:
        ui.state["pipewire_rt_setup_dirty"] = False
        save_state(ui.state)
        ui._on_queue_knob("pipewire_rt_limits_group", "apply")
        if _rt_module_configured(ui):
            ui._on_queue_knob("pipewire_rt_module_tuning", "apply")

    def _queue_reset() -> None:
        ui.state["pipewire_rt_setup_dirty"] = False
        save_state(ui.state)
        ui._on_queue_knob("pipewire_rt_limits_group", "reset")
        ui._on_queue_knob("pipewire_rt_module_tuning", "reset")

    if applied:
        btn.clicked.connect(_queue_reset)
    else:
        btn.clicked.connect(_queue_apply)

    ui._apply_busy_state(btn, busy=ctx.busy)
    return btn


def build_xrun_monitor_action(ui, knob, ctx):
    btn = ui._make_action_button("Monitor")
    if ctx.busy:
        btn.setEnabled(False)
    else:
        btn.clicked.connect(ui.on_open_xrun_monitor)
    ui._apply_busy_state(btn, busy=ctx.busy)
    return btn


def build_rtkit_info_action(ui, knob, ctx):
    btn = ui._make_action_button("Info")
    btn.clicked.connect(
        lambda: QMessageBox.information(
            ui,
            "RTKit Tuning",
            "RTKit tuning is on hold until distro-specific configuration is verified.\n\n"
            "See docs/knobs.md for current research notes.",
        )
    )
    return btn

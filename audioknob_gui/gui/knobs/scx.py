from __future__ import annotations

import html as html_lib
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
)

from audioknob_gui.core.scx import (
    list_available_scx_flag_presets,
    list_available_scx_schedulers,
    normalize_scx_flags,
    normalize_scx_scheduler_name,
    preferred_scx_scheduler,
    read_sched_ext_status,
    read_scx_flags_config,
    read_scx_scheduler_config,
    scx_service_dropin_matches,
    scx_service_dropin_path,
    scx_ops_name,
)
from audioknob_gui.gui.chrome import build_dialog_root, set_label_tone, style_dialog_button_box
from audioknob_gui.gui.state import save_state
from audioknob_gui.knob_ids import SCX_SCHEDULER


_ENABLED_STATES = {"enabled", "static", "indirect"}
_SCHEDULER_NOTES = {
    "scx_bpfland": "Recommended for mixed music + gaming workloads.",
    "scx_lavd": "Gaming-first choice for highly interactive workloads.",
    "scx_flash": "Audio/multimedia-first choice with predictable latency.",
}


class ScxSchedulerDialog(QDialog):
    def __init__(
        self,
        *,
        selected_scheduler: str | None,
        selected_flags: str | None,
        selected_enable_at_boot: bool | None,
        configured_scheduler: str | None,
        configured_flags: str | None,
        configured_enable_at_boot: bool | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure sched_ext scheduler")
        self.resize(760, 360)
        self._configured_scheduler = configured_scheduler
        self._configured_flags = configured_flags

        root = build_dialog_root(self, parent=parent)

        intro = QLabel(
            "Choose an installed scx scheduler, an optional preset SCX_FLAGS value, "
            "and whether scx.service should start automatically at boot."
        )
        intro.setWordWrap(True)
        set_label_tone(intro, "muted")
        root.addWidget(intro)

        self.scheduler_combo = QComboBox()
        self.flags_combo = QComboBox()
        _prepare_dialog_combo(self.scheduler_combo, min_width=360, min_chars=28)
        _prepare_dialog_combo(self.flags_combo, min_width=460, min_chars=36)

        _populate_scheduler_combo(self.scheduler_combo, selected_scheduler, configured_scheduler)
        current_scheduler = normalize_scx_scheduler_name(selected_scheduler)
        if current_scheduler is None:
            current_scheduler = normalize_scx_scheduler_name(configured_scheduler)
        current_flags = selected_flags
        if current_flags is None and current_scheduler:
            current_flags = _selected_flags(
                _DialogStateProxy(selected_flags, selected_enable_at_boot),
                current_scheduler,
                configured_scheduler,
                configured_flags,
            )
        _populate_flags_combo(
            self.flags_combo,
            current_scheduler,
            current_flags,
            configured_flags,
        )

        self.scheduler_combo.blockSignals(True)
        _select_combo_value(self.scheduler_combo, current_scheduler)
        self.scheduler_combo.blockSignals(False)
        self.flags_combo.blockSignals(True)
        _select_combo_value(self.flags_combo, current_flags if current_scheduler else None)
        self.flags_combo.blockSignals(False)

        self.enable_checkbox = QCheckBox("Enable at boot (scx.service)")
        enable_at_boot = selected_enable_at_boot
        if enable_at_boot is None:
            enable_at_boot = configured_enable_at_boot if configured_enable_at_boot is not None else False
        self.enable_checkbox.setChecked(bool(enable_at_boot))

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("Scheduler", self.scheduler_combo)
        form.addRow("Flags", self.flags_combo)
        form.addRow("", self.enable_checkbox)
        root.addLayout(form)

        self.note_label = QLabel("")
        self.note_label.setWordWrap(True)
        set_label_tone(self.note_label, "muted")
        root.addWidget(self.note_label)

        available = list_available_scx_schedulers()
        available_text = ", ".join(available) if available else "none detected in PATH"
        self.available_label = QLabel(f"Detected schedulers: {available_text}")
        self.available_label.setWordWrap(True)
        set_label_tone(self.available_label, "muted")
        root.addWidget(self.available_label)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        style_dialog_button_box(self._buttons)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

        self.scheduler_combo.currentIndexChanged.connect(self._on_scheduler_change)
        self.flags_combo.currentIndexChanged.connect(self._update_ok_state)
        self._refresh_note()
        self._update_ok_state()

    def values(self) -> tuple[str | None, str | None, bool]:
        scheduler = normalize_scx_scheduler_name(self.scheduler_combo.currentData())
        flags = normalize_scx_flags(self.flags_combo.currentData())
        if not scheduler:
            return None, None, self.enable_checkbox.isChecked()
        return scheduler, ("" if flags is None else flags), self.enable_checkbox.isChecked()

    def _on_scheduler_change(self, _: int) -> None:
        scheduler = normalize_scx_scheduler_name(self.scheduler_combo.currentData())
        if scheduler and scheduler == self._configured_scheduler:
            current_flags = self._configured_flags if self._configured_flags is not None else ""
        else:
            current_flags = ""
        _populate_flags_combo(self.flags_combo, scheduler, current_flags, self._configured_flags)
        self._refresh_note()
        self._update_ok_state()

    def _refresh_note(self) -> None:
        scheduler = normalize_scx_scheduler_name(self.scheduler_combo.currentData())
        note = _SCHEDULER_NOTES.get(scheduler or "", "Choose a scheduler to unlock Apply Config.")
        if scheduler:
            self.note_label.setText(
                f"{scheduler}: {note} Apply Config writes /etc/default/scx; Start/Stop controls runtime separately."
            )
        else:
            self.note_label.setText(note)

    def _update_ok_state(self) -> None:
        ok_button = self._buttons.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(normalize_scx_scheduler_name(self.scheduler_combo.currentData()) is not None)


class _DialogStateProxy:
    def __init__(self, flags: str | None, enable_at_boot: bool | None) -> None:
        self.state = {
            "scx_flags": flags,
            "scx_enable_at_boot": enable_at_boot,
        }

    def _scx_enable_at_boot_from_state(self) -> bool | None:
        raw = self.state.get("scx_enable_at_boot")
        return raw if isinstance(raw, bool) else None

    def _scx_scheduler_from_state(self) -> str | None:
        return None


def build_config_button(ui, knob_id: str) -> QPushButton:
    btn = ui._make_action_button("Configure...")
    btn.setToolTip("Select sched_ext scheduler, SCX_FLAGS preset, and boot persistence.")
    btn.setFocusPolicy(Qt.NoFocus)
    btn.clicked.connect(lambda _, kid=knob_id: ui.on_configure_knob(kid))
    return btn


def build_runtime_action(ui, knob, ctx) -> QPushButton:
    label, action = runtime_action(ui, ctx.status, unit=_unit_from_knob(knob))
    if action == "stop":
        btn = ui._make_reset_button(label)
        btn.setToolTip("Stop scx.service now without changing /etc/default/scx or Enable at boot.")
    else:
        btn = ui._make_apply_button(label)
        if action == "apply":
            btn.setToolTip("Write /etc/default/scx, install the scx.service memlock drop-in, and sync Enable at boot.")
        elif action == "restart":
            btn.setToolTip("Restart scx.service now using the configured scheduler.")
        else:
            btn.setToolTip("Start scx.service now using the configured scheduler.")

    if ctx.busy:
        btn.setText("Working...")
        btn.setEnabled(False)
        return btn

    if action == "apply":
        btn.clicked.connect(lambda _=False: ui._on_apply_knob(SCX_SCHEDULER))
    else:
        btn.clicked.connect(lambda _=False, mode=action: ui._on_scx_runtime(mode))
    return btn


def allow_config_when_row_dim(ctx) -> bool:
    config_locked = (
        ctx.group_pending_lock
        or ctx.reboot_dep_lock
        or ctx.reboot_gate_lock
        or ctx.advanced_gate_lock
    )
    return not config_locked


def configure_dialog(ui) -> None:
    configured = _configured_scheduler(ui)
    configured_flags = _configured_flags(ui)
    configured_enable_at_boot = _configured_enable_at_boot()
    selected = _selected_scheduler(ui, configured)
    selected_flags = _selected_flags(ui, selected, configured, configured_flags)
    selected_enable_at_boot = _selected_enable_at_boot(ui)
    available = list_available_scx_schedulers()

    if not available and not selected and not configured:
        QMessageBox.warning(
            ui,
            "No scx schedulers",
            "No scx_* schedulers were detected in PATH. Install scx first, then try again.",
        )
        return

    dialog = ScxSchedulerDialog(
        selected_scheduler=selected,
        selected_flags=selected_flags,
        selected_enable_at_boot=selected_enable_at_boot,
        configured_scheduler=configured,
        configured_flags=configured_flags,
        configured_enable_at_boot=configured_enable_at_boot,
        parent=ui,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    scheduler, flags, enable_at_boot = dialog.values()
    scheduler = save_selection(ui, scheduler, flags, enable_at_boot)
    if not scheduler:
        QMessageBox.warning(ui, "No scheduler selected", "Choose an scx scheduler before saving.")
        return

    QMessageBox.information(
        ui,
        "Saved",
        "Saved sched_ext configuration."
        + f" Scheduler: {scheduler}."
        + (f" Flags: {flags or 'default'}." if flags is not None else "")
        + f" Enable at boot: {'on' if enable_at_boot else 'off'}."
        + " Use Apply Config to write /etc/default/scx and the service drop-in, then Start to activate it.",
    )


def apply_param_overrides(ui, params: dict) -> None:
    scheduler = _selected_scheduler(ui, _configured_scheduler(ui))
    if scheduler:
        params["scheduler"] = scheduler
    flags = _selected_flags(ui, scheduler, _configured_scheduler(ui), _configured_flags(ui))
    if flags is not None:
        params["flags"] = flags
    enable_at_boot = _selected_enable_at_boot(ui)
    if enable_at_boot is not None:
        params["enable_at_boot"] = enable_at_boot


def save_selection(ui, scheduler: object, flags: object, enable_at_boot: bool | None) -> str | None:
    normalized_scheduler = normalize_scx_scheduler_name(scheduler)
    if normalized_scheduler:
        normalized_flags = normalize_scx_flags(flags)
        ui.state["scx_scheduler"] = normalized_scheduler
        ui.state["scx_flags"] = "" if normalized_flags is None else normalized_flags
        ui.state["scx_enable_at_boot"] = bool(enable_at_boot) if enable_at_boot is not None else None
    else:
        ui.state["scx_scheduler"] = None
        ui.state["scx_flags"] = None
        ui.state["scx_enable_at_boot"] = None
    save_state(ui.state)
    ui._knob_statuses[SCX_SCHEDULER] = "not_applied"
    ui._refresh_statuses()
    ui._populate()
    return normalized_scheduler


def info_extra_html(ui, knob) -> str:
    parts: list[str] = ["<hr/>"]

    selected = ui._scx_scheduler_from_state()
    selected_flags = _flags_from_state(ui)
    selected_enable_at_boot = _selected_enable_at_boot(ui)
    configured = _configured_scheduler(ui)
    configured_flags = _configured_flags(ui)
    unit = _unit_from_knob(knob)
    configured_enable_at_boot = _configured_enable_at_boot(unit)
    service_enabled = _service_enabled_state(unit)
    service_active = _service_active_state(unit)
    dropin_path = scx_service_dropin_path(unit)
    dropin_matches = _service_dropin_matches(unit)
    state, ops = read_sched_ext_status()
    available = list_available_scx_schedulers()
    preferred = preferred_scx_scheduler(available)

    parts.append("<p><b>Selection:</b> ")
    parts.append(html_lib.escape(selected or "none"))
    parts.append("</p>")
    parts.append("<p><b>Selected flags:</b> " + html_lib.escape(selected_flags or "none") + "</p>")
    parts.append(
        "<p><b>Selected enable at boot:</b> "
        + html_lib.escape(_enable_label(selected_enable_at_boot, unset_label="unchanged"))
        + "</p>"
    )

    if preferred:
        note = _SCHEDULER_NOTES.get(preferred, "Recommended starting point.")
        parts.append(
            "<p><b>Suggested start:</b> "
            + html_lib.escape(preferred)
            + " - "
            + html_lib.escape(note)
            + "</p>"
        )
    if available:
        parts.append("<p><b>Available:</b> " + html_lib.escape(", ".join(available)) + "</p>")
    else:
        parts.append("<p><b>Available:</b> none detected in PATH.</p>")

    config_path = _config_path(ui)
    if config_path:
        parts.append(f"<p><b>Config:</b> {html_lib.escape(config_path)}</p>")
    if configured:
        parts.append("<p><b>Configured scheduler:</b> " + html_lib.escape(configured) + "</p>")
    parts.append("<p><b>Configured flags:</b> " + html_lib.escape(configured_flags or "none") + "</p>")
    parts.append("<p><b>Service drop-in:</b> " + html_lib.escape(dropin_path) + "</p>")
    parts.append(
        "<p><b>Service drop-in status:</b> "
        + html_lib.escape("matched" if dropin_matches else "missing or drifted")
        + "</p>"
    )
    parts.append(
        "<p><b>Configured enable at boot:</b> "
        + html_lib.escape(_enable_label(configured_enable_at_boot, unset_label="unknown"))
        + "</p>"
    )
    parts.append("<p><b>Service enabled:</b> " + html_lib.escape(service_enabled or "unknown") + "</p>")
    parts.append("<p><b>Service active:</b> " + html_lib.escape(service_active or "unknown") + "</p>")
    current_scheduler = selected or configured
    presets = list_available_scx_flag_presets(current_scheduler)
    if current_scheduler and presets:
        preset_labels = ", ".join(option.value for option in presets if option.value)
        if preset_labels:
            parts.append("<p><b>Preset flags:</b> " + html_lib.escape(preset_labels) + "</p>")
    if state:
        parts.append("<p><b>sched_ext state:</b> " + html_lib.escape(state) + "</p>")
    if ops:
        parts.append(
            "<p><b>Live scheduler ops:</b> "
            + html_lib.escape(ops)
            + " ("
            + html_lib.escape(scx_ops_name(ops) or ops)
            + ")</p>"
        )
    parts.append(
        "<p><b>Flow:</b> Configure... saves the desired scheduler, Apply Config writes /etc/default/scx plus an scx.service memlock drop-in, and Start/Stop controls the runtime session separately.</p>"
    )
    parts.append(
        "<p><b>Note:</b> sched_ext complements the realtime audio path rather than replacing PipeWire RT limits and scheduling.</p>"
    )
    return "".join(parts)


def effective_scheduler(ui) -> str | None:
    return _selected_scheduler(ui, _configured_scheduler(ui))


def runtime_action(ui, status: str, *, unit: str = "scx.service") -> tuple[str, str]:
    configured = _configured_scheduler(ui)
    configured_flags = _configured_flags(ui)
    selected = _selected_scheduler(ui, configured)
    selected_flags = _selected_flags(ui, selected, configured, configured_flags)
    selected_enable_at_boot = _selected_enable_at_boot(ui)
    enabled_state = _service_enabled_state(unit)
    active_state = _service_active_state(unit)
    dropin_matches = _service_dropin_matches(unit)
    sched_state, _live_ops = read_sched_ext_status()

    if not selected:
        return "Apply Config", "apply"

    config_matches = configured == selected
    flags_match = selected_flags is None or configured_flags == selected_flags
    boot_matches = selected_enable_at_boot is None or _service_enabled_matches(enabled_state, selected_enable_at_boot)

    if not (config_matches and flags_match and boot_matches and dropin_matches):
        return "Apply Config", "apply"
    if status == "applied":
        return "Stop", "stop"
    if status == "active_external" and (sched_state == "enabled" or active_state == "active"):
        return "Stop", "stop"
    if sched_state == "enabled" or active_state == "active":
        return "Restart", "restart"
    return "Start", "start"


def _configured_scheduler(ui) -> str | None:
    path = _config_path(ui)
    if not path:
        return None
    return read_scx_scheduler_config(path)


def _configured_flags(ui) -> str | None:
    path = _config_path(ui)
    if not path:
        return None
    return read_scx_flags_config(path)


def _configured_enable_at_boot(unit: str = "scx.service") -> bool | None:
    state = _service_enabled_state(unit)
    if state is None:
        return None
    return state in _ENABLED_STATES


def _service_dropin_matches(unit: str = "scx.service") -> bool:
    return scx_service_dropin_matches(unit)


def _flags_from_state(ui) -> str | None:
    raw = ui.state.get("scx_flags")
    if raw is None:
        return None
    return normalize_scx_flags(raw)


def _selected_scheduler(ui, configured: str | None) -> str | None:
    return ui._scx_scheduler_from_state() or configured


def _selected_enable_at_boot(ui) -> bool | None:
    fn = getattr(ui, "_scx_enable_at_boot_from_state", None)
    if callable(fn):
        value = fn()
        if isinstance(value, bool):
            return value
    return None


def _selected_flags(
    ui,
    scheduler: str | None,
    configured_scheduler: str | None,
    configured_flags: str | None,
) -> str | None:
    state_flags = _flags_from_state(ui)
    if state_flags is not None:
        return state_flags
    if scheduler and configured_scheduler == scheduler and configured_flags is not None:
        return configured_flags
    if scheduler:
        return ""
    return None


def _populate_scheduler_combo(
    combo: QComboBox,
    selected_scheduler: str | None,
    configured: str | None,
) -> None:
    combo.clear()
    combo.addItem("Scheduler...", None)

    available = list_available_scx_schedulers()
    preferred = preferred_scx_scheduler(available)
    seen: set[str] = set()
    for name in available:
        label = f"{name} (Recommended)" if name == preferred else name
        combo.addItem(label, name)
        seen.add(name)

    for name in (selected_scheduler, configured):
        normalized = normalize_scx_scheduler_name(name)
        if not normalized or normalized in seen:
            continue
        combo.addItem(f"{normalized} (not found)", normalized)
        seen.add(normalized)

    combo.setToolTip(
        "Pick an installed scx scheduler. Recommended for music + gaming: scx_bpfland."
    )
    _set_combo_popup_width(combo, minimum_width=360)


def _populate_flags_combo(
    combo: QComboBox,
    scheduler: str | None,
    selected_flags: str | None,
    configured_flags: str | None,
) -> None:
    combo.blockSignals(True)
    combo.clear()
    if not scheduler:
        combo.addItem("Flags...", None)
        combo.setEnabled(False)
        combo.setToolTip("Select a scheduler first.")
        combo.blockSignals(False)
        return

    combo.addItem("Default flags", "")
    combo.setItemData(0, "Run the selected scheduler with no extra SCX_FLAGS.", Qt.ToolTipRole)

    seen: set[str] = {""}
    for option in list_available_scx_flag_presets(scheduler):
        value = normalize_scx_flags(option.value)
        if value is None or value in seen:
            continue
        combo.addItem(option.label, value)
        combo.setItemData(combo.count() - 1, option.description, Qt.ToolTipRole)
        seen.add(value)

    for flags in (selected_flags, configured_flags):
        value = normalize_scx_flags(flags)
        if value is None or value in seen or not value:
            continue
        combo.addItem(f"Custom: {value}", value)
        combo.setItemData(combo.count() - 1, "Existing custom SCX_FLAGS value.", Qt.ToolTipRole)
        seen.add(value)

    combo.setEnabled(True)
    combo.setToolTip(f"Choose SCX_FLAGS for {scheduler}.")
    _select_combo_value(combo, selected_flags if selected_flags is not None else "")
    _set_combo_popup_width(combo, minimum_width=460)
    combo.blockSignals(False)


def _select_combo_value(combo: QComboBox, value: str | None) -> None:
    for idx in range(combo.count()):
        if combo.itemData(idx) == value:
            combo.setCurrentIndex(idx)
            return


def _prepare_dialog_combo(combo: QComboBox, *, min_width: int, min_chars: int) -> None:
    combo.setMinimumWidth(min_width)
    combo.setMinimumContentsLength(min_chars)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


def _set_combo_popup_width(combo: QComboBox, *, minimum_width: int) -> None:
    metrics = combo.fontMetrics()
    widest = max((metrics.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())), default=0)
    popup_width = max(minimum_width, widest + 64)
    combo.setMinimumWidth(minimum_width)
    view = combo.view()
    if view is not None:
        view.setMinimumWidth(popup_width)
        try:
            view.setTextElideMode(Qt.TextElideMode.ElideNone)
        except Exception:
            pass


def _systemctl_state(*args: str) -> str | None:
    try:
        result = subprocess.run(["systemctl", *args], capture_output=True, text=True, check=False)
    except Exception:
        return None
    value = result.stdout.strip() or result.stderr.strip()
    return value or None


def _service_enabled_state(unit: str) -> str | None:
    return _systemctl_state("is-enabled", unit)


def _service_active_state(unit: str) -> str | None:
    return _systemctl_state("is-active", unit)


def _service_enabled_matches(enabled_state: str | None, desired: bool) -> bool:
    return (enabled_state in _ENABLED_STATES) == desired


def _enable_label(value: bool | None, *, unset_label: str) -> str:
    if value is True:
        return "enabled"
    if value is False:
        return "disabled"
    return unset_label


def _unit_from_knob(knob) -> str:
    impl = getattr(knob, "impl", None)
    params = getattr(impl, "params", None)
    if isinstance(params, dict):
        unit = str(params.get("unit", "") or "").strip()
        if unit:
            return unit
    return "scx.service"


def _config_path(ui) -> str | None:
    profile = ui.state.get("system_profile")
    if isinstance(profile, dict):
        paths = profile.get("paths")
        if isinstance(paths, dict):
            path = str(paths.get("scx_config") or "").strip()
            if path:
                return path
    return str(Path("/etc/default/scx"))

from __future__ import annotations

import html as html_lib

from PySide6.QtWidgets import QComboBox, QSizePolicy

from audioknob_gui.gui.state import save_state
from audioknob_gui.knob_ids import POWER_PROFILE_PERFORMANCE


def build_backend_combo(ui, knob, ctx) -> QComboBox:
    combo = QComboBox()
    combo.setMinimumWidth(0)
    combo.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
    combo.addItem("Auto", "auto")
    combo.addItem("powerprofilesctl", "powerprofilesctl")
    combo.addItem("tuned", "tuned")
    combo.setToolTip(
        "Power profile backend: auto uses the active backend; tuned uses latency-performance."
    )
    current_backend = ui._power_profile_backend_from_state()
    if current_backend not in ("auto", "powerprofilesctl", "tuned"):
        current_backend = "auto"
    combo.blockSignals(True)
    for idx in range(combo.count()):
        if combo.itemData(idx) == current_backend:
            combo.setCurrentIndex(idx)
            break
    combo.blockSignals(False)

    def _on_backend_change(_: int, *, _combo: QComboBox = combo) -> None:
        ui.state["power_profile_backend"] = str(_combo.currentData())
        save_state(ui.state)
        # Config changed; force re-evaluation until apply succeeds.
        ui._knob_statuses[POWER_PROFILE_PERFORMANCE] = "not_applied"
        ui._refresh_statuses()
        ui._populate()

    combo.currentIndexChanged.connect(_on_backend_change)

    config_locked = (
        ctx.group_pending_lock
        or ctx.reboot_dep_lock
        or ctx.reboot_gate_lock
        or ctx.advanced_gate_lock
    )
    if config_locked:
        combo.setEnabled(False)
    return combo


def allow_config_when_row_dim(ctx) -> bool:
    config_locked = (
        ctx.group_pending_lock
        or ctx.reboot_dep_lock
        or ctx.reboot_gate_lock
        or ctx.advanced_gate_lock
    )
    return not config_locked


def apply_param_overrides(ui, params: dict) -> None:
    params["backend"] = ui._power_profile_backend_from_state()


def info_extra_html(ui, knob) -> str:
    extra = ""
    try:
        from audioknob_gui.worker.ops import read_power_profile, select_power_profile_backend

        pref = ui._power_profile_backend_from_state()
        params = dict(knob.impl.params) if knob.impl else {}
        params["backend"] = pref
        backend = select_power_profile_backend(params)
        pref_label = pref if pref != "auto" else "auto (active backend)"
        extra += "<hr/><p><b>Backend preference:</b> "
        extra += html_lib.escape(pref_label)
        extra += "</p>"
        if backend:
            current = read_power_profile(backend["backend"], backend["cmd"])
            if backend["backend"] == "powerprofilesctl":
                expected = str(params.get("ppd_profile", "performance")).strip() or "performance"
            else:
                expected = str(params.get("tuned_profile", "latency-performance")).strip() or "latency-performance"
            extra += "<p><b>Resolved backend:</b> "
            extra += html_lib.escape(backend["backend"])
            extra += "</p>"
            if current:
                extra += (
                    f"<p>Current: {html_lib.escape(current)}"
                    f" (target: {html_lib.escape(expected)})</p>"
                )
            if backend["backend"] == "tuned":
                conflict_ids = ui._tuned_conflict_ids()
                by_id = {kn.id: kn for kn in ui.registry}
                conflict_titles = []
                for cid in conflict_ids:
                    title = by_id.get(cid).title if cid in by_id else cid
                    state = ui._knob_statuses.get(cid)
                    if state in ("applied", "pending_reboot"):
                        conflict_titles.append(f"{title} ({state})")
                    else:
                        conflict_titles.append(title)
                if conflict_titles:
                    extra += (
                        "<p><b>Potential conflicts:</b> "
                        + html_lib.escape(", ".join(conflict_titles))
                        + "</p>"
                    )
                extra += (
                    "<p><b>Note:</b> tuned manages system power/governor settings. "
                    "Avoid stacking overlapping knobs unless you know their combined effect.</p>"
                )
        else:
            extra += (
                "<p><b>Resolved backend:</b> none detected "
                "(powerprofilesctl or tuned-adm required).</p>"
            )
    except Exception:
        pass
    return extra

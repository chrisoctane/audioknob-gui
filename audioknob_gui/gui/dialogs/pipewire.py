from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
import json
import re
import subprocess

from audioknob_gui.knob_ids import PIPEWIRE_RT_SETUP


class PipeWireQuantumDialog(QDialog):
    def __init__(self, current: int | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure PipeWire buffer (quantum)")
        self.resize(420, 160)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Select PipeWire buffer size (quantum)."))
        root.addWidget(QLabel("Recommended: 128 or 256. Smaller can underrun; larger adds latency."))

        self.combo = QComboBox()
        self._values = [32, 64, 128, 256, 512, 1024]
        for v in self._values:
            self.combo.addItem(str(v), v)
        if current in self._values:
            self.combo.setCurrentIndex(self._values.index(current))
        root.addWidget(self.combo)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.ok_btn = btns.button(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def selected_value(self) -> int:
        return int(self.combo.currentData())


class PipeWireSampleRateDialog(QDialog):
    def __init__(self, current: int | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure PipeWire sample rate")
        self.resize(420, 160)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Select PipeWire default sample rate."))
        root.addWidget(QLabel("Common: 48000 Hz. Higher rates for high-res audio."))

        self.combo = QComboBox()
        self._values = [44100, 48000, 88200, 96000, 192000]
        for v in self._values:
            self.combo.addItem(f"{v} Hz", v)
        if current in self._values:
            self.combo.setCurrentIndex(self._values.index(current))
        root.addWidget(self.combo)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        status_btn = btns.addButton("Status Check...", QDialogButtonBox.ActionRole)
        status_btn.clicked.connect(self._show_status_check)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def selected_value(self) -> int:
        return int(self.combo.currentData())


class PipeWireClockConstraintsDialog(QDialog):
    def __init__(self, current: dict[str, object] | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire clock constraints")
        self.resize(520, 320)
        current = current or {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Advanced clock constraints. Leave fields empty to keep defaults."))
        root.addWidget(QLabel("Note: allowed-rates is disabled by default in PipeWire due to kernel/Bluetooth quirks."))

        form = QFormLayout()
        self.allowed_rates = QLineEdit()
        rates = current.get("allowed_rates")
        if isinstance(rates, list):
            self.allowed_rates.setText(", ".join(str(x) for x in rates))
        self.allowed_rates.setPlaceholderText("e.g. 44100, 48000, 96000")
        form.addRow("Allowed rates", self.allowed_rates)

        self.min_quantum = QLineEdit(str(current.get("min_quantum") or ""))
        self.min_quantum.setPlaceholderText("leave empty")
        form.addRow("Min quantum", self.min_quantum)

        self.max_quantum = QLineEdit(str(current.get("max_quantum") or ""))
        self.max_quantum.setPlaceholderText("leave empty")
        form.addRow("Max quantum", self.max_quantum)

        self.quantum_limit = QLineEdit(str(current.get("quantum_limit") or ""))
        self.quantum_limit.setPlaceholderText("leave empty")
        form.addRow("Quantum limit", self.quantum_limit)

        self.quantum_floor = QLineEdit(str(current.get("quantum_floor") or ""))
        self.quantum_floor.setPlaceholderText("leave empty")
        form.addRow("Quantum floor", self.quantum_floor)

        self.power_of_two = QCheckBox("Power-of-two quantum")
        self.power_of_two.setTristate(True)
        pow2 = current.get("power_of_two")
        if pow2 is None:
            self.power_of_two.setCheckState(Qt.PartiallyChecked)
        elif bool(pow2):
            self.power_of_two.setCheckState(Qt.Checked)
        else:
            self.power_of_two.setCheckState(Qt.Unchecked)
        form.addRow(self.power_of_two)

        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        rates_raw = self.allowed_rates.text().strip()
        if rates_raw:
            parts = re.split(r"[,\s]+", rates_raw)
            rates: list[int] = []
            for part in parts:
                if not part:
                    continue
                try:
                    rates.append(int(part))
                except Exception as exc:
                    raise ValueError(f"Invalid rate: {part}") from exc
            values["allowed_rates"] = rates or None
        else:
            values["allowed_rates"] = None

        def _read_int(field: QLineEdit, label: str) -> int | None:
            raw = field.text().strip()
            if not raw:
                return None
            try:
                return int(raw)
            except Exception as exc:
                raise ValueError(f"Invalid {label}: {raw}") from exc

        values["min_quantum"] = _read_int(self.min_quantum, "min quantum")
        values["max_quantum"] = _read_int(self.max_quantum, "max quantum")
        values["quantum_limit"] = _read_int(self.quantum_limit, "quantum limit")
        values["quantum_floor"] = _read_int(self.quantum_floor, "quantum floor")

        state = self.power_of_two.checkState()
        if state == Qt.PartiallyChecked:
            values["power_of_two"] = None
        else:
            values["power_of_two"] = state == Qt.Checked
        return values


class PipeWireMlockDialog(QDialog):
    def __init__(self, current: dict[str, object] | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire memory locking")
        self.resize(420, 200)
        current = current or {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Enable PipeWire memory locking (advanced)."))
        root.addWidget(QLabel("If memlock limits are low, mlock-all may fail."))

        self.allow_mlock = QCheckBox("Allow mlock")
        self.allow_mlock.setTristate(True)
        allow = current.get("allow_mlock")
        if allow is None:
            self.allow_mlock.setCheckState(Qt.PartiallyChecked)
        elif bool(allow):
            self.allow_mlock.setCheckState(Qt.Checked)
        else:
            self.allow_mlock.setCheckState(Qt.Unchecked)

        self.mlock_all = QCheckBox("Mlock all")
        self.mlock_all.setTristate(True)
        mlock_all = current.get("mlock_all")
        if mlock_all is None:
            self.mlock_all.setCheckState(Qt.PartiallyChecked)
        elif bool(mlock_all):
            self.mlock_all.setCheckState(Qt.Checked)
        else:
            self.mlock_all.setCheckState(Qt.Unchecked)

        root.addWidget(self.allow_mlock)
        root.addWidget(self.mlock_all)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def values(self) -> dict[str, object]:
        def _tri(cb: QCheckBox) -> bool | None:
            state = cb.checkState()
            if state == Qt.PartiallyChecked:
                return None
            return state == Qt.Checked

        return {
            "allow_mlock": _tri(self.allow_mlock),
            "mlock_all": _tri(self.mlock_all),
        }


class PipeWireRtModuleDialog(QDialog):
    def __init__(self, current: dict[str, object] | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire RT module tuning")
        self.resize(520, 360)
        current = current or {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Set module.rt args (advanced). Leave fields empty to keep defaults."))

        form = QFormLayout()
        self.rt_prio = QLineEdit(str(current.get("rt_prio") or ""))
        form.addRow("rt.prio", self.rt_prio)
        self.rt_soft = QLineEdit(str(current.get("rt_time_soft") or ""))
        form.addRow("rt.time.soft", self.rt_soft)
        self.rt_hard = QLineEdit(str(current.get("rt_time_hard") or ""))
        form.addRow("rt.time.hard", self.rt_hard)
        self.nice_level = QLineEdit(str(current.get("nice_level") or ""))
        form.addRow("nice.level", self.nice_level)
        self.uclamp_min = QLineEdit(str(current.get("uclamp_min") or ""))
        form.addRow("uclamp.min", self.uclamp_min)
        self.uclamp_max = QLineEdit(str(current.get("uclamp_max") or ""))
        form.addRow("uclamp.max", self.uclamp_max)

        self.rlimits_enabled = QCheckBox("rlimits.enabled")
        self.rlimits_enabled.setTristate(True)
        self._set_tristate(self.rlimits_enabled, current.get("rlimits_enabled"))
        form.addRow(self.rlimits_enabled)

        self.rtkit_enabled = QCheckBox("rtkit.enabled")
        self.rtkit_enabled.setTristate(True)
        self._set_tristate(self.rtkit_enabled, current.get("rtkit_enabled"))
        form.addRow(self.rtkit_enabled)

        self.rtportal_enabled = QCheckBox("rtportal.enabled")
        self.rtportal_enabled.setTristate(True)
        self._set_tristate(self.rtportal_enabled, current.get("rtportal_enabled"))
        form.addRow(self.rtportal_enabled)

        self.cpu_zero_denormals = QCheckBox("cpu.zero.denormals")
        self.cpu_zero_denormals.setTristate(True)
        self._set_tristate(self.cpu_zero_denormals, current.get("cpu_zero_denormals"))
        form.addRow(self.cpu_zero_denormals)

        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    @staticmethod
    def _set_tristate(cb: QCheckBox, value: object) -> None:
        if value is None:
            cb.setCheckState(Qt.PartiallyChecked)
        elif bool(value):
            cb.setCheckState(Qt.Checked)
        else:
            cb.setCheckState(Qt.Unchecked)

    @staticmethod
    def _read_int(field: QLineEdit, label: str) -> int | None:
        raw = field.text().strip()
        if not raw:
            return None
        try:
            return int(raw)
        except Exception as exc:
            raise ValueError(f"Invalid {label}: {raw}") from exc

    @staticmethod
    def _tri_value(cb: QCheckBox) -> bool | None:
        state = cb.checkState()
        if state == Qt.PartiallyChecked:
            return None
        return state == Qt.Checked

    def values(self) -> dict[str, object]:
        return {
            "rt_prio": self._read_int(self.rt_prio, "rt.prio"),
            "rt_time_soft": self._read_int(self.rt_soft, "rt.time.soft"),
            "rt_time_hard": self._read_int(self.rt_hard, "rt.time.hard"),
            "nice_level": self._read_int(self.nice_level, "nice.level"),
            "uclamp_min": self._read_int(self.uclamp_min, "uclamp.min"),
            "uclamp_max": self._read_int(self.uclamp_max, "uclamp.max"),
            "rlimits_enabled": self._tri_value(self.rlimits_enabled),
            "rtkit_enabled": self._tri_value(self.rtkit_enabled),
            "rtportal_enabled": self._tri_value(self.rtportal_enabled),
            "cpu_zero_denormals": self._tri_value(self.cpu_zero_denormals),
        }


class PipeWirePulseLatencyDialog(QDialog):
    def __init__(self, current: dict[str, object] | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire pulse latency")
        self.resize(520, 260)
        current = current or {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Configure global pipewire-pulse latency properties."))
        root.addWidget(QLabel("Examples: 64/48000, 128/48000, 256/48000"))

        form = QFormLayout()
        self.min_req = QLineEdit(str(current.get("min_req") or ""))
        self.min_req.setPlaceholderText("pulse.min.req (e.g. 64/48000)")
        form.addRow("pulse.min.req", self.min_req)

        self.default_req = QLineEdit(str(current.get("default_req") or ""))
        self.default_req.setPlaceholderText("pulse.default.req (optional)")
        form.addRow("pulse.default.req", self.default_req)

        self.min_quantum = QLineEdit(str(current.get("min_quantum") or ""))
        self.min_quantum.setPlaceholderText("pulse.min.quantum (optional)")
        form.addRow("pulse.min.quantum", self.min_quantum)
        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def values(self) -> dict[str, object]:
        def _clean(value: str) -> str | None:
            raw = value.strip()
            return raw or None

        return {
            "min_req": _clean(self.min_req.text()),
            "default_req": _clean(self.default_req.text()),
            "min_quantum": _clean(self.min_quantum.text()),
        }


class PipeWirePulseRulesDialog(QDialog):
    def __init__(self, current: list[dict[str, object]] | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire pulse app rules")
        self.resize(660, 460)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Configure per-app pipewire-pulse latency rules as JSON."))
        root.addWidget(QLabel("Each rule needs 'match' (object) and 'latency' (string)."))

        self.rules_edit = QTextEdit()
        if isinstance(current, list):
            self.rules_edit.setText(json.dumps(current, indent=2))
        else:
            self.rules_edit.setText(
                json.dumps(
                    [
                        {
                            "match": {"application.process.binary": "reaper"},
                            "latency": "64/48000",
                        }
                    ],
                    indent=2,
                )
            )
        root.addWidget(self.rules_edit)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def values(self) -> list[dict[str, object]]:
        raw = self.rules_edit.toPlainText().strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            raise ValueError("Invalid JSON in pulse rules") from exc
        if not isinstance(parsed, list):
            raise ValueError("Pulse rules must be a JSON list")
        out: list[dict[str, object]] = []
        for index, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Rule #{index} must be an object")
            match = item.get("match")
            latency = item.get("latency")
            if not isinstance(match, dict) or not match:
                raise ValueError(f"Rule #{index} requires non-empty 'match' object")
            if not isinstance(latency, str) or not latency.strip():
                raise ValueError(f"Rule #{index} requires non-empty 'latency' string")
            clean: dict[str, object] = {
                "match": {str(k): v for k, v in match.items() if isinstance(k, str) and v is not None},
                "latency": latency.strip(),
            }
            for key in ("default_req", "min_quantum"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    clean[key] = value.strip()
            out.append(clean)
        return out


class SystemdServiceRtDialog(QDialog):
    def __init__(
        self,
        *,
        service_label: str,
        current: dict[str, object] | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Systemd service tuning: {service_label}")
        self.resize(540, 300)
        current = current or {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Configure systemd scheduling + affinity drop-in values."))

        form = QFormLayout()
        self.policy = QComboBox()
        self.policy.addItem("fifo", "fifo")
        self.policy.addItem("rr", "rr")
        self.policy.addItem("other", "other")
        policy = str(current.get("policy") or "fifo").strip().lower()
        idx = self.policy.findData(policy)
        self.policy.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("CPUSchedulingPolicy", self.policy)

        self.priority = QLineEdit(str(current.get("priority") or ""))
        self.priority.setPlaceholderText("1..99 (empty keeps default)")
        form.addRow("CPUSchedulingPriority", self.priority)

        self.cpu_list = QLineEdit("")
        self.cpu_list.setPlaceholderText("e.g. 2-3 or 2,3")
        cores = current.get("cpus")
        if isinstance(cores, list) and cores:
            try:
                from audioknob_gui.core.irq import cpu_list_from_cores

                self.cpu_list.setText(cpu_list_from_cores([int(x) for x in cores]))
            except Exception:
                self.cpu_list.setText(",".join(str(x) for x in cores if isinstance(x, int)))
        form.addRow("CPUAffinity", self.cpu_list)
        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    @staticmethod
    def _read_priority(raw: str) -> int | None:
        text = raw.strip()
        if not text:
            return None
        try:
            value = int(text)
        except Exception as exc:
            raise ValueError(f"Invalid priority: {raw}") from exc
        if value < 1 or value > 99:
            raise ValueError("Priority must be between 1 and 99")
        return value

    @staticmethod
    def _read_cpus(raw: str) -> list[int] | None:
        text = raw.strip()
        if not text:
            return None
        try:
            from audioknob_gui.core.irq import parse_cpu_list

            cpus = sorted(parse_cpu_list(text))
        except Exception as exc:
            raise ValueError(f"Invalid CPU list: {raw}") from exc
        return cpus or None

    def values(self) -> dict[str, object]:
        return {
            "policy": str(self.policy.currentData() or "fifo"),
            "priority": self._read_priority(self.priority.text()),
            "cpus": self._read_cpus(self.cpu_list.text()),
        }


PIPEWIRE_RT_FULL_LIMITS: dict[str, object] = {
    "enabled": True,
    "group": "pipewire",
    "rtprio": 95,
    "nice": -19,
    "memlock": 4194304,
}

PIPEWIRE_RT_FULL_MODULE: dict[str, object] = {
    "rt_prio": 88,
    "rt_time_soft": None,
    "rt_time_hard": None,
    "nice_level": -11,
    "rlimits_enabled": True,
    "rtkit_enabled": True,
    "rtportal_enabled": True,
    "uclamp_min": None,
    "uclamp_max": None,
    "cpu_zero_denormals": None,
}

PIPEWIRE_RT_SAFE_LIMITS: dict[str, object] = {
    "enabled": False,
}

PIPEWIRE_RT_SAFE_MODULE: dict[str, object] = {
    "rt_prio": 88,
    "rt_time_soft": None,
    "rt_time_hard": None,
    "nice_level": -11,
    "rlimits_enabled": False,
    "rtkit_enabled": True,
    "rtportal_enabled": True,
    "uclamp_min": None,
    "uclamp_max": None,
    "cpu_zero_denormals": None,
}

PIPEWIRE_RT_MUTED_TEXT_STYLE = "color: #aeb8c4;"


def _normalized_pipewire_rt_limits(current: dict[str, object] | None) -> dict[str, object]:
    current = current or {}
    enabled = current.get("enabled")
    return {
        "enabled": bool(enabled) if enabled is not None else True,
        "group": str(current.get("group") or "pipewire"),
        "rtprio": int(current.get("rtprio") or 95),
        "nice": int(current.get("nice") or -19),
        "memlock": int(current.get("memlock") or 4194304),
    }


def _normalized_pipewire_rt_module(current: dict[str, object] | None) -> dict[str, object]:
    current = current or {}
    return {
        "rt_prio": int(current.get("rt_prio") or 88),
        "rt_time_soft": current.get("rt_time_soft"),
        "rt_time_hard": current.get("rt_time_hard"),
        "nice_level": int(current.get("nice_level") or -11),
        "rlimits_enabled": (
            bool(current.get("rlimits_enabled"))
            if current.get("rlimits_enabled") is not None
            else True
        ),
        "rtkit_enabled": (
            bool(current.get("rtkit_enabled"))
            if current.get("rtkit_enabled") is not None
            else True
        ),
        "rtportal_enabled": (
            bool(current.get("rtportal_enabled"))
            if current.get("rtportal_enabled") is not None
            else True
        ),
        "uclamp_min": current.get("uclamp_min"),
        "uclamp_max": current.get("uclamp_max"),
        "cpu_zero_denormals": current.get("cpu_zero_denormals"),
    }


def infer_pipewire_rt_preset(
    limits_current: dict[str, object] | None,
    module_current: dict[str, object] | None,
) -> str:
    limits = _normalized_pipewire_rt_limits(limits_current)
    module = _normalized_pipewire_rt_module(module_current)
    if limits == PIPEWIRE_RT_FULL_LIMITS and module == PIPEWIRE_RT_FULL_MODULE:
        return "full_rt"

    safe_limits_ok = limits.get("enabled") is False
    safe_module_ok = all(module.get(key) == value for key, value in PIPEWIRE_RT_SAFE_MODULE.items())
    if safe_limits_ok and safe_module_ok:
        return "safe_rt"
    return "custom"


class PipeWireRtSetupDialog(QDialog):
    _PRESETS: dict[str, dict[str, str]] = {
        "safe_rt": {
            "label": "Safe RT",
            "brief": "Best default for most systems",
            "desc": (
                "Lower-friction setup. Does not write PAM limits and relies on RTKit/portal "
                "fallbacks instead."
            ),
        },
        "full_rt": {
            "label": "Full RT",
            "brief": "Use PAM limits for stronger RT access",
            "desc": (
                "Best for dedicated audio machines. Writes PAM limits and keeps all three "
                "PipeWire realtime paths available."
            ),
        },
        "custom": {
            "label": "Custom",
            "brief": "Fine-tune the technical details",
            "desc": "Use this if you need to tune priorities, limits, or fallback behavior yourself.",
        },
    }

    def __init__(
        self,
        limits_current: dict[str, object] | None,
        module_current: dict[str, object] | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire RT")
        self.resize(560, 620)
        limits_current = _normalized_pipewire_rt_limits(limits_current)
        module_current = _normalized_pipewire_rt_module(module_current)
        self._limits_defaults = dict(limits_current)
        self._module_defaults = dict(module_current)
        self._preset_buttons: dict[str, QPushButton] = {}
        self._selected_preset = "safe_rt"

        root = QVBoxLayout(self)
        root.setSpacing(12)

        intro = QLabel(
            "<b>Pick a PipeWire realtime mode.</b><br>"
            "Start with Safe RT for most systems. Use Full RT if you want PAM limits and the strongest RT path."
        )
        intro.setTextFormat(Qt.RichText)
        intro.setWordWrap(True)
        root.addWidget(intro)

        mode_box = QGroupBox("PipeWire RT Mode")
        self._style_section_box(mode_box)
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.setSpacing(10)
        mode_layout.setContentsMargins(12, 24, 12, 12)

        picker_hint = QLabel("Choose the level of control you want.")
        picker_hint.setWordWrap(True)
        picker_hint.setStyleSheet(PIPEWIRE_RT_MUTED_TEXT_STYLE)
        mode_layout.addWidget(picker_hint)

        preset_cards = QHBoxLayout()
        preset_cards.setSpacing(8)
        for preset_key in ("safe_rt", "full_rt", "custom"):
            preset_cards.addWidget(self._build_preset_button(preset_key), 1)
        mode_layout.addLayout(preset_cards)

        self._preset_desc = QLabel()
        self._preset_desc.setWordWrap(True)
        self._preset_desc.setStyleSheet(PIPEWIRE_RT_MUTED_TEXT_STYLE)
        mode_layout.addWidget(self._preset_desc)

        self._preset_summary = QLabel()
        self._preset_summary.setWordWrap(True)
        self._preset_summary.setTextFormat(Qt.RichText)
        self._preset_summary.setStyleSheet(
            "background-color: #20252b; border: 1px solid #323840; border-radius: 10px; padding: 10px 12px;"
        )
        mode_layout.addWidget(self._preset_summary)

        advanced_row = QHBoxLayout()
        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setText("Advanced tuning")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._advanced_toggle.setArrowType(Qt.RightArrow)
        advanced_row.addWidget(self._advanced_toggle, 0, Qt.AlignLeft)
        advanced_row.addStretch(1)
        mode_layout.addLayout(advanced_row)

        self._advanced_hint = QLabel(
            "Open this only if you want to change exact limits or fallback flags. "
            "CPU affinity and core pinning live in the Cores & IRQ tab."
        )
        self._advanced_hint.setWordWrap(True)
        self._advanced_hint.setStyleSheet(PIPEWIRE_RT_MUTED_TEXT_STYLE)
        mode_layout.addWidget(self._advanced_hint)
        root.addWidget(mode_box)

        self._advanced_panel = QWidget()
        advanced_root = QVBoxLayout(self._advanced_panel)
        advanced_root.setContentsMargins(0, 0, 0, 0)
        advanced_root.setSpacing(10)

        # ── RT Limits (permissions) ───────────────────────────────────────
        limits_box = QGroupBox("RT Permissions")
        self._style_section_box(limits_box)
        limits_grid = QGridLayout(limits_box)
        limits_grid.setSpacing(8)
        limits_grid.setContentsMargins(12, 24, 12, 12)
        limits_grid.setColumnStretch(1, 1)
        limits_grid.setColumnStretch(3, 1)

        limits_intro = QLabel(
            "Only needed for Full RT or a custom setup that writes PAM limits."
        )
        limits_intro.setWordWrap(True)
        limits_intro.setStyleSheet(PIPEWIRE_RT_MUTED_TEXT_STYLE)
        limits_grid.addWidget(limits_intro, 0, 0, 1, 4)

        self.limits_enabled = QCheckBox("Enable RT limits (PAM limits)")
        limits_enabled = limits_current.get("enabled")
        self.limits_enabled.setChecked(bool(limits_enabled) if limits_enabled is not None else True)
        self.limits_enabled.setToolTip(
            "Grant realtime permissions via PAM limits (rtprio/nice/memlock). "
            "Disable to avoid writing limits; use Reset to remove existing limits."
        )
        self.limits_enabled.stateChanged.connect(self._on_limits_toggle)
        limits_grid.addWidget(self.limits_enabled, 1, 0, 1, 4)

        limits_grid.addWidget(QLabel("Group"), 2, 0)
        self.group = QComboBox()
        self.group.addItem("Auto (pipewire \u2192 audio \u2192 realtime)", "")
        for g in ["pipewire", "audio", "realtime"]:
            self.group.addItem(g, g)
        current_group = limits_current.get("group")
        if current_group:
            idx = self.group.findData(current_group)
            if idx >= 0:
                self.group.setCurrentIndex(idx)
        limits_grid.addWidget(self.group, 2, 1, 1, 3)

        limits_grid.addWidget(QLabel("RT priority ceiling"), 3, 0)
        self.rtprio = QLineEdit(str(limits_current.get("rtprio") or ""))
        self.rtprio.setPlaceholderText("95")
        limits_grid.addWidget(self.rtprio, 3, 1)
        limits_grid.addWidget(QLabel("Nice limit"), 3, 2)
        self.nice = QLineEdit(str(limits_current.get("nice") or ""))
        self.nice.setPlaceholderText("-19")
        limits_grid.addWidget(self.nice, 3, 3)

        limits_grid.addWidget(QLabel("Memory lock limit (KB)"), 4, 0)
        self.memlock = QLineEdit(str(limits_current.get("memlock") or ""))
        self.memlock.setPlaceholderText("4194304")
        limits_grid.addWidget(self.memlock, 4, 1, 1, 3)

        advanced_root.addWidget(limits_box)
        self._on_limits_toggle()

        # ── module-rt behavior ────────────────────────────────────────────
        module_box = QGroupBox("Advanced PipeWire RT Options")
        self._style_section_box(module_box)
        module_grid = QGridLayout(module_box)
        module_grid.setSpacing(8)
        module_grid.setContentsMargins(12, 24, 12, 12)
        module_grid.setColumnStretch(1, 1)
        module_grid.setColumnStretch(3, 1)

        module_intro = QLabel(
            "Fine-tune how PipeWire asks for realtime scheduling. Leave blanks to keep PipeWire defaults."
        )
        module_intro.setWordWrap(True)
        module_intro.setStyleSheet(PIPEWIRE_RT_MUTED_TEXT_STYLE)
        module_grid.addWidget(module_intro, 0, 0, 1, 4)

        module_grid.addWidget(QLabel("PipeWire RT priority"), 1, 0)
        self.rt_prio = QLineEdit(str(module_current.get("rt_prio") or ""))
        self.rt_prio.setPlaceholderText("88")
        module_grid.addWidget(self.rt_prio, 1, 1)
        module_grid.addWidget(QLabel("Nice level"), 1, 2)
        self.nice_level = QLineEdit(str(module_current.get("nice_level") or ""))
        self.nice_level.setPlaceholderText("-11")
        module_grid.addWidget(self.nice_level, 1, 3)

        module_grid.addWidget(QLabel("Soft RT budget"), 2, 0)
        self.rt_soft = QLineEdit(str(module_current.get("rt_time_soft") or ""))
        self.rt_soft.setPlaceholderText("leave blank")
        module_grid.addWidget(self.rt_soft, 2, 1)
        module_grid.addWidget(QLabel("Hard RT budget"), 2, 2)
        self.rt_hard = QLineEdit(str(module_current.get("rt_time_hard") or ""))
        self.rt_hard.setPlaceholderText("leave blank")
        module_grid.addWidget(self.rt_hard, 2, 3)

        module_grid.addWidget(QLabel("Util clamp min"), 3, 0)
        self.uclamp_min = QLineEdit(str(module_current.get("uclamp_min") or ""))
        self.uclamp_min.setPlaceholderText("leave blank")
        module_grid.addWidget(self.uclamp_min, 3, 1)
        module_grid.addWidget(QLabel("Util clamp max"), 3, 2)
        self.uclamp_max = QLineEdit(str(module_current.get("uclamp_max") or ""))
        self.uclamp_max.setPlaceholderText("leave blank")
        module_grid.addWidget(self.uclamp_max, 3, 3)

        toggles_label = QLabel("Fallback paths and optional hints  (\u2015 = keep PipeWire default)")
        toggles_label.setStyleSheet(PIPEWIRE_RT_MUTED_TEXT_STYLE)
        module_grid.addWidget(toggles_label, 4, 0, 1, 4)

        self.rlimits_enabled = QCheckBox("Use PAM/rlimits path")
        self.rlimits_enabled.setTristate(True)
        _set_tristate_default(self.rlimits_enabled, module_current.get("rlimits_enabled"))
        self.rlimits_enabled.setToolTip(
            "Underlying key: rlimits.enabled\n"
            "Try to acquire realtime scheduling via OS/PAM limits (primary path).\n"
            "Indeterminate (\u2015) = PipeWire default (true)."
        )
        module_grid.addWidget(self.rlimits_enabled, 5, 0, 1, 2)

        self.rtkit_enabled = QCheckBox("Allow RTKit fallback")
        self.rtkit_enabled.setTristate(True)
        _set_tristate_default(self.rtkit_enabled, module_current.get("rtkit_enabled"))
        self.rtkit_enabled.setToolTip(
            "Underlying key: rtkit.enabled\n"
            "Fall back to the RTKit daemon for realtime scheduling.\n"
            "Indeterminate (\u2015) = PipeWire default (true)."
        )
        module_grid.addWidget(self.rtkit_enabled, 5, 2, 1, 2)

        self.rtportal_enabled = QCheckBox("Allow realtime portal fallback")
        self.rtportal_enabled.setTristate(True)
        _set_tristate_default(self.rtportal_enabled, module_current.get("rtportal_enabled"))
        self.rtportal_enabled.setToolTip(
            "Underlying key: rtportal.enabled\n"
            "Fall back to the XDG realtime portal for realtime scheduling.\n"
            "Indeterminate (\u2015) = PipeWire default (true)."
        )
        module_grid.addWidget(self.rtportal_enabled, 6, 0, 1, 2)

        self.cpu_zero_denormals = QCheckBox("Zero denormals hint")
        self.cpu_zero_denormals.setTristate(True)
        PipeWireRtModuleDialog._set_tristate(
            self.cpu_zero_denormals,
            module_current.get("cpu_zero_denormals"),
        )
        self.cpu_zero_denormals.setToolTip(
            "Underlying key: cpu.zero.denormals\n"
            "Set denormal handling hint for module-rt where supported.\n"
            "Indeterminate (\u2015) = not set."
        )
        module_grid.addWidget(self.cpu_zero_denormals, 6, 2, 1, 2)

        advanced_root.addWidget(module_box)
        root.addWidget(self._advanced_panel)
        root.addStretch(1)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        status_btn = btns.addButton("Status Check...", QDialogButtonBox.ActionRole)
        status_btn.clicked.connect(self._show_status_check)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        preset_key = infer_pipewire_rt_preset(limits_current, module_current)
        self._advanced_toggle.toggled.connect(self._on_advanced_toggled)
        self._select_preset(preset_key, apply_values=False, reveal_advanced=False)

    # ── Preset helpers ────────────────────────────────────────────────────

    @staticmethod
    def _style_section_box(box: QGroupBox) -> None:
        box.setStyleSheet(
            """
            QGroupBox {
                background-color: #232629;
                border: 1px solid #343942;
                border-radius: 10px;
                margin-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #f0f0f0;
                font-weight: 600;
            }
            """
        )

    def _build_preset_button(self, preset_key: str) -> QPushButton:
        info = self._PRESETS[preset_key]
        btn = QPushButton(f"{info['label']}\n{info['brief']}")
        btn.setCheckable(True)
        btn.setMinimumHeight(72)
        btn.setStyleSheet(
            """
            QPushButton {
                text-align: left;
                padding: 10px 12px;
                border-radius: 10px;
                border: 1px solid #343942;
                background-color: #20252b;
                color: #e8e8e8;
            }
            QPushButton:hover {
                background-color: #252b33;
            }
            QPushButton:checked {
                background-color: #273649;
                border: 1px solid #6b93bf;
                color: #f3f6fb;
            }
            """
        )
        btn.clicked.connect(lambda _checked=False, key=preset_key: self._on_preset_button_clicked(key))
        self._preset_buttons[preset_key] = btn
        return btn

    def _update_preset_copy(self) -> None:
        preset = self._selected_preset
        self._preset_desc.setText(self._PRESETS.get(preset or "", {}).get("desc", ""))
        if preset == "safe_rt":
            summary = (
                "<b>Best for:</b> most systems and first-time setup.<br>"
                "<b>Changes:</b> keeps PipeWire on RTKit/portal fallbacks and does not write PAM limits."
            )
        elif preset == "full_rt":
            summary = (
                "<b>Best for:</b> dedicated audio machines where you want the strongest RT path.<br>"
                "<b>Changes:</b> writes PAM limits, then keeps rlimits, portal, and RTKit available."
            )
        else:
            summary = (
                "<b>Best for:</b> uncommon setups that need manual limits or fallback tuning.<br>"
                "<b>Tip:</b> start from Safe RT or Full RT, then open Advanced tuning only if you need to fine-tune."
            )
        self._preset_summary.setText(summary)

    def _set_advanced_visible(self, visible: bool) -> None:
        self._advanced_toggle.blockSignals(True)
        self._advanced_toggle.setChecked(bool(visible))
        self._advanced_toggle.blockSignals(False)
        self._advanced_panel.setVisible(visible)
        self._advanced_toggle.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)

    def _select_preset(self, preset: str, *, apply_values: bool, reveal_advanced: bool) -> None:
        self._selected_preset = preset
        for key, btn in self._preset_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(key == preset)
            btn.blockSignals(False)
        self._update_preset_copy()
        if apply_values and preset == "full_rt":
            self._apply_full_rt()
        elif apply_values and preset == "safe_rt":
            self._apply_safe_rt()
        self._set_advanced_visible(reveal_advanced)

    def _on_preset_button_clicked(self, preset: str) -> None:
        self._select_preset(
            preset,
            apply_values=preset in ("safe_rt", "full_rt"),
            reveal_advanced=(preset == "custom"),
        )

    def _on_advanced_toggled(self, checked: bool) -> None:
        self._set_advanced_visible(bool(checked))

    def _apply_full_rt(self) -> None:
        """Populate form with the upstream-recommended Full RT settings."""
        self.limits_enabled.setChecked(True)
        self._on_limits_toggle()
        idx = self.group.findData(PIPEWIRE_RT_FULL_LIMITS["group"])
        if idx >= 0:
            self.group.setCurrentIndex(idx)
        self.rtprio.setText(str(PIPEWIRE_RT_FULL_LIMITS["rtprio"]))
        self.nice.setText(str(PIPEWIRE_RT_FULL_LIMITS["nice"]))
        self.memlock.setText(str(PIPEWIRE_RT_FULL_LIMITS["memlock"]))
        self.rt_prio.setText(str(PIPEWIRE_RT_FULL_MODULE["rt_prio"]))
        self.nice_level.setText(str(PIPEWIRE_RT_FULL_MODULE["nice_level"]))
        self.rt_soft.setText("")
        self.rt_hard.setText("")
        self.uclamp_min.setText("")
        self.uclamp_max.setText("")
        self.rlimits_enabled.setCheckState(Qt.Checked)
        self.rtkit_enabled.setCheckState(Qt.Checked)
        self.rtportal_enabled.setCheckState(Qt.Checked)
        PipeWireRtModuleDialog._set_tristate(
            self.cpu_zero_denormals,
            PIPEWIRE_RT_FULL_MODULE["cpu_zero_denormals"],
        )

    def _apply_safe_rt(self) -> None:
        """Populate form with Safe RT (RTKit/portal only) settings."""
        self.limits_enabled.setChecked(False)
        self._on_limits_toggle()
        group = self._limits_defaults.get("group")
        idx = self.group.findData(group) if group else -1
        self.group.setCurrentIndex(idx if idx >= 0 else 0)
        self.rtprio.setText(str(self._limits_defaults.get("rtprio") or ""))
        self.nice.setText(str(self._limits_defaults.get("nice") or ""))
        self.memlock.setText(str(self._limits_defaults.get("memlock") or ""))
        self.rt_prio.setText(str(PIPEWIRE_RT_SAFE_MODULE["rt_prio"]))
        self.rt_soft.setText("")
        self.rt_hard.setText("")
        self.nice_level.setText(str(PIPEWIRE_RT_SAFE_MODULE["nice_level"]))
        self.uclamp_min.setText("")
        self.uclamp_max.setText("")
        self.rlimits_enabled.setCheckState(Qt.Unchecked)
        self.rtkit_enabled.setCheckState(Qt.Checked)
        self.rtportal_enabled.setCheckState(Qt.Checked)
        PipeWireRtModuleDialog._set_tristate(
            self.cpu_zero_denormals,
            PIPEWIRE_RT_SAFE_MODULE["cpu_zero_denormals"],
        )

    # ── Slot / helpers ────────────────────────────────────────────────────

    def _on_limits_toggle(self, *_args) -> None:
        enabled = self.limits_enabled.isChecked()
        for widget in (self.group, self.rtprio, self.nice, self.memlock):
            widget.setEnabled(enabled)

    @staticmethod
    def _read_int(field: QLineEdit, label: str) -> int | None:
        raw = field.text().strip()
        if not raw:
            return None
        try:
            return int(raw)
        except Exception as exc:
            raise ValueError(f"Invalid {label}: {raw}") from exc

    def limits_values(self) -> dict[str, object]:
        group = self.group.currentData()
        return {
            "group": str(group).strip() if group else None,
            "rtprio": self._read_int(self.rtprio, "rtprio"),
            "nice": self._read_int(self.nice, "nice"),
            "memlock": self._read_int(self.memlock, "memlock"),
            "enabled": bool(self.limits_enabled.isChecked()),
        }

    def module_values(self) -> dict[str, object]:
        return {
            "rt_prio": PipeWireRtModuleDialog._read_int(self.rt_prio, "rt.prio"),
            "rt_time_soft": PipeWireRtModuleDialog._read_int(self.rt_soft, "rt.time.soft"),
            "rt_time_hard": PipeWireRtModuleDialog._read_int(self.rt_hard, "rt.time.hard"),
            "nice_level": PipeWireRtModuleDialog._read_int(self.nice_level, "nice.level"),
            "uclamp_min": PipeWireRtModuleDialog._read_int(self.uclamp_min, "uclamp.min"),
            "uclamp_max": PipeWireRtModuleDialog._read_int(self.uclamp_max, "uclamp.max"),
            "rlimits_enabled": PipeWireRtModuleDialog._tri_value(self.rlimits_enabled),
            "rtkit_enabled": PipeWireRtModuleDialog._tri_value(self.rtkit_enabled),
            "rtportal_enabled": PipeWireRtModuleDialog._tri_value(self.rtportal_enabled),
            "cpu_zero_denormals": PipeWireRtModuleDialog._tri_value(self.cpu_zero_denormals),
        }

    def _show_status_check(self) -> None:
        try:
            from audioknob_gui.gui import status as gui_status
        except Exception:
            return
        parent = self.parent()
        if parent is None:
            return
        try:
            gui_status.show_cli_status(parent, PIPEWIRE_RT_SETUP)
        except Exception:
            pass


def _set_tristate_default(cb: QCheckBox, value: object) -> None:
    if value is None:
        cb.setCheckState(Qt.Checked)
        return
    PipeWireRtModuleDialog._set_tristate(cb, value)


class PipeWireDataLoopsDialog(QDialog):
    def __init__(self, current: dict[str, object] | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire data loop affinity")
        self.resize(600, 420)
        current = current or {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Configure context.data-loops (advanced)."))
        root.addWidget(QLabel("Enter JSON for the data-loops list (leave empty to unset)."))

        form = QFormLayout()
        self.num_loops = QLineEdit(str(current.get("num_data_loops") or ""))
        self.num_loops.setPlaceholderText("leave empty")
        form.addRow("context.num-data-loops", self.num_loops)
        root.addLayout(form)

        self.loops = QTextEdit()
        loops_value = current.get("data_loops")
        if isinstance(loops_value, list):
            self.loops.setText(json.dumps(loops_value, indent=2))
        self.loops.setPlaceholderText('[{"thread.affinity":[2,3],"loop.rt-prio":88}]')
        root.addWidget(self.loops)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        raw_num = self.num_loops.text().strip()
        if raw_num:
            try:
                values["num_data_loops"] = int(raw_num)
            except Exception as exc:
                raise ValueError(f"Invalid num-data-loops: {raw_num}") from exc
        else:
            values["num_data_loops"] = None

        raw_loops = self.loops.toPlainText().strip()
        if raw_loops:
            try:
                parsed = json.loads(raw_loops)
            except Exception as exc:
                raise ValueError("Invalid JSON in data-loops") from exc
            if not isinstance(parsed, list) or not all(isinstance(x, dict) for x in parsed):
                raise ValueError("data-loops must be a JSON list of objects")
            values["data_loops"] = parsed
        else:
            values["data_loops"] = None
        return values


class PipeWireRtLimitsGroupDialog(QDialog):
    def __init__(self, current_group: str | None, candidates: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire RT limits group")
        self.resize(420, 180)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Select which group should receive PipeWire RT limits."))

        self.combo = QComboBox()
        self.combo.addItem("Auto (pipewire -> audio -> realtime)", "")
        for group in candidates:
            self.combo.addItem(group, group)
        if current_group:
            idx = self.combo.findData(current_group)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        root.addWidget(self.combo)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def selected_group(self) -> str | None:
        data = self.combo.currentData()
        return str(data).strip() if data else None


class WirePlumberAlsaDialog(QDialog):
    def __init__(self, current: dict[str, object] | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("WirePlumber ALSA USB tuning")
        self.resize(480, 260)
        current = current or {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Tune ALSA USB properties (advanced). Leave empty to keep defaults."))

        form = QFormLayout()
        self.period_size = QLineEdit(str(current.get("period_size") or ""))
        form.addRow("api.alsa.period-size", self.period_size)
        self.period_num = QLineEdit(str(current.get("period_num") or ""))
        form.addRow("api.alsa.period-num", self.period_num)
        self.headroom = QLineEdit(str(current.get("headroom") or ""))
        form.addRow("api.alsa.headroom", self.headroom)

        self.disable_batch = QCheckBox("api.alsa.disable-batch")
        self.disable_batch.setTristate(True)
        value = current.get("disable_batch")
        if value is None:
            self.disable_batch.setCheckState(Qt.PartiallyChecked)
        elif bool(value):
            self.disable_batch.setCheckState(Qt.Checked)
        else:
            self.disable_batch.setCheckState(Qt.Unchecked)
        form.addRow(self.disable_batch)

        root.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def values(self) -> dict[str, object]:
        def _read_int(field: QLineEdit, label: str) -> int | None:
            raw = field.text().strip()
            if not raw:
                return None
            try:
                return int(raw)
            except Exception as exc:
                raise ValueError(f"Invalid {label}: {raw}") from exc

        state = self.disable_batch.checkState()
        if state == Qt.PartiallyChecked:
            disable = None
        else:
            disable = state == Qt.Checked

        return {
            "period_size": _read_int(self.period_size, "period-size"),
            "period_num": _read_int(self.period_num, "period-num"),
            "headroom": _read_int(self.headroom, "headroom"),
            "disable_batch": disable,
        }


class ProAudioProfileDialog(QDialog):
    def __init__(self, current_device: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire Pro Audio profile")
        self.resize(520, 300)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Select a device to switch to the Pro Audio profile."))

        row = QHBoxLayout()
        self.combo = QComboBox()
        row.addWidget(self.combo)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_devices)
        row.addWidget(refresh_btn)
        root.addLayout(row)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.ok_btn: QPushButton | None = None
        self._devices: list[tuple[str, str]] = []
        self._refresh_devices()
        if current_device:
            idx = self.combo.findData(current_device)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
                self._update_status()
        self.combo.currentIndexChanged.connect(self._update_status)

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.ok_btn = btns.button(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _refresh_devices(self) -> None:
        self.combo.clear()
        self._devices = []
        try:
            result = subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception as exc:
            QMessageBox.warning(self, "wpctl error", str(exc))
            return
        if result.returncode != 0:
            QMessageBox.warning(self, "wpctl error", result.stderr.strip() or "wpctl status failed")
            return
        devices = self._parse_devices(result.stdout or "")
        for dev_id, label in devices:
            self.combo.addItem(f"{dev_id}. {label}", dev_id)
            self._devices.append((dev_id, label))
        if not devices:
            self.combo.addItem("No devices found", "")
        self._update_status()

    def _parse_devices(self, text: str) -> list[tuple[str, str]]:
        devices: list[tuple[str, str]] = []
        in_audio = False
        in_devices = False
        for line in text.splitlines():
            raw = line.rstrip()
            if not raw.strip():
                continue
            clean = re.sub(r"^[\s│├└─]+", "", raw).strip()
            if not clean:
                continue
            if clean.startswith("Audio"):
                in_audio = True
                in_devices = False
                continue
            if clean.startswith(("Video", "Settings", "Clients")):
                in_audio = False
                in_devices = False
                continue
            if in_audio and clean.startswith("Devices:"):
                in_devices = True
                continue
            if in_audio and clean.startswith(("Sinks:", "Sources:", "Filters:", "Streams:")):
                in_devices = False
                continue
            if not in_devices:
                continue
            m = re.match(r"^(\d+)\.\s*(.+)$", clean)
            if m:
                dev_id = m.group(1).strip()
                label = m.group(2).strip()
                devices.append((dev_id, label))
        return devices

    def _update_status(self) -> None:
        device_id = self.selected_device_id()
        if not device_id:
            self.status.setText("Select a device to see Pro Audio availability.")
            if self.ok_btn is not None:
                self.ok_btn.setEnabled(False)
            return
        try:
            result = subprocess.run(
                ["wpctl", "inspect", str(device_id)],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception as exc:
            self.status.setText(f"wpctl inspect failed: {exc}")
            return
        if result.returncode != 0:
            self.status.setText(result.stderr.strip() or "wpctl inspect failed")
            return
        text = result.stdout or ""
        profiles = self._parse_profiles(text)
        current = profiles.get("current")
        pro = profiles.get("pro_audio")
        card_name = self._parse_device_name(text)
        if not pro and card_name:
            pactl_current, pactl_pro = self._pactl_profile_status(card_name)
            if pactl_current:
                current = pactl_current
            pro = pro or pactl_pro
        if pro:
            msg = "Pro Audio profile available."
            if self.ok_btn is not None:
                self.ok_btn.setEnabled(True)
        else:
            msg = "Pro Audio profile not found for this device."
            if self.ok_btn is not None:
                self.ok_btn.setEnabled(False)
        if current:
            msg += f" Current: {current}"
        self.status.setText(msg)

    @staticmethod
    def _parse_device_name(text: str) -> str | None:
        for line in text.splitlines():
            raw = line.strip()
            clean = raw.lstrip("* ").strip()
            if clean.startswith("device.name"):
                _, _, value = clean.partition("=")
                name = value.strip().strip('"')
                if name:
                    return name
        return None

    @staticmethod
    def _pactl_profile_status(card_name: str) -> tuple[str | None, bool]:
        try:
            result = subprocess.run(
                ["pactl", "list", "cards"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return None, False
        text = result.stdout or ""
        current = None
        pro = False
        in_card = False
        in_profiles = False
        for line in text.splitlines():
            raw = line.rstrip()
            if raw.strip().startswith("Name:"):
                name = raw.split(":", 1)[1].strip()
                in_card = name == card_name
                in_profiles = False
                continue
            if not in_card:
                continue
            if raw.strip().startswith("Profiles:"):
                in_profiles = True
                continue
            if raw.strip().startswith("Active Profile:"):
                current = raw.split(":", 1)[1].strip()
                continue
            if in_profiles:
                stripped = raw.strip()
                if stripped and ":" in stripped:
                    profile_key = stripped.split(":", 1)[0].strip().lower()
                    if profile_key == "pro-audio":
                        pro = True
        return current, pro

    @staticmethod
    def _parse_profiles(text: str) -> dict[str, str | None]:
        current = None
        pro_audio = None
        in_profiles = False
        for line in text.splitlines():
            raw = line.strip()
            clean = raw.lstrip("* ").strip()
            if not raw:
                continue
            low = clean.lower()
            if low.startswith("profiles:"):
                in_profiles = True
                continue
            if in_profiles and ":" in clean and not re.match(r"^\d+\.", clean):
                in_profiles = False
            if low.startswith("active profile:"):
                current = clean.split(":", 1)[1].strip()
                continue
            if in_profiles:
                m = re.match(r"^(\d+)\.\s*(.+)$", clean)
                if m:
                    name_raw = m.group(2).strip()
                    name = name_raw.split("(", 1)[0].strip()
                    if "pro audio" in name.lower() or "pro-audio" in name.lower():
                        pro_audio = name
        return {"current": current, "pro_audio": pro_audio}

    def selected_device_id(self) -> str | None:
        data = self.combo.currentData()
        return str(data).strip() if data else None

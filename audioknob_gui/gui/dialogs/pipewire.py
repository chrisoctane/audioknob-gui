from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import json
import re
import subprocess


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
            "rlimits_enabled": self._tri_value(self.rlimits_enabled),
            "rtkit_enabled": self._tri_value(self.rtkit_enabled),
            "rtportal_enabled": self._tri_value(self.rtportal_enabled),
        }


class PipeWireRtSetupDialog(QDialog):
    def __init__(
        self,
        limits_current: dict[str, object] | None,
        module_current: dict[str, object] | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PipeWire RT setup")
        self.resize(560, 460)
        limits_current = limits_current or {}
        module_current = module_current or {}
        # Used by the Safe RT preset to restore text fields/combos after edits.
        self._limits_defaults = dict(limits_current)
        self._module_defaults = dict(module_current)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Configure PipeWire realtime limits and module-rt behavior."))

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Presets:"))
        safe_btn = QPushButton("Safe RT (RTKit)")
        safe_btn.setToolTip("Use RTKit/portal and disable direct RT limits for safer operation.")
        safe_btn.clicked.connect(self._apply_safe_rt_preset)
        preset_row.addWidget(safe_btn)
        preset_row.addStretch(1)
        root.addLayout(preset_row)

        limits_box = QGroupBox("RT Limits (permissions)")
        limits_layout = QFormLayout(limits_box)
        self.limits_enabled = QCheckBox("Enable RT limits (PAM limits)")
        limits_enabled = limits_current.get("enabled")
        self.limits_enabled.setChecked(bool(limits_enabled) if limits_enabled is not None else True)
        self.limits_enabled.setToolTip(
            "Grant realtime permissions via PAM limits (rtprio/nice/memlock). "
            "Disable to avoid writing limits; use Reset to remove existing limits."
        )
        self.limits_enabled.stateChanged.connect(self._on_limits_toggle)
        limits_layout.addRow(self.limits_enabled)
        self.group = QComboBox()
        self.group.addItem("Auto (pipewire -> audio -> realtime)", "")
        for group in ["pipewire", "audio", "realtime"]:
            self.group.addItem(group, group)
        current_group = limits_current.get("group")
        if current_group:
            idx = self.group.findData(current_group)
            if idx >= 0:
                self.group.setCurrentIndex(idx)
        limits_layout.addRow("Group", self.group)
        self.rtprio = QLineEdit(str(limits_current.get("rtprio") or ""))
        limits_layout.addRow("rtprio", self.rtprio)
        self.nice = QLineEdit(str(limits_current.get("nice") or ""))
        limits_layout.addRow("nice", self.nice)
        self.memlock = QLineEdit(str(limits_current.get("memlock") or ""))
        limits_layout.addRow("memlock (KB)", self.memlock)
        root.addWidget(limits_box)
        self._on_limits_toggle()

        module_box = QGroupBox("module-rt behavior")
        module_layout = QFormLayout(module_box)
        self.rt_prio = QLineEdit(str(module_current.get("rt_prio") or ""))
        module_layout.addRow("rt.prio", self.rt_prio)
        self.rt_soft = QLineEdit(str(module_current.get("rt_time_soft") or ""))
        module_layout.addRow("rt.time.soft", self.rt_soft)
        self.rt_hard = QLineEdit(str(module_current.get("rt_time_hard") or ""))
        module_layout.addRow("rt.time.hard", self.rt_hard)
        self.nice_level = QLineEdit(str(module_current.get("nice_level") or ""))
        module_layout.addRow("nice.level", self.nice_level)

        self.rlimits_enabled = QCheckBox("rlimits.enabled")
        self.rlimits_enabled.setTristate(True)
        _set_tristate_default(self.rlimits_enabled, module_current.get("rlimits_enabled"))
        self.rlimits_enabled.setToolTip(
            "Use OS limits (PAM limits) when requesting realtime priority."
        )
        module_layout.addRow(self.rlimits_enabled)

        module_layout.addRow(QLabel("Fallback paths (permissions / brokered access):"))
        self.rtkit_enabled = QCheckBox("rtkit.enabled")
        self.rtkit_enabled.setTristate(True)
        _set_tristate_default(self.rtkit_enabled, module_current.get("rtkit_enabled"))
        self.rtkit_enabled.setToolTip(
            "Allow PipeWire to request realtime via RTKit if direct RT is not allowed."
        )
        module_layout.addRow(self.rtkit_enabled)

        self.rtportal_enabled = QCheckBox("rtportal.enabled")
        self.rtportal_enabled.setTristate(True)
        _set_tristate_default(self.rtportal_enabled, module_current.get("rtportal_enabled"))
        self.rtportal_enabled.setToolTip(
            "Allow PipeWire to request realtime via the Realtime portal (best for sandboxed apps)."
        )
        module_layout.addRow(self.rtportal_enabled)
        root.addWidget(module_box)

        root.addWidget(QLabel("Tip: Leave fields blank to keep defaults."))

        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_limits_toggle(self, *_args) -> None:
        enabled = self.limits_enabled.isChecked()
        for widget in (self.group, self.rtprio, self.nice, self.memlock):
            widget.setEnabled(enabled)

    def _apply_safe_rt_preset(self) -> None:
        self.limits_enabled.setChecked(False)
        self._on_limits_toggle()
        group = self._limits_defaults.get("group")
        if group:
            idx = self.group.findData(group)
            self.group.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.group.setCurrentIndex(0)
        self.rtprio.setText(str(self._limits_defaults.get("rtprio") or ""))
        self.nice.setText(str(self._limits_defaults.get("nice") or ""))
        self.memlock.setText(str(self._limits_defaults.get("memlock") or ""))

        self.rt_prio.setText(str(self._module_defaults.get("rt_prio") or ""))
        self.rt_soft.setText(str(self._module_defaults.get("rt_time_soft") or ""))
        self.rt_hard.setText(str(self._module_defaults.get("rt_time_hard") or ""))
        self.nice_level.setText(str(self._module_defaults.get("nice_level") or ""))
        self.rlimits_enabled.setCheckState(Qt.Unchecked)
        self.rtkit_enabled.setCheckState(Qt.Checked)
        self.rtportal_enabled.setCheckState(Qt.Checked)

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
            "rlimits_enabled": PipeWireRtModuleDialog._tri_value(self.rlimits_enabled),
            "rtkit_enabled": PipeWireRtModuleDialog._tri_value(self.rtkit_enabled),
            "rtportal_enabled": PipeWireRtModuleDialog._tri_value(self.rtportal_enabled),
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
            gui_status.show_cli_status(parent, "pipewire_rt_setup")
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

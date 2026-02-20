from __future__ import annotations

from types import SimpleNamespace

from audioknob_gui.gui.main_window import MainWindow


class _DummyCorePlan:
    _linked_core_plan_enabled = MainWindow._linked_core_plan_enabled
    _sanitize_core_plan_list = MainWindow._sanitize_core_plan_list
    _invert_core_selection = MainWindow._invert_core_selection
    _audio_core_state_keys = MainWindow._audio_core_state_keys
    _housekeeping_core_state_keys = MainWindow._housekeeping_core_state_keys
    _apply_linked_core_plan = MainWindow._apply_linked_core_plan

    def __init__(self, *, linked: bool = True) -> None:
        self.state: dict[str, object] = {"core_plan_linked": linked}

    def _cpu_core_universe(self) -> list[int]:
        return [0, 1, 2, 3]


class _DummyTimer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _DummyMonitorDialog:
    def __init__(self) -> None:
        self._timer = _DummyTimer()
        self._running = True
        self._closing = False
        self.stop_called = False
        self.delete_later_called = False

    def _stop(self) -> None:
        self.stop_called = True

    def deleteLater(self) -> None:
        self.delete_later_called = True


class _DummyMonitorUi:
    _stop_monitor_dialog = MainWindow._stop_monitor_dialog

    def __init__(self) -> None:
        self._xrun_dialog: object | None = "sentinel"


class _DummyViewFilter:
    _core_knob_ids = MainWindow._core_knob_ids
    _dev_knob_ids = MainWindow._dev_knob_ids
    _hidden_knob_ids = MainWindow._hidden_knob_ids
    _visible_knobs = MainWindow._visible_knobs

    def __init__(self, mode: str) -> None:
        self._view_mode = mode
        self.registry = [
            SimpleNamespace(id="kernel_workqueue_cpumask"),
            SimpleNamespace(id="cgroup_user_slice_allowed_cpus"),
            SimpleNamespace(id="irqbalance_banned_cpulist"),
            SimpleNamespace(id="kernel_clocksource_tsc"),
            SimpleNamespace(id="kernel_tsc_reliable"),
            SimpleNamespace(id="kernel_preempt_full"),
            SimpleNamespace(id="systemd_pipewire_service_rt"),
            SimpleNamespace(id="swappiness"),
        ]


def test_apply_linked_core_plan_from_audio() -> None:
    ui = _DummyCorePlan(linked=True)

    changed = ui._apply_linked_core_plan(source="audio", cores=[2, 3])

    assert changed is True
    for key in ui._audio_core_state_keys():
        assert ui.state[key] == [2, 3]
    for key in ui._housekeeping_core_state_keys():
        assert ui.state[key] == [0, 1]


def test_apply_linked_core_plan_from_housekeeping() -> None:
    ui = _DummyCorePlan(linked=True)

    changed = ui._apply_linked_core_plan(source="housekeeping", cores=[0, 1])

    assert changed is True
    for key in ui._audio_core_state_keys():
        assert ui.state[key] == [2, 3]
    for key in ui._housekeeping_core_state_keys():
        assert ui.state[key] == [0, 1]


def test_apply_linked_core_plan_noop_when_disabled() -> None:
    ui = _DummyCorePlan(linked=False)
    ui.state["irq_pinning_cpu_cores"] = [2, 3]

    changed = ui._apply_linked_core_plan(source="audio", cores=[1, 2])

    assert changed is False
    assert ui.state["irq_pinning_cpu_cores"] == [2, 3]


def test_stop_monitor_dialog_stops_background_polling() -> None:
    ui = _DummyMonitorUi()
    dialog = _DummyMonitorDialog()

    ui._stop_monitor_dialog(dialog)

    assert dialog.stop_called is True
    assert dialog._timer.stopped is True
    assert dialog._running is False
    assert dialog._closing is False


def test_stop_monitor_dialog_preserves_restart_state() -> None:
    ui = _DummyMonitorUi()
    dialog = _DummyMonitorDialog()

    ui._stop_monitor_dialog(dialog)

    assert dialog._closing is False
    assert dialog.stop_called is True
    assert dialog._timer.stopped is True


def test_core_partition_knobs_are_in_cores_tab() -> None:
    ui = _DummyViewFilter("cores")

    visible = {k.id for k in ui._visible_knobs()}

    assert "kernel_workqueue_cpumask" in visible
    assert "cgroup_user_slice_allowed_cpus" in visible
    assert "irqbalance_banned_cpulist" in visible
    assert "systemd_pipewire_service_rt" not in visible


def test_core_partition_knobs_are_not_in_dev_tab() -> None:
    ui = _DummyViewFilter("dev")

    visible = {k.id for k in ui._visible_knobs()}

    assert "kernel_workqueue_cpumask" not in visible
    assert "cgroup_user_slice_allowed_cpus" not in visible
    assert "irqbalance_banned_cpulist" not in visible
    assert "systemd_pipewire_service_rt" in visible


def test_tsc_knobs_are_in_main_tab() -> None:
    ui = _DummyViewFilter("all")

    visible = {k.id for k in ui._visible_knobs()}

    assert "kernel_clocksource_tsc" in visible
    assert "kernel_tsc_reliable" in visible
    assert "kernel_preempt_full" not in visible


def test_tsc_knobs_are_not_in_dev_tab() -> None:
    ui = _DummyViewFilter("dev")

    visible = {k.id for k in ui._visible_knobs()}

    assert "kernel_clocksource_tsc" not in visible
    assert "kernel_tsc_reliable" not in visible
    assert "kernel_preempt_full" in visible

from __future__ import annotations

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

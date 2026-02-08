"""Tests for preset comparison status handling."""

from types import SimpleNamespace


def test_apply_baseline_statuses_keeps_operational_state() -> None:
    from audioknob_gui.gui import status as status_mod

    ui = SimpleNamespace()
    ui.registry = [SimpleNamespace(id="cpu_governor_performance_persistent", requires_root=True)]
    ui.state = {
        "baseline_statuses": {"cpu_governor_performance_persistent": "not_applied"},
        "factory_statuses": {},
    }
    ui._knob_statuses = {"cpu_governor_performance_persistent": "not_applied"}

    status_mod.apply_baseline_statuses(ui)

    assert ui._knob_statuses["cpu_governor_performance_persistent"] == "not_applied"
    assert ui._knob_preset_matches["cpu_governor_performance_persistent"] == "Matches Reference preset"
    assert ui._knob_preset_flags["cpu_governor_performance_persistent"] == {
        "reference": True,
        "factory": False,
    }


def test_apply_baseline_statuses_marks_both_reference_and_factory() -> None:
    from audioknob_gui.gui import status as status_mod

    ui = SimpleNamespace()
    ui.registry = [SimpleNamespace(id="swappiness", requires_root=True)]
    ui.state = {
        "baseline_statuses": {"swappiness": "applied"},
        "factory_statuses": {"swappiness": "applied"},
    }
    ui._knob_statuses = {"swappiness": "applied"}

    status_mod.apply_baseline_statuses(ui)

    assert ui._knob_preset_matches["swappiness"] == "Matches Reference + Factory presets"
    assert ui._knob_preset_flags["swappiness"] == {"reference": True, "factory": True}


def test_apply_baseline_statuses_ignores_partial_reference() -> None:
    from audioknob_gui.gui import status as status_mod

    ui = SimpleNamespace()
    ui.registry = [SimpleNamespace(id="cpu_governor_performance_persistent", requires_root=True)]
    ui.state = {
        "baseline_statuses": {"cpu_governor_performance_persistent": "partial"},
        "factory_statuses": {},
    }
    ui._knob_statuses = {"cpu_governor_performance_persistent": "not_applied"}

    status_mod.apply_baseline_statuses(ui)

    assert ui._knob_preset_matches == {}
    assert ui._knob_preset_flags == {}

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


def test_baseline_config_keys_include_new_dev_rt_keys() -> None:
    from audioknob_gui.gui.status import _baseline_config_keys

    keys = set(_baseline_config_keys())
    assert {
        "kernel_workqueue_cpumask_cores",
        "cgroup_user_slice_allowed_cores",
        "irqbalance_banned_cpulist_cores",
        "systemd_pipewire_service_rt_policy",
        "systemd_pipewire_service_rt_priority",
        "systemd_pipewire_service_rt_cpus",
        "systemd_wireplumber_service_rt_policy",
        "systemd_wireplumber_service_rt_priority",
        "systemd_wireplumber_service_rt_cpus",
        "core_plan_linked",
        "pipewire_uclamp_min",
        "pipewire_uclamp_max",
        "pipewire_cpu_zero_denormals",
        "pipewire_pulse_min_req",
        "pipewire_pulse_default_req",
        "pipewire_pulse_min_quantum",
        "pipewire_pulse_app_rules",
    }.issubset(keys)


def test_apply_baseline_config_clear_missing_removes_stale_selector_keys(monkeypatch) -> None:
    from audioknob_gui.gui import status as status_mod

    monkeypatch.setattr(status_mod, "save_state", lambda _state: None)

    ui = SimpleNamespace()
    ui.state = {
        "kernel_workqueue_cpumask_cores": list(range(8)),
        "irqbalance_banned_cpulist_cores": [],
        "power_profile_backend": "tuned",
    }

    status_mod._apply_baseline_config(
        ui,
        {"power_profile_backend": "auto"},
        clear_missing=True,
    )

    assert "kernel_workqueue_cpumask_cores" not in ui.state
    assert "irqbalance_banned_cpulist_cores" not in ui.state
    assert ui.state["power_profile_backend"] == "auto"

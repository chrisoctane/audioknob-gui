"""Tests for factory preset lifecycle behavior."""

from types import SimpleNamespace


def test_factory_preset_locking_and_timestamp(monkeypatch) -> None:
    from audioknob_gui.gui import status as status_mod

    monkeypatch.setattr(status_mod, "save_state", lambda _state: None)

    ui = SimpleNamespace()
    ui.registry = [SimpleNamespace(id="swappiness")]
    ui.state = {}

    assert status_mod.factory_preset_locked(ui) is False

    status_mod.set_factory_state(ui, {"swappiness": "not_applied"}, source=None, captured_at=None)

    assert status_mod.factory_preset_locked(ui) is True
    captured_at = ui.state.get("factory_captured_at")
    assert isinstance(captured_at, str) and captured_at.endswith("Z")
    assert ui.state.get("factory_source") == "capture"


def test_factory_lock_message_includes_capture_details() -> None:
    from audioknob_gui.gui import status as status_mod

    ui = SimpleNamespace()
    ui.state = {
        "factory_statuses": {"swappiness": "not_applied"},
        "factory_captured_at": "2026-02-08T20:00:00Z",
        "factory_source": "initial",
    }

    msg = status_mod._factory_lock_message(ui)
    assert "Factory Preset is immutable once set." in msg
    assert "2026-02-08T20:00:00Z" in msg
    assert "initial" in msg


def test_restore_factory_reset_config_restores_saved_selector_state(monkeypatch) -> None:
    from audioknob_gui.gui import actions as actions_mod
    from audioknob_gui.gui import status as status_mod

    monkeypatch.setattr(status_mod, "save_state", lambda _state: None)

    ui = SimpleNamespace()
    ui.state = {
        "factory_config": {
            "kernel_workqueue_cpumask_cores": None,
            "irqbalance_banned_cpulist_cores": None,
            "kernel_isolcpus_cores": None,
            "power_profile_backend": "auto",
        },
        "kernel_workqueue_cpumask_cores": list(range(32)),
        "irqbalance_banned_cpulist_cores": [],
        "kernel_isolcpus_cores": [2, 3],
        "power_profile_backend": "tuned",
    }

    assert actions_mod._restore_factory_reset_config(ui) is True
    assert ui.state["kernel_workqueue_cpumask_cores"] is None
    assert ui.state["irqbalance_banned_cpulist_cores"] is None
    assert ui.state["kernel_isolcpus_cores"] is None
    assert ui.state["power_profile_backend"] == "auto"


def test_restore_factory_reset_config_replays_saved_config(monkeypatch) -> None:
    from audioknob_gui.gui import actions, status as status_mod

    applied: dict[str, object] = {}

    def _fake_apply(ui, config, *, clear_missing=False):
        applied["ui"] = ui
        applied["config"] = dict(config)
        applied["clear_missing"] = clear_missing

    monkeypatch.setattr(status_mod, "_apply_baseline_config", _fake_apply)

    ui = SimpleNamespace(
        state={
            "factory_config": {
                "kernel_workqueue_cpumask_cores": None,
                "irqbalance_banned_cpulist_cores": None,
            }
        }
    )

    assert actions._restore_factory_reset_config(ui) is True

    assert applied["ui"] is ui
    assert applied["config"] == {
        "kernel_workqueue_cpumask_cores": None,
        "irqbalance_banned_cpulist_cores": None,
    }
    assert applied["clear_missing"] is True


def test_restore_factory_reset_config_clears_stale_state_when_factory_config_empty(monkeypatch) -> None:
    from audioknob_gui.gui import actions as actions_mod
    from audioknob_gui.gui import status as status_mod

    monkeypatch.setattr(status_mod, "save_state", lambda _state: None)

    ui = SimpleNamespace()
    ui.state = {
        "factory_config": {},
        "kernel_workqueue_cpumask_cores": list(range(32)),
        "irqbalance_banned_cpulist_cores": [],
    }

    assert actions_mod._restore_factory_reset_config(ui) is True
    assert "kernel_workqueue_cpumask_cores" not in ui.state
    assert "irqbalance_banned_cpulist_cores" not in ui.state

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

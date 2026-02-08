"""Tests for baseline status relabeling."""

from types import SimpleNamespace


def test_baseline_partial_is_not_relabelled_deviated(monkeypatch) -> None:
    from audioknob_gui.gui import status as status_mod

    ui = SimpleNamespace()
    ui.registry = [SimpleNamespace(id="cpu_governor_performance_persistent", requires_root=True)]
    ui.state = {
        "baseline_statuses": {"cpu_governor_performance_persistent": "partial"},
        "baseline_source": "initial",
        "baseline_txid_user": None,
        "baseline_txid_root": None,
        "last_user_txid": None,
        "last_root_txid": None,
    }
    ui._knob_statuses = {"cpu_governor_performance_persistent": "not_applied"}

    monkeypatch.setattr(status_mod, "parse_baseline_timestamp", lambda _ui: None)
    monkeypatch.setattr(status_mod, "collect_transaction_times", lambda _ui: ({}, False))

    status_mod.apply_baseline_statuses(ui)

    assert ui._knob_statuses["cpu_governor_performance_persistent"] == "not_applied"

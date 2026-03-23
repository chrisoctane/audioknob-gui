"""Tests for status reason helpers."""

from types import SimpleNamespace

from audioknob_gui.gui import status as status_mod


def test_sysfs_selected_value_extracts_bracket_token() -> None:
    assert status_mod._sysfs_selected_value("always [madvise] never") == "madvise"
    assert status_mod._sysfs_selected_value("[performance] powersave") == "performance"


def test_sysfs_partial_reason_includes_counts() -> None:
    reason = status_mod._sysfs_partial_reason(
        total=4,
        match=2,
        mismatch=1,
        unreadable=1,
        expected_val="performance",
    )
    assert reason is not None
    assert "matched 2/4 paths" in reason
    assert "expected performance" in reason
    assert "mismatched=1" in reason
    assert "unreadable=1" in reason


def test_config_partial_reason_reports_missing_lines() -> None:
    reason = status_mod._config_partial_reason(
        ["foo = 1", "bar = 2"],
        ["foo = 1"],
    )
    assert reason.startswith("missing lines:")
    assert "bar = 2" in reason


def test_config_partial_reason_reports_format_only_difference() -> None:
    reason = status_mod._config_partial_reason(
        ["foo = 1", "bar = 2"],
        ["bar = 2", "foo = 1", ""],
    )
    assert "formatting/order differs" in reason


def test_collect_live_checks_reports_external_systemd_note(monkeypatch) -> None:
    def _fake_run(cmd, capture_output=True, text=True):
        if cmd[:2] == ["systemctl", "is-enabled"]:
            return SimpleNamespace(stdout="disabled\n", stderr="")
        return SimpleNamespace(stdout="inactive\n", stderr="")

    monkeypatch.setattr(status_mod.subprocess, "run", _fake_run)

    knob = SimpleNamespace(
        id="irqbalance_disable",
        title="IRQ Balance",
        impl=SimpleNamespace(kind="systemd_unit_toggle", params={"unit": "irqbalance.service"}),
    )

    ui = SimpleNamespace(state={}, _knob_statuses={})

    lines = status_mod.collect_live_checks(ui, knob, status_override="active_external")

    assert any("no matching AudioKnob ownership was proven" in line for line in lines)


def test_collect_live_checks_reports_group_membership_reset_note(monkeypatch) -> None:
    import grp
    import os
    import pwd

    def _fake_run(_cmd, capture_output=True, text=True):
        return SimpleNamespace(stdout="uid=1000(chris) gid=1000(chris)", stderr="")

    groups = {
        "audio": SimpleNamespace(gr_gid=100, gr_mem=["chris"]),
        "realtime": SimpleNamespace(gr_gid=200, gr_mem=["chris"]),
    }

    monkeypatch.setattr(status_mod.subprocess, "run", _fake_run)
    monkeypatch.setattr("audioknob_gui.platform.detect.get_missing_groups", lambda: [])
    monkeypatch.setattr(os, "getuid", lambda: 1000)
    monkeypatch.setattr(os, "getgid", lambda: 1000)
    monkeypatch.setattr(os, "getgroups", lambda: [100, 200])
    monkeypatch.setattr(pwd, "getpwuid", lambda _uid: SimpleNamespace(pw_name="chris"))
    monkeypatch.setattr(grp, "getgrnam", lambda name: groups[name])

    knob = SimpleNamespace(
        id="audio_group_membership",
        title="Audio Groups",
        impl=SimpleNamespace(kind="group_membership", params={"groups": ["audio", "realtime"]}),
    )

    ui = SimpleNamespace(state={}, _knob_statuses={})

    lines = status_mod.collect_live_checks(ui, knob, status_override="applied")

    assert any("Factory Reset does not revoke group membership automatically" in line for line in lines)

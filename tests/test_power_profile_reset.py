"""Tests for tuned/power-profiles-daemon reset safety."""

from __future__ import annotations

import subprocess


def test_systemd_enable_now_unmasks_masked_unit(monkeypatch):
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.worker.ops import systemd_enable_now

    calls: list[list[str]] = []

    def _fake_run(argv, *, check=False, timeout=None):
        calls.append(list(argv))
        if argv[:2] == ["systemctl", "is-enabled"]:
            return RunResult(argv=list(argv), returncode=0, stdout="masked\n", stderr="")
        if argv[:2] == ["systemctl", "is-active"]:
            return RunResult(argv=list(argv), returncode=0, stdout="inactive\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    effect = systemd_enable_now("power-profiles-daemon.service")

    assert effect["pre"] == {"enabled": "masked", "active": "inactive"}
    assert calls == [
        ["systemctl", "is-enabled", "power-profiles-daemon.service"],
        ["systemctl", "is-active", "power-profiles-daemon.service"],
        ["systemctl", "unmask", "power-profiles-daemon.service"],
        ["systemctl", "enable", "--now", "power-profiles-daemon.service"],
    ]


def test_systemd_restore_unmasks_before_restoring_disabled_state(monkeypatch):
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.worker.ops import systemd_restore

    calls: list[list[str]] = []

    def _fake_run(argv, *, check=False, timeout=None):
        calls.append(list(argv))
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    systemd_restore(
        {
            "kind": "systemd_unit_toggle",
            "unit": "power-profiles-daemon.service",
            "pre": {"enabled": "disabled", "active": "inactive"},
        }
    )

    assert calls == [
        ["systemctl", "unmask", "power-profiles-daemon.service"],
        ["systemctl", "disable", "power-profiles-daemon.service"],
        ["systemctl", "stop", "power-profiles-daemon.service"],
    ]


def test_restore_power_profile_effects_infers_ppd_for_old_tuned_transactions(monkeypatch):
    from audioknob_gui.worker.cli import _restore_power_profile_effects

    calls: list[list[str]] = []

    def _fake_run(argv, capture_output=False, text=False):
        calls.append(list(argv))
        return subprocess.CompletedProcess(args=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.platform.packages.which_command", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr("audioknob_gui.worker.cli.subprocess.run", _fake_run)

    effects = [
        {
            "kind": "systemd_unit_toggle",
            "unit": "power-profiles-daemon.service",
            "pre": {"enabled": "disabled", "active": "active"},
        },
        {
            "kind": "systemd_unit_toggle",
            "unit": "tuned.service",
            "pre": {"enabled": "disabled", "active": "inactive"},
        },
        {
            "kind": "power_profile",
            "backend": "tuned",
            "before": "balanced",
        },
    ]
    errors: list[str] = []

    restored = _restore_power_profile_effects(effects, errors)

    assert restored == 1
    assert errors == []
    assert calls == [["/usr/bin/powerprofilesctl", "set", "balanced"]]


def test_force_reset_power_profile_unmasks_ppd_before_enable(monkeypatch):
    from audioknob_gui.worker.cli import _force_reset_power_profile

    calls: list[list[str]] = []

    def _fake_run(argv, capture_output=False, text=False):
        calls.append(list(argv))
        return subprocess.CompletedProcess(args=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.select_power_profile_backend",
        lambda _params: {"backend": "tuned", "cmd": "/usr/sbin/tuned-adm"},
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.detect_power_profile_backend",
        lambda: {"backend": "powerprofilesctl", "cmd": "/usr/bin/powerprofilesctl"},
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.read_power_profile",
        lambda _backend, _cmd: "balanced",
    )
    monkeypatch.setattr("audioknob_gui.worker.cli.subprocess.run", _fake_run)

    success, message = _force_reset_power_profile({})

    assert success is True
    assert "restored ppd to balanced" in message
    assert calls[:4] == [
        ["systemctl", "disable", "--now", "tuned.service"],
        ["systemctl", "unmask", "power-profiles-daemon.service"],
        ["systemctl", "enable", "--now", "power-profiles-daemon.service"],
        ["/usr/bin/powerprofilesctl", "set", "balanced"],
    ]

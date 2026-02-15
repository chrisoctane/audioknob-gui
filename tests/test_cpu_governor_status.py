"""Tests for CPU governor status semantics under tuned."""

from __future__ import annotations


def _cpu_governor_knob():
    from audioknob_gui.registry import Capabilities, Impl, Knob

    return Knob(
        id="cpu_governor_performance_persistent",
        title="CPU Performance (persistent)",
        description="",
        category="cpu",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysfs_glob_kv",
            params={
                "glob": "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor",
                "value": "performance",
            },
        ),
    )


def test_cpu_governor_status_not_applied_when_tuned_active(monkeypatch):
    """If tuned is active and persistence is not configured, report not_applied (not partial)."""
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.worker.ops import check_knob_status

    knob = _cpu_governor_knob()

    monkeypatch.setattr(
        "audioknob_gui.worker.ops._expand_sysfs_globs",
        lambda _glob: ["/sys/cpu0/governor"],
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_cpupower_config_path",
        lambda _distro_id: "/etc/cpupower-service.conf",
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_cpu_governor_service",
        lambda _distro_id: "cpupower.service",
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops._systemd_is_active",
        lambda _unit: True,
    )

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"] and argv[-1] == "cpupower.service":
            return RunResult(argv=list(argv), returncode=0, stdout="disabled\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    def _fake_read_text(self, *args, **kwargs):
        path = str(self)
        if path == "/sys/cpu0/governor":
            return "[performance] powersave\n"
        if path == "/etc/cpupower-service.conf":
            return 'GOVERNOR="powersave"\n'
        raise FileNotFoundError(path)

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)
    monkeypatch.setattr("audioknob_gui.worker.ops.Path.read_text", _fake_read_text)

    assert check_knob_status(knob) == "not_applied"


def test_cpu_governor_status_not_applied_when_tuned_inactive(monkeypatch):
    """Without tuned, runtime match + missing persistence is still not_applied (runtime-only match is not evidence)."""
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.worker.ops import check_knob_status

    knob = _cpu_governor_knob()

    monkeypatch.setattr(
        "audioknob_gui.worker.ops._expand_sysfs_globs",
        lambda _glob: ["/sys/cpu0/governor"],
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_cpupower_config_path",
        lambda _distro_id: "/etc/cpupower-service.conf",
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_cpu_governor_service",
        lambda _distro_id: "cpupower.service",
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops._systemd_is_active",
        lambda _unit: False,
    )

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"] and argv[-1] == "cpupower.service":
            return RunResult(argv=list(argv), returncode=0, stdout="disabled\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    def _fake_read_text(self, *args, **kwargs):
        path = str(self)
        if path == "/sys/cpu0/governor":
            return "[performance] powersave\n"
        if path == "/etc/cpupower-service.conf":
            return 'GOVERNOR="powersave"\n'
        raise FileNotFoundError(path)

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)
    monkeypatch.setattr("audioknob_gui.worker.ops.Path.read_text", _fake_read_text)

    assert check_knob_status(knob) == "not_applied"


def test_cpu_governor_status_partial_when_configured_but_service_disabled(monkeypatch):
    """If the config is set but the service isn't enabled, the knob is partial."""
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.worker.ops import check_knob_status

    knob = _cpu_governor_knob()

    monkeypatch.setattr(
        "audioknob_gui.worker.ops._expand_sysfs_globs",
        lambda _glob: ["/sys/cpu0/governor"],
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_cpupower_config_path",
        lambda _distro_id: "/etc/cpupower-service.conf",
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_cpu_governor_service",
        lambda _distro_id: "cpupower.service",
    )

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"] and argv[-1] == "cpupower.service":
            return RunResult(argv=list(argv), returncode=0, stdout="disabled\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    def _fake_read_text(self, *args, **kwargs):
        path = str(self)
        if path == "/sys/cpu0/governor":
            return "[performance] powersave\n"
        if path == "/etc/cpupower-service.conf":
            return 'GOVERNOR="performance"\n'
        raise FileNotFoundError(path)

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)
    monkeypatch.setattr("audioknob_gui.worker.ops.Path.read_text", _fake_read_text)

    assert check_knob_status(knob) == "partial"


def test_cpu_governor_status_applied_when_configured_and_service_enabled(monkeypatch):
    """If config + service are set and runtime matches, the knob is applied."""
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.worker.ops import check_knob_status

    knob = _cpu_governor_knob()

    monkeypatch.setattr(
        "audioknob_gui.worker.ops._expand_sysfs_globs",
        lambda _glob: ["/sys/cpu0/governor"],
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_cpupower_config_path",
        lambda _distro_id: "/etc/cpupower-service.conf",
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_cpu_governor_service",
        lambda _distro_id: "cpupower.service",
    )

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"] and argv[-1] == "cpupower.service":
            return RunResult(argv=list(argv), returncode=0, stdout="enabled\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    def _fake_read_text(self, *args, **kwargs):
        path = str(self)
        if path == "/sys/cpu0/governor":
            return "[performance] powersave\n"
        if path == "/etc/cpupower-service.conf":
            return 'GOVERNOR="performance"\n'
        raise FileNotFoundError(path)

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)
    monkeypatch.setattr("audioknob_gui.worker.ops.Path.read_text", _fake_read_text)

    assert check_knob_status(knob) == "applied"

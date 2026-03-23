from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_scx_service_dropin_helpers() -> None:
    from audioknob_gui.core.scx import scx_service_dropin_content, scx_service_dropin_path

    assert scx_service_dropin_path() == "/etc/systemd/system/scx.service.d/99-audioknob-memlock.conf"
    assert scx_service_dropin_content() == "[Service]\nLimitMEMLOCK=infinity\n"


def test_scx_managed_knob_ids_for_lavd_default_mode() -> None:
    from audioknob_gui.core.scx import scx_managed_knob_ids

    assert scx_managed_knob_ids("scx_lavd", "") == (
        "cpu_governor_performance_persistent",
        "power_profile_performance",
    )


def test_scx_managed_knob_ids_for_lavd_autopower_without_freq_scaling() -> None:
    from audioknob_gui.core.scx import scx_managed_knob_ids

    assert scx_managed_knob_ids("scx_lavd", "--autopower --no-freq-scaling") == ()


def test_scx_managed_knob_ids_for_bpfland_cpufreq_only_locks_governor() -> None:
    from audioknob_gui.core.scx import scx_managed_knob_ids

    assert scx_managed_knob_ids("scx_bpfland", "--cpufreq") == (
        "cpu_governor_performance_persistent",
    )


def test_update_scx_scheduler_config_clears_flags_when_scheduler_changes() -> None:
    from audioknob_gui.core.scx import scx_flags_reset_required, update_scx_scheduler_config

    before = (
        "# List of scx schedulers\n"
        "SCX_SCHEDULER=scx_lavd\n"
        "\n"
        "SCX_FLAGS='--performance'\n"
    )

    assert scx_flags_reset_required(before, "scx_bpfland") is True
    after = update_scx_scheduler_config(before, "scx_bpfland")

    assert "SCX_SCHEDULER=scx_bpfland\n" in after
    assert "SCX_FLAGS=\n" in after
    assert "scx_lavd" not in after


def test_update_scx_scheduler_config_preserves_flags_when_scheduler_stays_same() -> None:
    from audioknob_gui.core.scx import scx_flags_reset_required, update_scx_scheduler_config

    before = (
        "# List of scx schedulers\n"
        "SCX_SCHEDULER=scx_bpfland\n"
        "\n"
        "SCX_FLAGS='-s 700 -S'\n"
    )

    assert scx_flags_reset_required(before, "scx_bpfland") is False
    after = update_scx_scheduler_config(before, "scx_bpfland")

    assert "SCX_SCHEDULER=scx_bpfland\n" in after
    assert "SCX_FLAGS='-s 700 -S'\n" in after


def test_update_scx_scheduler_config_writes_explicit_flags() -> None:
    from audioknob_gui.core.scx import update_scx_scheduler_config

    before = "SCX_SCHEDULER=scx_bpfland\nSCX_FLAGS=\n"

    after = update_scx_scheduler_config(before, "scx_lavd", "--performance")

    assert "SCX_SCHEDULER=scx_lavd\n" in after
    assert "SCX_FLAGS=--performance\n" in after


def test_list_available_scx_schedulers_filters_helper_binaries(monkeypatch, tmp_path: Path) -> None:
    from audioknob_gui.core.scx import list_available_scx_schedulers

    for name in ("scx_bpfland", "scx_flash", "scx_loader", "scx_show_state"):
        path = tmp_path / name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)

    monkeypatch.setattr("audioknob_gui.core.scx._search_directories", lambda: [tmp_path])

    assert list_available_scx_schedulers() == ["scx_bpfland", "scx_flash"]


def test_list_available_scx_flag_presets_parses_boolean_help_options(monkeypatch) -> None:
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.core.scx import _scheduler_flag_options, list_available_scx_flag_presets

    def _fake_run(argv, *, check=False, timeout=None):
        assert argv == ["scx_lavd", "--help"]
        return RunResult(
            argv=list(argv),
            returncode=0,
            stdout=(
                "Usage: scx_lavd [OPTIONS]\n\n"
                "Options:\n"
                "      --autopilot\n"
                "          Automatically decide the scheduler's power mode.\n"
                "      --performance\n"
                "          Run the scheduler in performance mode.\n"
                "      --slice-max-us <SLICE_MAX_US>\n"
                "          Maximum scheduling slice duration.\n"
                "  -v, --verbose...\n"
                "          Verbose logging.\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("audioknob_gui.core.scx.run", _fake_run)
    _scheduler_flag_options.cache_clear()
    options = list_available_scx_flag_presets("scx_lavd")

    assert [item.value for item in options] == ["--autopilot", "--performance", "--verbose"]


def test_scx_apply_param_overrides_uses_configured_scheduler_when_state_is_empty(monkeypatch) -> None:
    from audioknob_gui.gui.knobs import scx

    cfg_path = Path("/tmp/scx-config-for-test")
    ui = SimpleNamespace(
        state={
            "scx_scheduler": None,
            "scx_flags": None,
            "scx_enable_at_boot": None,
            "system_profile": {"paths": {"scx_config": str(cfg_path)}},
        },
        _scx_scheduler_from_state=lambda: None,
        _scx_enable_at_boot_from_state=lambda: None,
    )

    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_scheduler_config", lambda _path: "scx_lavd")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_flags_config", lambda _path: "--performance")

    params: dict[str, str] = {}
    scx.apply_param_overrides(ui, params)

    assert params["scheduler"] == "scx_lavd"
    assert params["flags"] == "--performance"


def test_scx_save_selection_updates_state(monkeypatch) -> None:
    from audioknob_gui.gui.knobs import scx

    saved: list[object] = []
    ui = SimpleNamespace(
        state={"scx_scheduler": None, "scx_flags": None, "scx_enable_at_boot": None},
        _knob_statuses={},
        _refresh_statuses=lambda: saved.append("refresh"),
        _populate=lambda: saved.append("populate"),
    )

    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.save_state", lambda state: saved.append(dict(state)))

    scheduler = scx.save_selection(ui, "scx_lavd", "--performance", True)

    assert scheduler == "scx_lavd"
    assert ui.state["scx_scheduler"] == "scx_lavd"
    assert ui.state["scx_flags"] == "--performance"
    assert ui.state["scx_enable_at_boot"] is True
    assert ui._knob_statuses["scx_scheduler"] == "not_applied"
    assert "refresh" in saved
    assert "populate" in saved


def test_scx_registry_configure_handler_uses_dialog(monkeypatch) -> None:
    from audioknob_gui.gui.knobs.registry import handle_configure_knob

    called: list[object] = []
    ui = SimpleNamespace()

    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.configure_dialog", lambda passed_ui: called.append(passed_ui))

    assert handle_configure_knob(ui, "scx_scheduler") is True
    assert called == [ui]


def test_scx_force_reset_supported_in_gui() -> None:
    from audioknob_gui.gui.main_window import MainWindow

    class _DummyUi:
        _force_reset_supported = MainWindow._force_reset_supported

        def __init__(self) -> None:
            self.registry = [
                SimpleNamespace(
                    id="scx_scheduler",
                    impl=SimpleNamespace(kind="scx_scheduler"),
                )
            ]

    ui = _DummyUi()

    assert ui._force_reset_supported("scx_scheduler") is True


def test_scx_managed_lock_reason_in_gui() -> None:
    from audioknob_gui.gui.main_window import MainWindow

    class _DummyUi:
        _scx_managed_lock_reason = MainWindow._scx_managed_lock_reason

        @staticmethod
        def _scx_managed_ids() -> list[str]:
            return ["cpu_governor_performance_persistent"]

    ui = _DummyUi()

    assert (
        ui._scx_managed_lock_reason("cpu_governor_performance_persistent")
        == "Managed by sched_ext. Stop sched_ext Scheduler to unlock."
    )
    assert ui._scx_managed_lock_reason("scx_scheduler") == ""


def test_scx_managed_ids_follow_live_config_not_pending_state(monkeypatch) -> None:
    from audioknob_gui.gui.main_window import MainWindow

    class _DummyUi:
        _scx_managed_ids = MainWindow._scx_managed_ids

        def __init__(self) -> None:
            self.state = {
                "scx_scheduler": "scx_bpfland",
                "scx_flags": "--cpufreq",
            }

    ui = _DummyUi()

    monkeypatch.setattr("audioknob_gui.core.scx.read_sched_ext_status", lambda: ("enabled", "lavd"))
    monkeypatch.setattr("audioknob_gui.worker.ops.read_os_release", lambda: {"ID": "opensuse"})
    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: "/etc/default/scx")
    monkeypatch.setattr("audioknob_gui.core.scx.read_scx_scheduler_config", lambda _path: "scx_lavd")
    monkeypatch.setattr("audioknob_gui.core.scx.read_scx_flags_config", lambda _path: "--no-freq-scaling")

    assert ui._scx_managed_ids() == ["power_profile_performance"]


def test_scx_runtime_action_returns_start_for_configured_stopped_state(monkeypatch) -> None:
    from audioknob_gui.gui.knobs import scx

    ui = SimpleNamespace(
        state={
            "scx_scheduler": "scx_lavd",
            "scx_flags": "--performance",
            "scx_enable_at_boot": True,
            "system_profile": None,
        },
        _scx_scheduler_from_state=lambda: "scx_lavd",
        _scx_enable_at_boot_from_state=lambda: True,
    )

    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_scheduler_config", lambda _path: "scx_lavd")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_flags_config", lambda _path: "--performance")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_enabled_state", lambda _unit: "enabled")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_active_state", lambda _unit: "inactive")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_dropin_matches", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_sched_ext_status", lambda: ("disabled", None))

    assert scx.runtime_action(ui, "configured") == ("Start", "start")


def test_scx_runtime_action_returns_apply_for_config_drift(monkeypatch) -> None:
    from audioknob_gui.gui.knobs import scx

    ui = SimpleNamespace(
        state={
            "scx_scheduler": "scx_flash",
            "scx_flags": "--slice-lag-scaling",
            "scx_enable_at_boot": False,
            "system_profile": None,
        },
        _scx_scheduler_from_state=lambda: "scx_flash",
        _scx_enable_at_boot_from_state=lambda: False,
    )

    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_scheduler_config", lambda _path: "scx_lavd")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_flags_config", lambda _path: "")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_enabled_state", lambda _unit: "enabled")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_active_state", lambda _unit: "inactive")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_dropin_matches", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_sched_ext_status", lambda: ("disabled", None))

    assert scx.runtime_action(ui, "not_applied") == ("Apply Config", "apply")


def test_scx_runtime_action_returns_stop_for_applied_state(monkeypatch) -> None:
    from audioknob_gui.gui.knobs import scx

    ui = SimpleNamespace(
        state={
            "scx_scheduler": "scx_bpfland",
            "scx_flags": "",
            "scx_enable_at_boot": False,
            "system_profile": None,
        },
        _scx_scheduler_from_state=lambda: "scx_bpfland",
        _scx_enable_at_boot_from_state=lambda: False,
    )

    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_scheduler_config", lambda _path: "scx_bpfland")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_flags_config", lambda _path: "")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_enabled_state", lambda _unit: "disabled")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_active_state", lambda _unit: "active")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_dropin_matches", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_sched_ext_status", lambda: ("enabled", "bpfland"))

    assert scx.runtime_action(ui, "applied") == ("Stop", "stop")


def test_scx_runtime_action_returns_apply_when_dropin_is_missing(monkeypatch) -> None:
    from audioknob_gui.gui.knobs import scx

    ui = SimpleNamespace(
        state={
            "scx_scheduler": "scx_bpfland",
            "scx_flags": "",
            "scx_enable_at_boot": True,
            "system_profile": None,
        },
        _scx_scheduler_from_state=lambda: "scx_bpfland",
        _scx_enable_at_boot_from_state=lambda: True,
    )

    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_scheduler_config", lambda _path: "scx_bpfland")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_scx_flags_config", lambda _path: "")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_enabled_state", lambda _unit: "enabled")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_active_state", lambda _unit: "inactive")
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx._service_dropin_matches", lambda _unit: False)
    monkeypatch.setattr("audioknob_gui.gui.knobs.scx.read_sched_ext_status", lambda: ("disabled", None))

    assert scx.runtime_action(ui, "not_applied") == ("Apply Config", "apply")


def test_scx_collect_live_checks_reports_disabled_sched_ext_reason(monkeypatch) -> None:
    from audioknob_gui.gui.status import collect_live_checks
    from audioknob_gui.registry import Capabilities, Impl, Knob

    ui = SimpleNamespace(
        _knob_statuses={"scx_scheduler": "partial"},
        state={},
        registry=[],
    )
    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="scx_scheduler",
            params={"scheduler": "scx_lavd", "flags": "--performance", "unit": "scx.service"},
        ),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.read_os_release", lambda: {"ID": "opensuse-tumbleweed"})
    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: "/etc/default/scx")
    monkeypatch.setattr("audioknob_gui.core.scx.read_scx_scheduler_config", lambda _path: "scx_lavd")
    monkeypatch.setattr("audioknob_gui.core.scx.read_scx_flags_config", lambda _path: "--performance")
    monkeypatch.setattr("audioknob_gui.core.scx.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": True)
    monkeypatch.setattr("audioknob_gui.core.scx.read_sched_ext_status", lambda: ("disabled", None))

    def _fake_run(cmd, capture_output=False, text=False):
        if cmd[:2] == ["systemctl", "is-enabled"]:
            return SimpleNamespace(stdout="enabled\n", stderr="")
        if cmd[:2] == ["systemctl", "is-active"]:
            return SimpleNamespace(stdout="active\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("subprocess.run", _fake_run)

    lines = collect_live_checks(ui, knob, status_override="partial")

    assert "partial_reason: scx.service is enabled or running, but sched_ext is currently disabled." in lines
    assert "partial_reason: live sched_ext ops do not match the selected scheduler." not in lines


def test_scx_collect_live_checks_reports_configured_note(monkeypatch) -> None:
    from audioknob_gui.gui.status import collect_live_checks
    from audioknob_gui.registry import Capabilities, Impl, Knob

    ui = SimpleNamespace(
        _knob_statuses={"scx_scheduler": "configured"},
        state={},
        registry=[],
    )
    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="scx_scheduler",
            params={"scheduler": "scx_lavd", "flags": "--performance", "enable_at_boot": True, "unit": "scx.service"},
        ),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.read_os_release", lambda: {"ID": "opensuse-tumbleweed"})
    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: "/etc/default/scx")
    monkeypatch.setattr("audioknob_gui.core.scx.read_scx_scheduler_config", lambda _path: "scx_lavd")
    monkeypatch.setattr("audioknob_gui.core.scx.read_scx_flags_config", lambda _path: "--performance")
    monkeypatch.setattr("audioknob_gui.core.scx.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": True)
    monkeypatch.setattr("audioknob_gui.core.scx.read_sched_ext_status", lambda: ("disabled", None))

    def _fake_run(cmd, capture_output=False, text=False):
        if cmd[:2] == ["systemctl", "is-enabled"]:
            return SimpleNamespace(stdout="enabled\n", stderr="")
        if cmd[:2] == ["systemctl", "is-active"]:
            return SimpleNamespace(stdout="inactive\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("subprocess.run", _fake_run)

    lines = collect_live_checks(ui, knob, status_override="configured")

    assert "note: configuration matches the selected scheduler, but scx.service is currently stopped." in lines


def test_verify_scx_runtime_reports_failed_service(monkeypatch) -> None:
    from audioknob_gui.worker.cli import _verify_scx_runtime

    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.read_sched_ext_status", lambda: ("disabled", None))

    def _fake_run(cmd, capture_output=False, text=False, check=False):
        if cmd[:3] == ["systemctl", "is-active", "scx.service"]:
            return SimpleNamespace(stdout="failed\n", stderr="")
        if cmd[:3] == ["systemctl", "is-enabled", "scx.service"]:
            return SimpleNamespace(stdout="enabled\n", stderr="")
        if cmd[:3] == ["systemctl", "show", "scx.service"]:
            return SimpleNamespace(
                stdout="Result=exit-code\nActiveState=failed\nSubState=failed\nExecMainStatus=1\n",
                stderr="",
            )
        if cmd[:3] == ["journalctl", "-u", "scx.service"]:
            return SimpleNamespace(stdout="Error: Failed to load BPF program\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("audioknob_gui.worker.cli.subprocess.run", _fake_run)

    detail = _verify_scx_runtime("scx.service", "scx_lavd", timeout_sec=0.0)

    assert detail is not None
    assert "service_active=failed" in detail
    assert "sched_ext_state=disabled" in detail
    assert "Error: Failed to load BPF program" in detail


def test_scx_scheduler_preview_includes_memlock_dropin(monkeypatch, tmp_path: Path) -> None:
    from audioknob_gui.worker.ops import _scx_scheduler_preview

    cfg_path = tmp_path / "scx"
    cfg_path.write_text("SCX_SCHEDULER=scx_lavd\nSCX_FLAGS=--performance\n", encoding="utf-8")
    dropin_path = tmp_path / "scx.service.d" / "99-audioknob-memlock.conf"

    monkeypatch.setattr("audioknob_gui.worker.ops.read_os_release", lambda: {"ID": "opensuse-tumbleweed"})
    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: str(cfg_path))
    monkeypatch.setattr("audioknob_gui.worker.ops.scx_service_dropin_path", lambda _unit="scx.service": str(dropin_path))

    changes, cmds, notes = _scx_scheduler_preview({"scheduler": "scx_bpfland", "flags": "", "unit": "scx.service"})

    change_paths = {item.path for item in changes}
    assert str(cfg_path) in change_paths
    assert str(dropin_path) in change_paths
    assert ["systemctl", "daemon-reload"] in cmds
    assert any("LimitMEMLOCK=infinity" in note for note in notes)


def test_cmd_apply_scx_scheduler_writes_memlock_dropin(monkeypatch, tmp_path: Path, capsys) -> None:
    import argparse
    import subprocess

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    cfg_path = tmp_path / "scx"
    cfg_path.write_text("SCX_SCHEDULER=scx_lavd\nSCX_FLAGS=--performance\n", encoding="utf-8")
    dropin_path = tmp_path / "scx.service.d" / "99-audioknob-memlock.conf"

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="scx_scheduler", params={"scheduler": "", "unit": "scx.service"}),
    )

    monkeypatch.setattr(cli, "_require_root", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(
        cli,
        "default_paths",
        lambda: SimpleNamespace(var_lib_dir=str(tmp_path / "var"), user_state_dir=str(tmp_path / "user")),
    )
    monkeypatch.setattr(
        cli,
        "_load_gui_state",
        lambda: {"scx_scheduler": "scx_bpfland", "scx_flags": "", "scx_enable_at_boot": None},
    )
    monkeypatch.setattr(cli, "_log_audit_event", lambda *_a, **_kw: None)
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.read_os_release", lambda: {"ID": "opensuse-tumbleweed"})
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.resolve_scx_config_path", lambda _distro_id: str(cfg_path))
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.scx_service_dropin_path",
        lambda _unit="scx.service": str(dropin_path),
    )
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.read_sched_ext_status", lambda: ("disabled", None))

    def _fake_subprocess_run(cmd, check=False, capture_output=False, text=False):
        if cmd == ["systemctl", "daemon-reload"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:3] == ["systemctl", "is-active", "scx.service"]:
            return subprocess.CompletedProcess(cmd, 3, "", "inactive\n")
        raise AssertionError(f"unexpected subprocess command: {cmd}")

    monkeypatch.setattr(cli.subprocess, "run", _fake_subprocess_run)

    rc = cli.cmd_apply(argparse.Namespace(registry="unused", knob=["scx_scheduler"]))

    assert rc == 0
    assert "SCX_SCHEDULER=scx_bpfland\n" in cfg_path.read_text(encoding="utf-8")
    assert dropin_path.read_text(encoding="utf-8") == "[Service]\nLimitMEMLOCK=infinity\n"
    payload = capsys.readouterr().out
    assert '"applied": [' in payload


def test_cmd_scx_runtime_start_uses_configured_scheduler(monkeypatch, capsys) -> None:
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.cli import cmd_scx_runtime

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="scx_scheduler", params={"unit": "scx.service"}),
    )

    monkeypatch.setattr("audioknob_gui.worker.cli._require_root", lambda: None)
    monkeypatch.setattr("audioknob_gui.worker.cli.load_registry", lambda _path: [knob])
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.read_os_release", lambda: {"ID": "opensuse-tumbleweed"})
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.resolve_scx_config_path", lambda _distro_id: "/etc/default/scx")
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.read_scx_scheduler_config", lambda _path: "scx_lavd")
    monkeypatch.setattr("audioknob_gui.worker.cli._ensure_scx_unit_unmasked", lambda _unit: None)
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.systemd_start",
        lambda _unit: {"result": {"returncode": 0, "stdout": "", "stderr": ""}},
    )
    monkeypatch.setattr("audioknob_gui.worker.cli._verify_scx_runtime", lambda _unit, _scheduler: None)
    monkeypatch.setattr("audioknob_gui.worker.cli._log_audit_event", lambda *_args, **_kwargs: None)

    rc = cmd_scx_runtime(SimpleNamespace(action="start", registry="/tmp/registry.json"))

    assert rc == 0
    payload = capsys.readouterr().out
    assert '"success": true' in payload
    assert '"scheduler": "scx_lavd"' in payload


def test_cmd_scx_runtime_stop_reports_success(monkeypatch, capsys) -> None:
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.cli import cmd_scx_runtime

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="scx_scheduler", params={"unit": "scx.service"}),
    )

    monkeypatch.setattr("audioknob_gui.worker.cli._require_root", lambda: None)
    monkeypatch.setattr("audioknob_gui.worker.cli.load_registry", lambda _path: [knob])
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.read_os_release", lambda: {"ID": "opensuse-tumbleweed"})
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.resolve_scx_config_path", lambda _distro_id: "/etc/default/scx")
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.read_scx_scheduler_config", lambda _path: "scx_bpfland")
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.systemd_stop",
        lambda _unit: {"result": {"returncode": 0, "stdout": "", "stderr": ""}},
    )
    monkeypatch.setattr("audioknob_gui.worker.cli._verify_scx_stopped", lambda _unit: None)
    monkeypatch.setattr("audioknob_gui.worker.cli._log_audit_event", lambda *_args, **_kwargs: None)

    rc = cmd_scx_runtime(SimpleNamespace(action="stop", registry="/tmp/registry.json"))

    assert rc == 0
    payload = capsys.readouterr().out
    assert '"success": true' in payload
    assert '"action": "stop"' in payload


def test_scx_collect_live_checks_reports_failed_service_reason(monkeypatch) -> None:
    from audioknob_gui.gui.status import collect_live_checks
    from audioknob_gui.registry import Capabilities, Impl, Knob

    ui = SimpleNamespace(
        _knob_statuses={"scx_scheduler": "partial"},
        state={},
        registry=[],
    )
    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="scx_scheduler",
            params={"scheduler": "scx_lavd", "flags": "--performance", "unit": "scx.service"},
        ),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.read_os_release", lambda: {"ID": "opensuse-tumbleweed"})
    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: "/etc/default/scx")
    monkeypatch.setattr("audioknob_gui.core.scx.read_scx_scheduler_config", lambda _path: "scx_lavd")
    monkeypatch.setattr("audioknob_gui.core.scx.read_scx_flags_config", lambda _path: "--performance")
    monkeypatch.setattr("audioknob_gui.core.scx.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": True)
    monkeypatch.setattr("audioknob_gui.core.scx.read_sched_ext_status", lambda: ("disabled", None))

    def _fake_run(cmd, capture_output=False, text=False):
        if cmd[:2] == ["systemctl", "is-enabled"]:
            return SimpleNamespace(stdout="enabled\n", stderr="")
        if cmd[:2] == ["systemctl", "is-active"]:
            return SimpleNamespace(stdout="failed\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("subprocess.run", _fake_run)

    lines = collect_live_checks(ui, knob, status_override="partial")

    assert "partial_reason: scx.service failed to start, so sched_ext is currently disabled." in lines


def test_scx_status_applied(monkeypatch, tmp_path: Path) -> None:
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    cfg_path = tmp_path / "scx"
    cfg_path.write_text("SCX_SCHEDULER=scx_bpfland\nSCX_FLAGS='-s 700 -S'\n", encoding="utf-8")

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="scx_scheduler", params={"scheduler": "scx_bpfland", "unit": "scx.service"}),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: str(cfg_path))
    monkeypatch.setattr("audioknob_gui.worker.ops.read_sched_ext_status", lambda: ("enabled", "bpfland"))
    monkeypatch.setattr("audioknob_gui.worker.ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.ops.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": True)

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"]:
            return RunResult(argv=list(argv), returncode=0, stdout="enabled\n", stderr="")
        if argv[:2] == ["systemctl", "is-active"]:
            return RunResult(argv=list(argv), returncode=0, stdout="active\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    assert check_knob_status(knob) == "applied"


def test_scx_status_configured_when_runtime_is_stopped(monkeypatch, tmp_path: Path) -> None:
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    cfg_path = tmp_path / "scx"
    cfg_path.write_text("SCX_SCHEDULER=scx_lavd\nSCX_FLAGS=--performance\n", encoding="utf-8")

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="scx_scheduler",
            params={
                "scheduler": "scx_lavd",
                "flags": "--performance",
                "enable_at_boot": True,
                "unit": "scx.service",
            },
        ),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: str(cfg_path))
    monkeypatch.setattr("audioknob_gui.worker.ops.read_sched_ext_status", lambda: ("disabled", None))
    monkeypatch.setattr("audioknob_gui.worker.ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.ops.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": True)

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"]:
            return RunResult(argv=list(argv), returncode=0, stdout="enabled\n", stderr="")
        if argv[:2] == ["systemctl", "is-active"]:
            return RunResult(argv=list(argv), returncode=3, stdout="inactive\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    assert check_knob_status(knob) == "configured"


def test_scx_status_partial_when_selected_flags_do_not_match(monkeypatch, tmp_path: Path) -> None:
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    cfg_path = tmp_path / "scx"
    cfg_path.write_text("SCX_SCHEDULER=scx_lavd\nSCX_FLAGS=--autopilot\n", encoding="utf-8")

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="scx_scheduler",
            params={"scheduler": "scx_lavd", "flags": "--performance", "unit": "scx.service"},
        ),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: str(cfg_path))
    monkeypatch.setattr("audioknob_gui.worker.ops.read_sched_ext_status", lambda: ("enabled", "lavd"))
    monkeypatch.setattr("audioknob_gui.worker.ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.ops.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": True)

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"]:
            return RunResult(argv=list(argv), returncode=0, stdout="enabled\n", stderr="")
        if argv[:2] == ["systemctl", "is-active"]:
            return RunResult(argv=list(argv), returncode=0, stdout="active\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    assert check_knob_status(knob) == "partial"


def test_scx_status_not_applied_for_dormant_config_only(monkeypatch, tmp_path: Path) -> None:
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    cfg_path = tmp_path / "scx"
    cfg_path.write_text("SCX_SCHEDULER=scx_lavd\nSCX_FLAGS=\n", encoding="utf-8")

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="scx_scheduler",
            params={"scheduler": "scx_flash", "flags": "--slice-lag-scaling", "unit": "scx.service"},
        ),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: str(cfg_path))
    monkeypatch.setattr("audioknob_gui.worker.ops.read_sched_ext_status", lambda: ("disabled", None))
    monkeypatch.setattr("audioknob_gui.worker.ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.ops.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": False)

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"]:
            return RunResult(argv=list(argv), returncode=1, stdout="disabled\n", stderr="")
        if argv[:2] == ["systemctl", "is-active"]:
            return RunResult(argv=list(argv), returncode=3, stdout="failed\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    assert check_knob_status(knob) == "not_applied"


def test_scx_status_active_external_without_selection(monkeypatch, tmp_path: Path) -> None:
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    cfg_path = tmp_path / "scx"
    cfg_path.write_text("SCX_SCHEDULER=scx_bpfland\n", encoding="utf-8")

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="scx_scheduler", params={"scheduler": "", "unit": "scx.service"}),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: str(cfg_path))
    monkeypatch.setattr("audioknob_gui.worker.ops.read_sched_ext_status", lambda: ("enabled", "bpfland"))
    monkeypatch.setattr("audioknob_gui.worker.ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.ops.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": True)

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"]:
            return RunResult(argv=list(argv), returncode=0, stdout="enabled\n", stderr="")
        if argv[:2] == ["systemctl", "is-active"]:
            return RunResult(argv=list(argv), returncode=0, stdout="active\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    assert check_knob_status(knob) == "active_external"


def test_scx_status_not_applied_when_memlock_dropin_is_missing(monkeypatch, tmp_path: Path) -> None:
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    cfg_path = tmp_path / "scx"
    cfg_path.write_text("SCX_SCHEDULER=scx_bpfland\nSCX_FLAGS=\n", encoding="utf-8")

    knob = Knob(
        id="scx_scheduler",
        title="sched_ext Scheduler",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="scx_scheduler",
            params={"scheduler": "scx_bpfland", "flags": "", "enable_at_boot": True, "unit": "scx.service"},
        ),
    )

    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_scx_config_path", lambda _distro_id: str(cfg_path))
    monkeypatch.setattr("audioknob_gui.worker.ops.read_sched_ext_status", lambda: ("disabled", None))
    monkeypatch.setattr("audioknob_gui.worker.ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.ops.scx_service_dropin_matches", lambda _unit="scx.service", _base="/etc/systemd/system": False)

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"]:
            return RunResult(argv=list(argv), returncode=0, stdout="enabled\n", stderr="")
        if argv[:2] == ["systemctl", "is-active"]:
            return RunResult(argv=list(argv), returncode=3, stdout="inactive\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    assert check_knob_status(knob) == "not_applied"


def test_force_reset_scx_scheduler_reports_external_scheduler(monkeypatch) -> None:
    from audioknob_gui.worker.cli import _force_reset_scx_scheduler

    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops._systemd_unit_exists", lambda _unit: True)
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.systemd_disable_now", lambda _unit: {"unit": _unit})
    monkeypatch.setattr("audioknob_gui.worker.cli.worker_ops.read_sched_ext_status", lambda: ("enabled", "bpfland"))

    def _fake_run(argv, capture_output=False, text=False):
        if argv[:2] == ["systemctl", "is-enabled"]:
            return type("Result", (), {"stdout": "disabled\n", "stderr": ""})()
        if argv[:2] == ["systemctl", "is-active"]:
            return type("Result", (), {"stdout": "inactive\n", "stderr": ""})()
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr("audioknob_gui.worker.cli.subprocess.run", _fake_run)

    success, message = _force_reset_scx_scheduler({"unit": "scx.service"})

    assert success is False
    assert "still enabled externally" in message

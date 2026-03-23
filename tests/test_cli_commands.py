"""Tests for worker CLI commands: list-pending, reset-defaults."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_list_pending_output_shape():
    """Test that list-pending returns expected JSON structure."""
    from audioknob_gui.worker.cli import main
    import io
    import sys
    
    # Capture stdout
    captured = io.StringIO()
    with patch.object(sys, 'stdout', captured):
        result = main(["list-pending"])
    
    assert result == 0
    output = json.loads(captured.getvalue())
    
    # Check required fields
    assert "schema" in output
    assert output["schema"] == 1
    assert "files" in output
    assert "count" in output
    assert "effects" in output
    assert "effects_count" in output
    assert "has_root_files" in output
    assert "has_user_files" in output
    assert "has_root_effects" in output
    assert "has_user_effects" in output
    
    # Types
    assert isinstance(output["files"], list)
    assert isinstance(output["effects"], list)
    assert isinstance(output["count"], int)
    assert isinstance(output["effects_count"], int)


def test_reset_defaults_scope_user_output_shape():
    """Test that reset-defaults --scope user returns expected JSON structure."""
    from audioknob_gui.worker.cli import main
    import io
    import sys
    
    captured = io.StringIO()
    with patch.object(sys, 'stdout', captured):
        result = main(["reset-defaults", "--scope", "user"])
    
    # Should succeed (even if nothing to reset)
    assert result == 0
    output = json.loads(captured.getvalue())
    
    # Check required fields
    assert "schema" in output
    assert output["schema"] == 1
    assert "reset_count" in output
    assert "results" in output
    assert "errors" in output
    assert "scope" in output
    assert output["scope"] == "user"
    assert "needs_root_reset" in output


def test_reset_file_to_default_package_strategy_prefers_backup():
    """reset_file_to_default must restore file content from our backup even when reset_strategy=package.

    Older transactions recorded package-owned files with reset_strategy=package,
    but package-manager restore mechanisms can be metadata-only (e.g. rpm --restore).
    """
    from audioknob_gui.core.transaction import RESET_PACKAGE, backup_file, new_tx, reset_file_to_default

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        test_file = root / "cpupower-service.conf"
        test_file.write_text("GOVERNOR=powersave\n", encoding="utf-8")

        tx = new_tx(tmpdir)
        meta = backup_file(tx, str(test_file))

        # Mutate file.
        test_file.write_text("GOVERNOR=performance\n", encoding="utf-8")

        meta = dict(meta)
        meta["reset_strategy"] = RESET_PACKAGE
        meta["package"] = "fakepkg"

        ok, msg = reset_file_to_default(meta, tx)
        assert ok is True
        assert "backup" in msg.lower()
        assert test_file.read_text(encoding="utf-8") == "GOVERNOR=powersave\n"


def test_rtirq_status_partial_when_service_enabled_without_config(monkeypatch, tmp_path):
    """rtirq_enable should report partial when the service is enabled/failed but config is absent."""
    from audioknob_gui.core.runner import RunResult
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    knob = Knob(
        id="rtirq_enable",
        title="RT IRQ",
        description="",
        category="irq",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="rtirq_config",
            params={
                "name_list": ["snd", "usb"],
                "high_list": ["snd", "usb"],
                "prio_high": 90,
                "prio_decr": 5,
                "unit": "rtirq.service",
            },
        ),
    )

    # Ensure the config path doesn't exist, so cfg_ok stays false.
    cfg_path = str(tmp_path / "rtirq.conf")
    monkeypatch.setattr("audioknob_gui.worker.ops.resolve_rtirq_config_path", lambda _distro_id: cfg_path)

    def _fake_run(argv, *, check=False, timeout=None):
        if argv[:2] == ["systemctl", "is-enabled"] and argv[-1] == "rtirq.service":
            return RunResult(argv=list(argv), returncode=0, stdout="enabled\n", stderr="")
        if argv[:2] == ["systemctl", "is-active"] and argv[-1] == "rtirq.service":
            return RunResult(argv=list(argv), returncode=0, stdout="failed\n", stderr="")
        return RunResult(argv=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audioknob_gui.worker.ops.run", _fake_run)

    assert check_knob_status(knob) == "partial"


def test_restore_rtirq_auto_disables_when_unit_was_missing(monkeypatch, tmp_path):
    """restore-knob should auto-disable rtirq when the unit was not present in the original state."""
    import subprocess

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="rtirq_enable",
        title="RT IRQ",
        description="",
        category="irq",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="rtirq_config", params={"unit": "rtirq.service"}),
    )

    manifest = {
        "schema": 1,
        "txid": "tx1",
        "applied": ["rtirq_enable"],
        "backups": [],
        "effects": [
            {
                "kind": "systemd_unit_toggle",
                "unit": "rtirq.service",
                "pre": {"enabled": "not-found", "active": "inactive"},
                "result": {"returncode": 1, "stdout": "", "stderr": "Unit rtirq.service does not exist"},
            },
        ],
    }

    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(cli, "_find_transaction_for_knob", lambda _kid: ("tx1", manifest, "user"))
    monkeypatch.setattr(cli, "_knob_restore_targets", lambda _k: ([], ["rtirq.service"], []))
    monkeypatch.setattr(cli, "_filter_manifest_backups_for_knob", lambda *_a, **_kw: [])

    def _effects_filter(effects, **_kw):
        return list(effects)

    monkeypatch.setattr(cli, "_filter_manifest_effects_for_knob", _effects_filter)
    monkeypatch.setattr(cli.worker_ops, "systemd_restore", lambda _e: None)
    monkeypatch.setattr("audioknob_gui.worker.ops.read_os_release", lambda: {"ID": "test"})
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_rtirq_config_path",
        lambda _distro_id: str(tmp_path / "rtirq.conf"),
    )

    state = {"enabled": "enabled"}

    def _fake_run(argv, *args, **kwargs):
        if argv[:2] == ["systemctl", "is-enabled"] and argv[-1] == "rtirq.service":
            return subprocess.CompletedProcess(
                args=list(argv),
                returncode=0,
                stdout=f"{state['enabled']}\n",
                stderr="",
            )
        if argv[:3] == ["systemctl", "disable", "--now"] and argv[-1] == "rtirq.service":
            state["enabled"] = "disabled"
            return subprocess.CompletedProcess(args=list(argv), returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    result = cli._restore_knob_once("rtirq_enable")
    assert result.get("success") is True
    restored = [str(x) for x in result.get("restored", [])]
    assert any("auto-disabled rtirq.service" in line for line in restored)


def test_restore_rtirq_suggests_force_reset_when_auto_disable_fails(monkeypatch, tmp_path):
    """restore-knob should offer force reset if rtirq remains enabled after auto-disable."""
    import subprocess

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="rtirq_enable",
        title="RT IRQ",
        description="",
        category="irq",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="rtirq_config", params={"unit": "rtirq.service"}),
    )

    manifest = {
        "schema": 1,
        "txid": "tx1",
        "applied": ["rtirq_enable"],
        "backups": [],
        "effects": [
            {
                "kind": "systemd_unit_toggle",
                "unit": "rtirq.service",
                "pre": {"enabled": "not-found", "active": "inactive"},
                "result": {"returncode": 1, "stdout": "", "stderr": "Unit rtirq.service does not exist"},
            },
        ],
    }

    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(cli, "_find_transaction_for_knob", lambda _kid: ("tx1", manifest, "user"))
    monkeypatch.setattr(cli, "_knob_restore_targets", lambda _k: ([], ["rtirq.service"], []))
    monkeypatch.setattr(cli, "_filter_manifest_backups_for_knob", lambda *_a, **_kw: [])
    monkeypatch.setattr(cli, "_filter_manifest_effects_for_knob", lambda effects, **_kw: list(effects))
    monkeypatch.setattr(cli.worker_ops, "systemd_restore", lambda _e: None)
    monkeypatch.setattr("audioknob_gui.worker.ops.read_os_release", lambda: {"ID": "test"})
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.resolve_rtirq_config_path",
        lambda _distro_id: str(tmp_path / "rtirq.conf"),
    )

    def _fake_run(argv, *args, **kwargs):
        if argv[:2] == ["systemctl", "is-enabled"] and argv[-1] == "rtirq.service":
            return subprocess.CompletedProcess(args=list(argv), returncode=0, stdout="enabled\n", stderr="")
        if argv[:3] == ["systemctl", "disable", "--now"] and argv[-1] == "rtirq.service":
            return subprocess.CompletedProcess(
                args=list(argv),
                returncode=1,
                stdout="",
                stderr="mock disable failure",
            )
        return subprocess.CompletedProcess(args=list(argv), returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    result = cli._restore_knob_once("rtirq_enable")
    assert result.get("success") is False
    assert "force reset available" in (result.get("error") or "").lower()
    assert "reset did not disable" in (result.get("error") or "").lower()


def test_list_pending_filters_nonexistent_files():
    """Test that list-pending only shows files that still exist."""
    from audioknob_gui.core.transaction import new_tx, write_manifest, backup_file
    from audioknob_gui.worker.cli import cmd_list_pending
    from unittest.mock import MagicMock
    import argparse
    import io
    import sys
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a file, back it up, then delete it
        test_file = Path(tmpdir) / "test_file.txt"
        test_file.write_text("original content")
        
        tx = new_tx(tmpdir)
        backup_meta = backup_file(tx, str(test_file))
        
        manifest = {
            "schema": 1,
            "txid": tx.txid,
            "applied": ["test_knob"],
            "backups": [backup_meta],
            "effects": [],
        }
        write_manifest(tx, manifest)
        
        # Now delete the file
        test_file.unlink()
        
        # Mock list_transactions to return our transaction
        mock_txs = [{
            "txid": tx.txid,
            "root": str(tx.root),
            "backups": [backup_meta],
            "effects": [],
        }]
        
        with patch('audioknob_gui.worker.cli.list_transactions') as mock_list:
            with patch('audioknob_gui.worker.cli.default_paths') as mock_paths:
                mock_paths.return_value = MagicMock(
                    var_lib_dir="/nonexistent",
                    user_state_dir=tmpdir,
                )
                # Root txs empty, user txs return our mock
                mock_list.side_effect = [[], mock_txs]
                
                captured = io.StringIO()
                with patch.object(sys, 'stdout', captured):
                    result = cmd_list_pending(argparse.Namespace())
                
                assert result == 0
                output = json.loads(captured.getvalue())
                
                # File should not be in pending list (it was deleted)
                file_paths = [f["path"] for f in output["files"]]
                assert str(test_file) not in file_paths


def test_list_pending_effect_dedup_keeps_oldest():
    """Test that list-pending keeps the oldest effect (original before state)."""
    from audioknob_gui.worker.cli import cmd_list_pending
    from audioknob_gui.core.transaction import list_transactions
    from unittest.mock import MagicMock
    import argparse
    
    # Mock transactions with same path but different before values
    # Newer transaction first (that's how list_transactions returns)
    mock_root_txs = [
        {
            "txid": "tx2_newer",
            "root": "/var/lib/audioknob-gui/transactions/tx2_newer",
            "backups": [],
            "effects": [
                {"kind": "sysfs_write", "path": "/sys/foo", "before": "B", "after": "C"},
            ],
        },
        {
            "txid": "tx1_older",
            "root": "/var/lib/audioknob-gui/transactions/tx1_older",
            "backups": [],
            "effects": [
                {"kind": "sysfs_write", "path": "/sys/foo", "before": "A", "after": "B"},
            ],
        },
    ]
    
    with patch('audioknob_gui.worker.cli.list_transactions') as mock_list:
        with patch('audioknob_gui.worker.cli.default_paths') as mock_paths:
            mock_paths.return_value = MagicMock(
                var_lib_dir="/var/lib/audioknob-gui",
                user_state_dir="/home/test/.local/state/audioknob-gui",
            )
            # Root txs return our mock, user txs return empty
            mock_list.side_effect = [mock_root_txs, []]
            
            import io
            import sys
            captured = io.StringIO()
            with patch.object(sys, 'stdout', captured):
                result = cmd_list_pending(argparse.Namespace())
            
            assert result == 0
            output = json.loads(captured.getvalue())
            
            # Should have exactly 1 effect (deduplicated)
            assert output["effects_count"] == 1
            assert len(output["effects"]) == 1
            
            # Should be the OLDEST one (before: "A")
            effect = output["effects"][0]
            assert effect["before"] == "A"
            assert effect["txid"] == "tx1_older"


def test_dedupe_oldest_restore_effects_keeps_oldest_power_and_irq_state():
    from audioknob_gui.worker.cli import _dedupe_oldest_restore_effects

    effects = [
        {
            "kind": "power_profile",
            "knob_id": "power_profile_performance",
            "before": "latency-performance",
            "backend": "tuned",
        },
        {
            "kind": "irq_affinity",
            "irq": 112,
            "before": "B",
            "after": "C",
        },
        {
            "kind": "power_profile",
            "knob_id": "power_profile_performance",
            "before": "performance",
            "before_backend": "powerprofilesctl",
            "backend": "tuned",
        },
        {
            "kind": "irq_affinity",
            "irq": 112,
            "before": "A",
            "after": "B",
        },
    ]

    out = _dedupe_oldest_restore_effects(effects)
    by_kind = {f"{item['kind']}:{item.get('knob_id', item.get('irq'))}": item for item in out}

    assert by_kind["power_profile:power_profile_performance"]["before"] == "performance"
    assert by_kind["irq_affinity:112"]["before"] == "A"


def test_reset_defaults_uses_oldest_root_effect_baseline(monkeypatch):
    import argparse
    import io
    import sys
    from unittest.mock import MagicMock

    from audioknob_gui.worker import cli

    mock_root_txs = [
        {
            "txid": "tx2_newer",
            "root": "/var/lib/audioknob-gui/transactions/tx2_newer",
            "backups": [],
            "effects": [
                {
                    "kind": "power_profile",
                    "knob_id": "power_profile_performance",
                    "before": "latency-performance",
                    "backend": "tuned",
                },
                {
                    "kind": "irq_affinity",
                    "irq": 112,
                    "before": "B",
                    "after": "C",
                },
            ],
        },
        {
            "txid": "tx1_older",
            "root": "/var/lib/audioknob-gui/transactions/tx1_older",
            "backups": [],
            "effects": [
                {
                    "kind": "power_profile",
                    "knob_id": "power_profile_performance",
                    "before": "performance",
                    "before_backend": "powerprofilesctl",
                    "backend": "tuned",
                },
                {
                    "kind": "irq_affinity",
                    "irq": 112,
                    "before": "A",
                    "after": "B",
                },
            ],
        },
    ]

    captured_effects: dict[str, list[dict]] = {}

    monkeypatch.setattr(cli, "list_transactions", lambda _path: mock_root_txs)
    monkeypatch.setattr(
        cli,
        "default_paths",
        lambda: MagicMock(var_lib_dir="/var/lib/audioknob-gui", user_state_dir="/home/test/.local/state/audioknob-gui"),
    )
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli, "_log_audit_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "restore_sysfs", lambda effects: captured_effects.setdefault("sysfs", list(effects)) or [])
    monkeypatch.setattr(cli.worker_ops, "systemd_restore", lambda _effect: None)

    def _fake_restore_irq_affinity(effects, *, warnings=None):
        captured_effects["irq"] = list(effects)
        if warnings is not None:
            warnings.extend([])
        return []

    def _fake_restore_power_profile_effects(effects, errors):
        captured_effects["power"] = list(effects)
        return 1

    monkeypatch.setattr(cli, "restore_irq_affinity", _fake_restore_irq_affinity)
    monkeypatch.setattr(cli, "_restore_power_profile_effects", _fake_restore_power_profile_effects)

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_reset_defaults(argparse.Namespace(scope="root"))

    assert rc == 0
    assert captured_effects["power"][0]["before"] == "performance"
    assert captured_effects["irq"][0]["before"] == "A"


def test_restore_irq_affinity_skips_kernel_managed_permission_errors(monkeypatch):
    from audioknob_gui.worker.ops import restore_irq_affinity

    class _FakePath:
        def __init__(self, path: str) -> None:
            self._path = path

        def exists(self) -> bool:
            return True

        def write_text(self, _text: str, encoding: str = "utf-8") -> None:
            raise PermissionError(1, "Operation not permitted")

        def __str__(self) -> str:
            return self._path

    monkeypatch.setattr("audioknob_gui.worker.ops.Path", _FakePath)

    warnings: list[str] = []
    errors = restore_irq_affinity(
        [{"kind": "irq_affinity", "irq": 112, "before": "0-31"}],
        warnings=warnings,
    )

    assert errors == []
    assert warnings == ["Skipped kernel-managed IRQ affinity restore: /proc/irq/112/smp_affinity_list"]


def test_find_transaction_for_knob_returns_oldest():
    """_find_transaction_for_knob() must return the OLDEST tx so restore-knob restores original state."""
    from audioknob_gui.worker.cli import _find_transaction_for_knob
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmpdir:
        var_lib = Path(tmpdir) / "var"
        user_state = Path(tmpdir) / "user"
        (var_lib / "transactions").mkdir(parents=True)
        (user_state / "transactions").mkdir(parents=True)

        # Create two root transactions for the same knob.
        # Newer-first is what list_transactions() returns.
        tx_newer_root = var_lib / "transactions" / "tx_newer"
        tx_older_root = var_lib / "transactions" / "tx_older"
        tx_newer_root.mkdir(parents=True)
        tx_older_root.mkdir(parents=True)

        (tx_newer_root / "manifest.json").write_text(
            json.dumps({"schema": 1, "applied": ["kernel_audit_off"], "backups": [], "effects": []}),
            encoding="utf-8",
        )
        (tx_older_root / "manifest.json").write_text(
            json.dumps({"schema": 1, "applied": ["kernel_audit_off"], "backups": [], "effects": []}),
            encoding="utf-8",
        )

        mock_root_txs = [
            {"txid": "tx_newer", "root": str(tx_newer_root), "applied": ["kernel_audit_off"]},
            {"txid": "tx_older", "root": str(tx_older_root), "applied": ["kernel_audit_off"]},
        ]

        with patch("audioknob_gui.worker.cli.default_paths") as mock_paths:
            with patch("audioknob_gui.worker.cli.list_transactions") as mock_list:
                mock_paths.return_value = MagicMock(var_lib_dir=str(var_lib), user_state_dir=str(user_state))
                mock_list.side_effect = [mock_root_txs, []]

                txid, manifest, scope = _find_transaction_for_knob("kernel_audit_off")
                assert txid == "tx_older"
                assert scope == "root"
                assert manifest is not None


def test_restore_knob_is_surgical_for_batched_transactions(monkeypatch):
    """restore-knob must not restore unrelated files from the same transaction."""
    from unittest.mock import MagicMock

    from audioknob_gui.core.transaction import backup_file, new_tx, write_manifest
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        user_state = root / "user"
        var_lib = root / "var"
        user_state.mkdir(parents=True, exist_ok=True)
        var_lib.mkdir(parents=True, exist_ok=True)

        # Two files, backed up as part of a single tx (simulating a batched root/user apply).
        file_a = root / "a.conf"
        file_b = root / "b.conf"
        file_a.write_text("A0\n", encoding="utf-8")
        file_b.write_text("B0\n", encoding="utf-8")

        tx = new_tx(str(user_state))
        meta_a = backup_file(tx, str(file_a))
        meta_b = backup_file(tx, str(file_b))

        # Mutate both files after backing up.
        file_a.write_text("A1\n", encoding="utf-8")
        file_b.write_text("B1\n", encoding="utf-8")

        write_manifest(
            tx,
            {
                "schema": 1,
                "txid": tx.txid,
                "applied": ["knob_a", "knob_b"],
                "backups": [meta_a, meta_b],
                "effects": [],
            },
        )

        knob_a = Knob(
            id="knob_a",
            title="A",
            description="",
            category="test",
            risk_level="low",
            requires_root=False,
            requires_reboot=False,
            requires_groups=(),
            requires_commands=(),
            depends_on=(),
            capabilities=Capabilities(read=True, apply=True, restore=True),
            impl=Impl(kind="sysctl_conf", params={"path": str(file_a), "lines": ["x=1"]}),
        )
        knob_b = Knob(
            id="knob_b",
            title="B",
            description="",
            category="test",
            risk_level="low",
            requires_root=False,
            requires_reboot=False,
            requires_groups=(),
            requires_commands=(),
            depends_on=(),
            capabilities=Capabilities(read=True, apply=True, restore=True),
            impl=Impl(kind="sysctl_conf", params={"path": str(file_b), "lines": ["y=1"]}),
        )

        monkeypatch.setattr(cli, "load_registry", lambda _path: [knob_a, knob_b])
        monkeypatch.setattr(
            cli,
            "default_paths",
            lambda: MagicMock(var_lib_dir=str(var_lib), user_state_dir=str(user_state)),
        )

        result = cli._restore_knob_once("knob_a")
        assert result.get("success") is True

        # Only file_a should be restored.
        assert file_a.read_text(encoding="utf-8") == "A0\n"
        assert file_b.read_text(encoding="utf-8") == "B1\n"


def test_kernel_cmdline_status_param_fallback_for_dynamic_knobs():
    """Status checks should use key-name fallback when dynamic cores are unset."""
    from audioknob_gui.worker.cli import _kernel_cmdline_status_param

    state = {}
    assert _kernel_cmdline_status_param(state, "kernel_isolcpus") == "isolcpus"
    assert _kernel_cmdline_status_param(state, "kernel_nohz_full") == "nohz_full"
    assert _kernel_cmdline_status_param(state, "kernel_rcu_nocbs") == "rcu_nocbs"
    assert _kernel_cmdline_status_param(state, "kernel_irqaffinity") is None


def test_cmd_status_uses_kernel_status_param_fallback(monkeypatch):
    """cmd_status should pass a non-empty param for dynamic kernel status checks."""
    import argparse
    import io
    import sys

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="kernel_isolcpus",
        title="CPU Isolation",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=True,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="kernel_cmdline", params={"param": ""}),
    )

    captured_param: dict[str, str] = {}

    def _fake_status(k):
        captured_param["value"] = str(k.impl.params.get("param", ""))
        return "not_applied"

    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {})
    monkeypatch.setattr(cli, "check_knob_status", _fake_status)

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_status(argparse.Namespace(registry="unused"))

    assert rc == 0
    assert captured_param.get("value") == "isolcpus"


def test_cmd_status_keeps_neutral_workqueue_selector_out_of_status_params(monkeypatch) -> None:
    import argparse
    import io
    import json
    import sys

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="kernel_workqueue_cpumask",
        title="Workqueue cpumask",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="sysfs_glob_kv", params={"glob": "/sys/devices/virtual/workqueue/cpumask", "value": "0-1"}),
    )

    captured_value: dict[str, str] = {}

    def _fake_status(k):
        captured_value["value"] = str(k.impl.params.get("value", ""))
        return "applied"

    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {"kernel_workqueue_cpumask_cores": [0, 1, 2, 3]})
    monkeypatch.setattr(cli, "check_knob_status", _fake_status)
    monkeypatch.setattr("audioknob_gui.core.irq.read_cpu_present", lambda: {0, 1, 2, 3})

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_status(argparse.Namespace(registry="unused"))

    payload = json.loads(captured.getvalue())
    assert rc == 0
    assert captured_value.get("value") == "0-1"
    assert payload["statuses"][0]["status"] == "sys_default"


def test_cmd_status_keeps_empty_irqbalance_selector_out_of_status_params(monkeypatch) -> None:
    import argparse
    import io
    import json
    import sys

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="irqbalance_banned_cpulist",
        title="IRQ Balance Policy",
        description="",
        category="irq",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysctl_conf",
            params={"path": "/etc/sysconfig/irqbalance", "lines": ["IRQBALANCE_BANNED_CPULIST=0-1"]},
        ),
    )

    captured_params: dict[str, object] = {}

    def _fake_status(k):
        captured_params["path"] = k.impl.params.get("path")
        captured_params["lines"] = list(k.impl.params.get("lines", []))
        captured_params["clear_prefixes"] = list(k.impl.params.get("clear_prefixes", []))
        return "applied"

    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {"irqbalance_banned_cpulist_cores": []})
    monkeypatch.setattr(cli, "check_knob_status", _fake_status)
    monkeypatch.setattr(cli.worker_ops, "read_os_release", lambda: {"ID": "ubuntu"})
    monkeypatch.setattr(
        cli.worker_ops,
        "resolve_irqbalance_config_path",
        lambda _distro_id: "/etc/default/irqbalance",
    )

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_status(argparse.Namespace(registry="unused"))

    payload = json.loads(captured.getvalue())
    assert rc == 0
    assert captured_params["path"] == "/etc/default/irqbalance"
    assert captured_params["lines"] == ["IRQBALANCE_BANNED_CPULIST=0-1"]
    assert captured_params["clear_prefixes"] == []
    assert payload["statuses"][0]["status"] == "sys_default"


def test_normalize_status_result_marks_neutral_irqbalance_state_sys_default() -> None:
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="irqbalance_banned_cpulist",
        title="IRQ Balance Policy",
        description="",
        category="irq",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysctl_conf",
            params={"path": "/etc/sysconfig/irqbalance", "lines": ["IRQBALANCE_BANNED_CPULIST=0-1"]},
        ),
    )

    status = cli._normalize_status_result(knob, "applied", {"irqbalance_banned_cpulist_cores": []})

    assert status == "sys_default"


def test_normalize_status_result_marks_neutral_workqueue_state_sys_default(monkeypatch) -> None:
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="kernel_workqueue_cpumask",
        title="Workqueue cpumask",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="sysfs_glob_kv", params={"glob": "/sys/devices/virtual/workqueue/cpumask", "value": "0-1"}),
    )

    monkeypatch.setattr("audioknob_gui.core.irq.read_cpu_present", lambda: {0, 1, 2, 3})

    status = cli._normalize_status_result(knob, "applied", {"kernel_workqueue_cpumask_cores": [0, 1, 2, 3]})

    assert status == "sys_default"


def test_normalize_status_result_marks_systemd_row_active_external_without_transaction(monkeypatch) -> None:
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="irqbalance_disable",
        title="IRQ Balance",
        description="",
        category="irq",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="systemd_unit_toggle", params={"unit": "irqbalance.service", "action": "disable_now"}),
    )

    monkeypatch.setattr(cli, "_latest_effect_for_knob", lambda *args, **kwargs: None)

    status = cli._normalize_status_result(knob, "applied", {})

    assert status == "active_external"


def test_normalize_status_result_marks_power_profile_active_external_when_latest_effect_mismatches(
    monkeypatch,
) -> None:
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="power_profile_performance",
        title="Power Profile",
        description="",
        category="power",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="power_profile",
            params={"backend": "auto", "ppd_profile": "performance", "tuned_profile": "latency-performance"},
        ),
    )

    monkeypatch.setattr(
        cli.worker_ops,
        "select_power_profile_backend",
        lambda _params: {"backend": "powerprofilesctl", "cmd": "/usr/bin/powerprofilesctl"},
    )
    monkeypatch.setattr(cli.worker_ops, "read_power_profile", lambda _backend, _cmd: "performance")
    monkeypatch.setattr(
        cli,
        "_latest_effect_for_knob",
        lambda *args, **kwargs: {"after": "latency-performance", "backend": "tuned"},
    )

    status = cli._normalize_status_result(knob, "applied", {})

    assert status == "active_external"


def test_apply_root_state_overrides_irqbalance_uses_prefix_replace(monkeypatch):
    from audioknob_gui.worker.cli import _apply_root_state_overrides

    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.read_os_release",
        lambda: {"ID": "ubuntu"},
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.resolve_irqbalance_config_path",
        lambda _distro_id: "/etc/default/irqbalance",
    )

    params = {
        "path": "/etc/sysconfig/irqbalance",
        "lines": ["IRQBALANCE_BANNED_CPULIST=0-1"],
    }
    state = {"irqbalance_banned_cpulist_cores": [2, 3]}

    out = _apply_root_state_overrides("irqbalance_banned_cpulist", params, state)

    assert out["path"] == "/etc/default/irqbalance"
    assert out["lines"] == ["IRQBALANCE_BANNED_CPULIST=2,3"]
    assert out["replace_prefixes"] == ["IRQBALANCE_BANNED_CPULIST="]
    assert out.get("replace_file") is not True


def test_force_reset_remove_lines_supports_prefixes(tmp_path):
    from audioknob_gui.worker.cli import _force_reset_remove_lines

    target = tmp_path / "irqbalance"
    target.write_text(
        "IRQBALANCE_BANNED_CPULIST=0-1\n"
        "IRQBALANCE_ONESHOT=0\n",
        encoding="utf-8",
    )

    success, message = _force_reset_remove_lines(
        str(target),
        [],
        remove_prefixes=["IRQBALANCE_BANNED_CPULIST="],
    )

    assert success is True
    assert "Removed" in message
    assert target.read_text(encoding="utf-8") == "IRQBALANCE_ONESHOT=0\n"


@pytest.mark.parametrize(
    "knob_id,kind,helper_name",
    [
        ("irq_pinning", "irq_affinity", "_force_reset_irq_affinity"),
        ("power_profile_performance", "power_profile", "_force_reset_power_profile"),
        ("qjackctl_server_prefix_rt", "qjackctl_server_prefix", "_force_reset_qjackctl_server_prefix"),
        ("pipewire_pro_audio_profile", "wpctl_profile", "_force_reset_wpctl_profile"),
    ],
)
def test_cmd_force_reset_knob_dispatches_rb001_kinds(monkeypatch, knob_id, kind, helper_name):
    import argparse
    import io
    import sys

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id=knob_id,
        title="Test",
        description="",
        category="test",
        risk_level="low",
        requires_root=False,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind=kind, params={}),
    )
    called: dict[str, bool] = {}

    def _fake_handler(_params):
        called["hit"] = True
        return True, f"handled {kind}"

    monkeypatch.setattr(cli, "load_registry", lambda _registry: [knob])
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {})
    monkeypatch.setattr(cli, "_log_audit_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, helper_name, _fake_handler)

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_force_reset_knob(argparse.Namespace(knob_id=knob_id, registry="unused"))

    payload = json.loads(captured.getvalue())
    assert rc == 0
    assert payload["success"] is True
    assert payload["message"] == f"handled {kind}"
    assert called.get("hit") is True


def test_force_reset_wpctl_profile_declines_pro_audio(monkeypatch):
    import subprocess

    from audioknob_gui.worker.cli import _force_reset_wpctl_profile

    inspect_stdout = """
id 42, type PipeWire:Interface:Device
Active Profile: pro-audio
device.profile.pro = "true"
"""

    monkeypatch.setattr("audioknob_gui.platform.packages.which_command", lambda _name: "wpctl")
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.subprocess.run",
        lambda *_a, **_kw: subprocess.CompletedProcess(args=["wpctl", "inspect", "42"], returncode=0, stdout=inspect_stdout, stderr=""),
    )

    success, message = _force_reset_wpctl_profile({"device_id": "42"})
    assert success is False
    assert "Cannot safely force-reset Pro Audio profile" in message


def test_kernel_cmdline_clear_param_detects_explicit_empty() -> None:
    from audioknob_gui.worker.cli import _kernel_cmdline_clear_param

    assert _kernel_cmdline_clear_param({"kernel_isolcpus_cores": []}, "kernel_isolcpus") == "isolcpus"
    assert _kernel_cmdline_clear_param({"kernel_nohz_full_cores": []}, "kernel_nohz_full") == "nohz_full"
    assert _kernel_cmdline_clear_param({"kernel_rcu_nocbs_cores": []}, "kernel_rcu_nocbs") == "rcu_nocbs"
    assert _kernel_cmdline_clear_param(
        {"irq_housekeeping_auto": False, "kernel_irqaffinity_cores": []},
        "kernel_irqaffinity",
    ) == "irqaffinity"
    assert _kernel_cmdline_clear_param(
        {"irq_housekeeping_auto": True, "irq_pinning_cpu_cores": []},
        "kernel_irqaffinity",
    ) == "irqaffinity"


def test_cmd_apply_kernel_core_clear_removes_cmdline_param(monkeypatch, tmp_path):
    import argparse
    import io
    import sys
    from types import SimpleNamespace

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli
    from audioknob_gui.worker.ops import DistroInfo

    cmdline = tmp_path / "cmdline"
    cmdline.write_text("quiet splash isolcpus=2,3 threadirqs\n", encoding="utf-8")

    knob = Knob(
        id="kernel_isolcpus",
        title="CPU Isolation",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=True,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(kind="kernel_cmdline", params={"param": ""}),
    )

    monkeypatch.setattr(cli, "_require_root", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(
        cli,
        "default_paths",
        lambda: SimpleNamespace(var_lib_dir=str(tmp_path / "var"), user_state_dir=str(tmp_path / "user")),
    )
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {"kernel_isolcpus_cores": []})
    monkeypatch.setattr(cli, "_log_audit_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        "audioknob_gui.worker.ops.detect_distro",
        lambda: DistroInfo(
            distro_id="test",
            boot_system="bls",
            kernel_cmdline_file=str(cmdline),
            kernel_cmdline_update_cmd=[],
        ),
    )

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_apply(argparse.Namespace(registry="unused", knob=["kernel_isolcpus"]))

    assert rc == 0
    assert "isolcpus=" not in cmdline.read_text(encoding="utf-8")
    payload = json.loads(captured.getvalue())
    assert payload["applied"] == ["kernel_isolcpus"]


def test_cmd_apply_irqbalance_clear_removes_banned_line(monkeypatch, tmp_path):
    import argparse
    import io
    import subprocess
    import sys
    from types import SimpleNamespace

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    irqbalance_cfg = tmp_path / "irqbalance"
    irqbalance_cfg.write_text(
        "IRQBALANCE_BANNED_CPULIST=2,3\nIRQBALANCE_ONESHOT=0\n",
        encoding="utf-8",
    )

    knob = Knob(
        id="irqbalance_banned_cpulist",
        title="IRQ Balance Policy",
        description="",
        category="irq",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysctl_conf",
            params={
                "path": "/etc/sysconfig/irqbalance",
                "lines": ["IRQBALANCE_BANNED_CPULIST=0-1"],
            },
        ),
    )

    monkeypatch.setattr(cli, "_require_root", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(
        cli,
        "default_paths",
        lambda: SimpleNamespace(var_lib_dir=str(tmp_path / "var"), user_state_dir=str(tmp_path / "user")),
    )
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {"irqbalance_banned_cpulist_cores": []})
    monkeypatch.setattr(cli, "_log_audit_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.read_os_release",
        lambda: {"ID": "ubuntu"},
    )
    monkeypatch.setattr(
        "audioknob_gui.worker.cli.worker_ops.resolve_irqbalance_config_path",
        lambda _distro_id: str(irqbalance_cfg),
    )
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0] if args else [], returncode=0, stdout="", stderr=""),
    )

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_apply(argparse.Namespace(registry="unused", knob=["irqbalance_banned_cpulist"]))

    assert rc == 0
    text = irqbalance_cfg.read_text(encoding="utf-8")
    assert "IRQBALANCE_BANNED_CPULIST=" not in text
    assert "IRQBALANCE_ONESHOT=0" in text


def test_cmd_apply_cgroup_clear_deletes_dropin(monkeypatch, tmp_path):
    import argparse
    import io
    import subprocess
    import sys
    from types import SimpleNamespace

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    dropin = tmp_path / "99-audioknob-cpuset.conf"
    dropin.write_text("[Slice]\nAllowedCPUs=2 3\nCPUWeight=100\n", encoding="utf-8")

    knob = Knob(
        id="cgroup_user_slice_allowed_cpus",
        title="Cgroup CPU Partition",
        description="",
        category="cpu",
        risk_level="high",
        requires_root=True,
        requires_reboot=True,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysctl_conf",
            params={
                "path": str(dropin),
                "lines": ["[Slice]", "AllowedCPUs=0-3", "CPUWeight=100"],
            },
        ),
    )

    monkeypatch.setattr(cli, "_require_root", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(
        cli,
        "default_paths",
        lambda: SimpleNamespace(var_lib_dir=str(tmp_path / "var"), user_state_dir=str(tmp_path / "user")),
    )
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {"cgroup_user_slice_allowed_cores": []})
    monkeypatch.setattr(cli, "_log_audit_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0] if args else [], returncode=0, stdout="", stderr=""),
    )

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_apply(argparse.Namespace(registry="unused", knob=["cgroup_user_slice_allowed_cpus"]))

    assert rc == 0
    assert not dropin.exists()


def test_cmd_apply_irq_pinning_clear_uses_reset_path(monkeypatch, tmp_path):
    import argparse
    import io
    import sys
    from types import SimpleNamespace

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="irq_pinning",
        title="IRQ Pinning",
        description="",
        category="irq",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="irq_affinity",
            params={
                "cpu_cores": "0,1",
                "device_keys": [],
                "persist_state_path": "/var/lib/audioknob-gui/state.json",
                "persist_unit": "audioknob-irq-pinning.service",
                "persist_unit_path": "/etc/systemd/system/audioknob-irq-pinning.service",
            },
        ),
    )
    called: dict[str, dict] = {}

    def _fake_force_reset(params):
        called["params"] = dict(params)
        return True, "reset ok"

    monkeypatch.setattr(cli, "_require_root", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(
        cli,
        "default_paths",
        lambda: SimpleNamespace(var_lib_dir=str(tmp_path / "var"), user_state_dir=str(tmp_path / "user")),
    )
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {"irq_pinning_cpu_cores": []})
    monkeypatch.setattr(cli, "_log_audit_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "_force_reset_irq_affinity", _fake_force_reset)

    captured = io.StringIO()
    with patch.object(sys, "stdout", captured):
        rc = cli.cmd_apply(argparse.Namespace(registry="unused", knob=["irq_pinning"]))

    assert rc == 0
    assert "params" in called
    payload = json.loads(captured.getvalue())
    assert payload["applied"] == ["irq_pinning"]


def test_cmd_apply_sysfs_write_error_raises_clear_message(monkeypatch, tmp_path):
    import argparse
    from types import SimpleNamespace

    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker import cli

    knob = Knob(
        id="kernel_workqueue_cpumask",
        title="Workqueue cpumask",
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
            kind="sysfs_glob_kv",
            params={
                "glob": "/sys/devices/virtual/workqueue/cpumask",
                "value": "0-1",
            },
        ),
    )

    def _raise_sysfs(*_args, **_kwargs):
        raise OSError(75, "Value too large for defined data type")

    monkeypatch.setattr(cli, "_require_root", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda _path: [knob])
    monkeypatch.setattr(
        cli,
        "default_paths",
        lambda: SimpleNamespace(var_lib_dir=str(tmp_path / "var"), user_state_dir=str(tmp_path / "user")),
    )
    monkeypatch.setattr(cli, "_load_gui_state", lambda: {"kernel_workqueue_cpumask_cores": [2, 3]})
    monkeypatch.setattr(cli, "_log_audit_event", lambda *_a, **_kw: None)
    monkeypatch.setattr("audioknob_gui.worker.ops.write_sysfs_values", _raise_sysfs)

    with pytest.raises(SystemExit, match="failed to write sysfs value"):
        cli.cmd_apply(argparse.Namespace(registry="unused", knob=["kernel_workqueue_cpumask"]))


def test_check_knob_status_sysctl_clear_prefixes_uses_absence_semantics(tmp_path):
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    path = tmp_path / "irqbalance"
    path.write_text(
        "IRQBALANCE_BANNED_CPULIST=2,3\nIRQBALANCE_ONESHOT=0\n",
        encoding="utf-8",
    )

    knob = Knob(
        id="irqbalance_banned_cpulist",
        title="IRQ Balance Policy",
        description="",
        category="irq",
        risk_level="medium",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysctl_conf",
            params={
                "path": str(path),
                "lines": [],
                "clear_prefixes": ["IRQBALANCE_BANNED_CPULIST="],
            },
        ),
    )

    assert check_knob_status(knob) == "not_applied"
    path.write_text("IRQBALANCE_ONESHOT=0\n", encoding="utf-8")
    assert check_knob_status(knob) == "applied"
    path.unlink()
    assert check_knob_status(knob) == "applied"


def test_check_knob_status_sysctl_clear_file_uses_absence_semantics(tmp_path):
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import check_knob_status

    path = tmp_path / "99-audioknob-cpuset.conf"
    path.write_text("[Slice]\nAllowedCPUs=2 3\n", encoding="utf-8")

    knob = Knob(
        id="cgroup_user_slice_allowed_cpus",
        title="Cgroup CPU Partition",
        description="",
        category="cpu",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysctl_conf",
            params={
                "path": str(path),
                "lines": [],
                "clear_file": True,
            },
        ),
    )

    assert check_knob_status(knob) == "not_applied"
    path.unlink()
    assert check_knob_status(knob) == "applied"


def test_preview_sysctl_clear_file_reports_delete(tmp_path):
    from audioknob_gui.registry import Capabilities, Impl, Knob
    from audioknob_gui.worker.ops import preview

    path = tmp_path / "99-audioknob-cpuset.conf"
    path.write_text("[Slice]\nAllowedCPUs=2 3\n", encoding="utf-8")

    knob = Knob(
        id="cgroup_user_slice_allowed_cpus",
        title="Cgroup CPU Partition",
        description="",
        category="cpu",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysctl_conf",
            params={
                "path": str(path),
                "lines": [],
                "clear_file": True,
            },
        ),
    )

    item = preview(knob, action="apply")
    assert len(item.file_changes) == 1
    assert item.file_changes[0].path == str(path)
    assert item.file_changes[0].action == "delete"

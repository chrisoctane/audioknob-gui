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

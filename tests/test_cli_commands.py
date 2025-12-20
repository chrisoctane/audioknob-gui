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

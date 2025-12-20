"""Tests for transaction backup/restore metadata logic."""

import json
import tempfile
from pathlib import Path

import pytest

from audioknob_gui.core.transaction import (
    RESET_BACKUP,
    RESET_DELETE,
    RESET_PACKAGE,
    new_tx,
    backup_file,
    list_transactions,
)


class TestResetStrategySelection:
    """Tests for reset strategy selection logic."""

    def test_file_we_created_gets_delete_strategy(self, tmp_path: Path) -> None:
        """Files we create should get RESET_DELETE strategy."""
        tx = new_tx(str(tmp_path))
        
        # File doesn't exist yet - we're creating it
        new_file = tmp_path / "new_config.conf"
        
        meta = backup_file(tx, str(new_file))
        
        assert meta["reset_strategy"] == RESET_DELETE
        assert meta["we_created"] is True

    def test_existing_user_file_gets_backup_strategy(self, tmp_path: Path) -> None:
        """Existing user files should get RESET_BACKUP strategy."""
        tx = new_tx(str(tmp_path))
        
        # Create a user file first
        user_file = tmp_path / "existing.conf"
        user_file.write_text("original content")
        
        meta = backup_file(tx, str(user_file))
        
        assert meta["reset_strategy"] == RESET_BACKUP
        assert meta["we_created"] is False


class TestTransactionListing:
    """Tests for list_transactions()."""

    def test_list_empty_dir(self, tmp_path: Path) -> None:
        """Empty directory returns empty list."""
        result = list_transactions(tmp_path)
        
        assert result == []

    def test_list_with_transaction(self, tmp_path: Path) -> None:
        """Directory with transaction returns it."""
        # Create a transaction
        tx = new_tx(str(tmp_path))
        
        # Finalize the transaction by writing manifest
        manifest = {
            "applied": ["test_knob"],
            "backups": [],
            "effects": [],
        }
        manifest_path = Path(tx.root) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        
        result = list_transactions(tmp_path)
        
        assert len(result) == 1
        assert result[0]["txid"] == tx.txid
        assert result[0]["applied"] == ["test_knob"]

    def test_list_includes_effects(self, tmp_path: Path) -> None:
        """Transaction listing includes effects."""
        tx = new_tx(str(tmp_path))
        
        manifest = {
            "applied": ["test_knob"],
            "backups": [],
            "effects": [
                {"kind": "sysfs_write", "path": "/sys/test", "before": "0", "after": "1"},
            ],
        }
        manifest_path = Path(tx.root) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        
        result = list_transactions(tmp_path)
        
        assert len(result) == 1
        assert len(result[0]["effects"]) == 1
        assert result[0]["effects"][0]["kind"] == "sysfs_write"


class TestTransactionBackup:
    """Tests for backup_file()."""

    def test_backup_creates_copy(self, tmp_path: Path) -> None:
        """Backup creates a copy of existing file."""
        tx = new_tx(str(tmp_path))
        
        # Create source file
        source = tmp_path / "test.conf"
        source.write_text("test content")
        
        meta = backup_file(tx, str(source))
        
        # Backup should exist (using backup_key)
        backup_key = meta["backup_key"]
        backup_path = Path(tx.root) / "backups" / backup_key
        assert backup_path.exists()
        assert backup_path.read_text() == "test content"

    def test_backup_nonexistent_file(self, tmp_path: Path) -> None:
        """Backup of nonexistent file records we_created=True."""
        tx = new_tx(str(tmp_path))
        
        # File doesn't exist
        nonexistent = tmp_path / "does_not_exist.conf"
        
        meta = backup_file(tx, str(nonexistent))
        
        assert meta["we_created"] is True
        assert meta["reset_strategy"] == RESET_DELETE

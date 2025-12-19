from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Transaction:
    txid: str
    root: Path


# Reset strategy constants
RESET_DELETE = "delete"           # File we created - just delete it
RESET_BACKUP = "backup"           # Restore from our backup
RESET_PACKAGE = "package"         # Restore from package manager
RESET_MANUAL = "manual"           # Requires manual intervention


def new_tx(root_dir: str | Path) -> Transaction:
    root = Path(root_dir)
    txid = f"{time.time_ns():x}"
    tx_root = root / "transactions" / txid
    tx_root.mkdir(parents=True, exist_ok=False)
    (tx_root / "backups").mkdir()
    return Transaction(txid=txid, root=tx_root)


def find_tx(root_dir: str | Path, txid: str) -> Transaction | None:
    """Find an existing transaction by ID."""
    root = Path(root_dir)
    tx_root = root / "transactions" / txid
    if tx_root.exists() and (tx_root / "manifest.json").exists():
        return Transaction(txid=txid, root=tx_root)
    return None


def _backup_key_for_path(abs_path: str) -> str:
    p = abs_path.lstrip("/").replace("/", "__")
    return p


def backup_file(tx: Transaction, abs_path: str, *, we_created: bool = False) -> dict:
    """Backup a file before modifying it.
    
    Args:
        tx: The transaction context
        abs_path: Absolute path to the file
        we_created: True if we're creating a new file (vs modifying existing)
    
    Returns:
        Metadata dict including reset strategy
    """
    p = Path(abs_path)
    key = _backup_key_for_path(abs_path)
    dest = tx.root / "backups" / key
    existed = p.exists()

    meta: dict[str, Any] = {
        "path": abs_path,
        "existed": existed,
        "we_created": we_created or not existed,
        "mode": None,
        "uid": None,
        "gid": None,
        "backup_key": key,
        "reset_strategy": RESET_DELETE if (we_created or not existed) else RESET_BACKUP,
        "package": None,
    }

    # Check package ownership for system files
    if existed and not abs_path.startswith(str(Path.home())):
        try:
            from audioknob_gui.platform.packages import get_package_owner
            pkg_info = get_package_owner(abs_path)
            if pkg_info.owned and pkg_info.can_restore:
                meta["reset_strategy"] = RESET_PACKAGE
                meta["package"] = pkg_info.package
        except Exception:
            pass  # Fall back to backup strategy

    if existed:
        st = p.stat()
        meta.update({"mode": int(st.st_mode & 0o777), "uid": int(st.st_uid), "gid": int(st.st_gid)})
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)

    return meta


def restore_file(tx: Transaction, meta: dict) -> None:
    abs_path = meta["path"]
    existed = bool(meta.get("existed"))
    key = meta["backup_key"]
    backup = tx.root / "backups" / key
    p = Path(abs_path)

    if not existed:
        if p.exists():
            p.unlink()
        return

    if not backup.exists():
        raise FileNotFoundError(f"Missing backup for {abs_path}")

    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, p)

    mode = meta.get("mode")
    if mode is not None:
        os.chmod(p, int(mode))

    uid = meta.get("uid")
    gid = meta.get("gid")
    if uid is not None and gid is not None:
        try:
            os.chown(p, int(uid), int(gid))
        except PermissionError:
            pass


def write_manifest(tx: Transaction, payload: dict) -> None:
    (tx.root / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def reset_file_to_default(meta: dict, tx: Transaction | None = None) -> tuple[bool, str]:
    """Reset a file to its system default state.
    
    Uses the reset_strategy stored in meta to determine the best approach:
    - RESET_DELETE: Delete the file (we created it)
    - RESET_BACKUP: Restore from our backup
    - RESET_PACKAGE: Restore from package manager
    
    Args:
        meta: Backup metadata from backup_file()
        tx: Transaction context (needed for RESET_BACKUP)
    
    Returns:
        (success, message) tuple
    """
    abs_path = meta["path"]
    strategy = meta.get("reset_strategy", RESET_BACKUP)
    p = Path(abs_path)
    
    if strategy == RESET_DELETE:
        # We created this file, just delete it
        try:
            if p.exists():
                p.unlink()
            return True, f"Deleted {abs_path}"
        except Exception as e:
            return False, f"Failed to delete {abs_path}: {e}"
    
    elif strategy == RESET_PACKAGE:
        # Restore from package manager
        package = meta.get("package")
        if not package:
            # Fall back to backup
            strategy = RESET_BACKUP
        else:
            try:
                from audioknob_gui.platform.packages import (
                    PackageInfo,
                    detect_package_manager,
                    restore_package_file,
                )
                pkg_info = PackageInfo(
                    path=abs_path,
                    owned=True,
                    package=package,
                    manager=detect_package_manager(),
                    can_restore=True,
                )
                return restore_package_file(pkg_info)
            except Exception as e:
                return False, f"Failed to restore from package: {e}"
    
    if strategy == RESET_BACKUP:
        # Restore from our backup
        if tx is None:
            return False, "No transaction context for backup restore"
        try:
            restore_file(tx, meta)
            return True, f"Restored {abs_path} from backup"
        except Exception as e:
            return False, f"Failed to restore from backup: {e}"
    
    return False, f"Unknown reset strategy: {strategy}"


def list_transactions(root_dir: str | Path) -> list[dict]:
    """List all transactions with their metadata.
    
    Returns a list of dicts with txid, timestamp, applied knobs, etc.
    """
    root = Path(root_dir)
    tx_dir = root / "transactions"
    if not tx_dir.exists():
        return []
    
    results = []
    for entry in sorted(tx_dir.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Parse timestamp from txid (hex nanoseconds)
            txid = entry.name
            try:
                ts_ns = int(txid, 16)
                ts_sec = ts_ns / 1e9
            except ValueError:
                ts_sec = 0
            results.append({
                "txid": txid,
                "timestamp": ts_sec,
                "applied": manifest.get("applied", []),
                "backups": manifest.get("backups", []),
                "root": str(entry),
            })
        except Exception:
            continue
    
    return results

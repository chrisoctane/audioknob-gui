from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Transaction:
    txid: str
    root: Path


def new_tx(root_dir: str | Path) -> Transaction:
    root = Path(root_dir)
    txid = f"{time.time_ns():x}"
    tx_root = root / "transactions" / txid
    tx_root.mkdir(parents=True, exist_ok=False)
    (tx_root / "backups").mkdir()
    return Transaction(txid=txid, root=tx_root)


def _backup_key_for_path(abs_path: str) -> str:
    p = abs_path.lstrip("/").replace("/", "__")
    return p


def backup_file(tx: Transaction, abs_path: str) -> dict:
    p = Path(abs_path)
    key = _backup_key_for_path(abs_path)
    dest = tx.root / "backups" / key

    meta = {
        "path": abs_path,
        "existed": p.exists(),
        "mode": None,
        "uid": None,
        "gid": None,
        "backup_key": key,
    }

    if p.exists():
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

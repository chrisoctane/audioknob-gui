from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from pathlib import Path

from audioknob_gui.core.paths import default_paths
from audioknob_gui.core.transaction import (
    RESET_BACKUP,
    RESET_DELETE,
    RESET_PACKAGE,
    backup_file,
    list_transactions,
    new_tx,
    reset_file_to_default,
    restore_file,
    write_manifest,
)
from audioknob_gui.platform.detect import dump_detect
from audioknob_gui.registry import load_registry
from audioknob_gui.worker.ops import preview, restore_sysfs, systemd_restore


def _require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("This command must run as root (use pkexec).")


def _registry_default_path() -> str:
    here = Path(__file__).resolve()
    # parents[0] = audioknob_gui/worker/
    # parents[1] = audioknob_gui/
    # parents[2] = repo root
    repo_root = here.parents[2]
    return str(repo_root / "config" / "registry.json")


def _load_gui_state() -> dict:
    """Best-effort load of GUI state.json (user-scope)."""
    paths = default_paths()
    p = Path(paths.user_state_dir) / "state.json"
    try:
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _qjackctl_cpu_cores_override(state: dict) -> str | None:
    """Return comma-separated cpu list for taskset, or None if unset."""
    raw = state.get("qjackctl_cpu_cores")
    if raw is None:
        return None
    if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
        if not raw:
            # Explicitly configured as "no pinning"
            return ""
        return ",".join(str(int(x)) for x in raw)
    return None


def cmd_detect(_: argparse.Namespace) -> int:
    print(json.dumps(dump_detect(), indent=2, sort_keys=True))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    state = _load_gui_state()
    qjackctl_override = _qjackctl_cpu_cores_override(state)

    items = []
    for kid in args.knob:
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")

        # Apply per-user overrides from GUI state (non-root knobs)
        if (
            qjackctl_override is not None
            and k.impl is not None
            and k.impl.kind == "qjackctl_server_prefix"
        ):
            new_params = dict(k.impl.params)
            new_params["cpu_cores"] = qjackctl_override
            k = replace(k, impl=replace(k.impl, params=new_params))

        items.append(preview(k, action=args.action))

    payload = {
        "schema": 1,
        "items": [
            {
                "knob_id": i.knob_id,
                "title": i.title,
                "description": i.description,
                "requires_root": i.requires_root,
                "requires_reboot": i.requires_reboot,
                "risk_level": i.risk_level,
                "action": i.action,
                "file_changes": [
                    {"path": fc.path, "action": fc.action, "diff": fc.diff}
                    for fc in i.file_changes
                ],
                "would_run": i.would_run,
                "would_write": i.would_write,
                "notes": i.notes,
            }
            for i in items
        ],
    }

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_apply_user(args: argparse.Namespace) -> int:
    """Apply non-root knobs (user-scope transactions)."""
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    paths = default_paths()
    tx = new_tx(paths.user_state_dir)

    state = _load_gui_state()
    qjackctl_override = _qjackctl_cpu_cores_override(state)

    backups: list[dict] = []
    applied: list[str] = []

    for kid in args.knob:
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")
        if k.requires_root:
            raise SystemExit(f"Knob {kid} requires root; use 'apply' command with pkexec")
        if not k.capabilities.apply:
            continue
        if not k.impl:
            continue

        kind = k.impl.kind
        params = k.impl.params

        if kind == "qjackctl_server_prefix":
            from pathlib import Path

            path_str = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
            path = Path(path_str).expanduser()
            backups.append(backup_file(tx, str(path)))

            from audioknob_gui.core.qjackctl import ensure_server_flags

            ensure_rt = bool(params.get("ensure_rt", True))
            ensure_priority = bool(params.get("ensure_priority", False))
            cpu_cores = qjackctl_override if qjackctl_override is not None else params.get("cpu_cores")
            if cpu_cores is not None:
                cpu_cores = str(cpu_cores)

            before, after = ensure_server_flags(
                path, ensure_rt=ensure_rt, ensure_priority=ensure_priority, cpu_cores=cpu_cores
            )

        else:
            raise SystemExit(f"Unsupported non-root knob kind: {kind}")

        applied.append(kid)

    manifest = {
        "schema": 1,
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": [],
    }
    write_manifest(tx, manifest)

    print(json.dumps({"schema": 1, "txid": tx.txid, "applied": applied}, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    _require_root()

    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    paths = default_paths()
    tx = new_tx(paths.var_lib_dir)

    effects: list[dict] = []
    backups: list[dict] = []
    applied: list[str] = []

    for kid in args.knob:
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")
        if not k.capabilities.apply:
            continue
        if not k.impl:
            continue

        kind = k.impl.kind
        params = k.impl.params

        if kind == "pam_limits_audio_group":
            path = str(params["path"])
            backups.append(backup_file(tx, path))

            want_lines = [str(x) for x in params.get("lines", [])]
            before = ""
            try:
                before = Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""
            before_lines = before.splitlines()
            after_lines = list(before_lines)
            for line in want_lines:
                if line not in after_lines:
                    after_lines.append(line)
            after = "\n".join(after_lines).rstrip("\n") + "\n"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(after, encoding="utf-8")

        elif kind == "sysctl_conf":
            path = str(params["path"])
            backups.append(backup_file(tx, path))

            want_lines = [str(x) for x in params.get("lines", [])]
            before = ""
            try:
                before = Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""
            before_lines = before.splitlines()
            after_lines = list(before_lines)
            for line in want_lines:
                if line not in after_lines:
                    after_lines.append(line)
            after = "\n".join(after_lines).rstrip("\n") + "\n"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(after, encoding="utf-8")

        elif kind == "systemd_unit_toggle":
            from audioknob_gui.worker.ops import systemd_disable_now

            unit = str(params["unit"])
            action = str(params.get("action", ""))
            if action != "disable_now":
                raise SystemExit(f"Unsupported systemd action: {action}")
            effects.append(systemd_disable_now(unit))

        elif kind == "sysfs_glob_kv":
            from audioknob_gui.worker.ops import write_sysfs_values

            effects.extend(write_sysfs_values(str(params["glob"]), str(params["value"])))

        elif kind == "read_only":
            pass
        else:
            raise SystemExit(f"Unsupported knob kind: {kind}")

        applied.append(kid)

    manifest = {
        "schema": 1,
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": effects,
    }
    write_manifest(tx, manifest)

    print(json.dumps({"schema": 1, "txid": tx.txid, "applied": applied}, indent=2))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Restore a transaction (root or user-scope)."""
    paths = default_paths()

    # Try root transactions first, then user
    tx_root = Path(paths.var_lib_dir) / "transactions" / args.txid
    manifest_path = tx_root / "manifest.json"
    is_root = manifest_path.exists()

    if not is_root:
        tx_root = Path(paths.user_state_dir) / "transactions" / args.txid
        manifest_path = tx_root / "manifest.json"
        if not manifest_path.exists():
            raise SystemExit(f"Transaction not found: {args.txid}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Restore files (works for both root and user)
    for meta in manifest.get("backups", []):
        restore_file(type("Tx", (), {"root": tx_root})(), meta)

    # Restore effects (only for root transactions)
    if is_root:
        _require_root()
        effects = manifest.get("effects", [])
        sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
        systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]

        restore_sysfs(sysfs)
        for e in systemd:
            systemd_restore(e)

    print(json.dumps({"schema": 1, "restored": args.txid, "was_root": is_root}, indent=2))
    return 0


def cmd_history(_: argparse.Namespace) -> int:
    paths = default_paths()
    tx_dir = Path(paths.var_lib_dir) / "transactions"
    items: list[dict] = []

    if tx_dir.exists():
        for p in sorted(tx_dir.iterdir()):
            if not p.is_dir():
                continue
            mp = p / "manifest.json"
            if mp.exists():
                try:
                    m = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:
                    m = {"schema": 0}
                items.append({"txid": p.name, "manifest": m})
            else:
                items.append({"txid": p.name, "manifest": None})

    print(json.dumps({"schema": 1, "items": items}, indent=2))
    return 0


def cmd_reset_defaults(args: argparse.Namespace) -> int:
    """Reset all audioknob-gui changes to system defaults.
    
    This uses the reset_strategy stored in each backup:
    - Files we created: delete them
    - Package-owned files: restore from package manager
    - User files: restore from our backup
    """
    paths = default_paths()
    results: list[dict] = []
    errors: list[str] = []
    
    # Gather all transactions (root and user)
    root_txs = list_transactions(paths.var_lib_dir)
    user_txs = list_transactions(paths.user_state_dir)
    
    all_txs = []
    for tx_info in root_txs:
        tx_info["scope"] = "root"
        all_txs.append(tx_info)
    for tx_info in user_txs:
        tx_info["scope"] = "user"
        all_txs.append(tx_info)
    
    if not all_txs:
        print(json.dumps({
            "schema": 1,
            "message": "No transactions found - nothing to reset",
            "reset_count": 0,
            "errors": [],
        }, indent=2))
        return 0
    
    # Track which files we've already reset (avoid duplicate resets)
    reset_paths: set[str] = set()
    
    # Process all transactions (newest first - they're already sorted)
    for tx_info in all_txs:
        txid = tx_info["txid"]
        scope = tx_info["scope"]
        backups = tx_info.get("backups", [])
        
        # Check if this is a root transaction and we need root
        if scope == "root":
            # Check for package resets which need root
            needs_root = any(
                b.get("reset_strategy") == RESET_PACKAGE 
                for b in backups
            )
            if needs_root and os.geteuid() != 0:
                errors.append(f"Transaction {txid} has package-owned files; run with root to reset")
                continue
        
        # Create a Transaction object for backup restore
        from audioknob_gui.core.transaction import Transaction
        tx_root = Path(tx_info["root"])
        tx = Transaction(txid=txid, root=tx_root)
        
        for meta in backups:
            file_path = meta.get("path", "")
            if not file_path or file_path in reset_paths:
                continue
            
            strategy = meta.get("reset_strategy", RESET_BACKUP)
            
            # Check if we need root for package restore
            if strategy == RESET_PACKAGE and os.geteuid() != 0:
                errors.append(f"Need root to restore {file_path} from package")
                continue
            
            success, message = reset_file_to_default(meta, tx)
            results.append({
                "path": file_path,
                "strategy": strategy,
                "success": success,
                "message": message,
            })
            
            if success:
                reset_paths.add(file_path)
            else:
                errors.append(message)
        
        # Also handle effects (sysfs, systemd) for root transactions
        if scope == "root":
            effects = tx_info.get("effects", [])
            # Read manifest for effects since they're not in the summary
            manifest_path = tx_root / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    effects = manifest.get("effects", [])
                except Exception:
                    pass
            
            if effects and os.geteuid() == 0:
                sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
                systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]
                
                try:
                    restore_sysfs(sysfs)
                    for e in systemd:
                        systemd_restore(e)
                    results.append({
                        "path": "(effects)",
                        "strategy": "effects",
                        "success": True,
                        "message": f"Restored {len(sysfs)} sysfs + {len(systemd)} systemd effects",
                    })
                except Exception as ex:
                    errors.append(f"Failed to restore effects: {ex}")
    
    print(json.dumps({
        "schema": 1,
        "message": f"Reset {len(reset_paths)} files to system defaults",
        "reset_count": len(reset_paths),
        "results": results,
        "errors": errors,
    }, indent=2))
    
    return 1 if errors else 0


def cmd_list_changes(_: argparse.Namespace) -> int:
    """List all files modified by audioknob-gui across all transactions."""
    paths = default_paths()
    
    root_txs = list_transactions(paths.var_lib_dir)
    user_txs = list_transactions(paths.user_state_dir)
    
    all_files: dict[str, dict] = {}
    
    for tx_info in root_txs + user_txs:
        scope = "root" if tx_info in root_txs else "user"
        for meta in tx_info.get("backups", []):
            file_path = meta.get("path", "")
            if file_path and file_path not in all_files:
                all_files[file_path] = {
                    "path": file_path,
                    "scope": scope,
                    "txid": tx_info["txid"],
                    "reset_strategy": meta.get("reset_strategy", RESET_BACKUP),
                    "package": meta.get("package"),
                    "we_created": meta.get("we_created", False),
                }
    
    print(json.dumps({
        "schema": 1,
        "files": list(all_files.values()),
        "count": len(all_files),
    }, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="audioknob-worker")
    p.add_argument("--registry", default=_registry_default_path())

    sub = p.add_subparsers(dest="cmd", required=True)

    sd = sub.add_parser("detect", help="Detect audio stack and devices (read-only)")
    sd.set_defaults(func=cmd_detect)

    sp = sub.add_parser("preview", help="Preview planned changes")
    sp.add_argument("--action", choices=["apply", "restore"], default="apply")
    sp.add_argument("knob", nargs="+")
    sp.set_defaults(func=cmd_preview)

    sa = sub.add_parser("apply", help="Apply root knobs (creates a transaction, requires root)")
    sa.add_argument("knob", nargs="+")
    sa.set_defaults(func=cmd_apply)

    sau = sub.add_parser("apply-user", help="Apply non-root knobs (creates user-scope transaction)")
    sau.add_argument("knob", nargs="+")
    sau.set_defaults(func=cmd_apply_user)

    sr = sub.add_parser("restore", help="Restore a transaction")
    sr.add_argument("txid")
    sr.set_defaults(func=cmd_restore)

    sh = sub.add_parser("history", help="List transactions")
    sh.set_defaults(func=cmd_history)

    srd = sub.add_parser("reset-defaults", help="Reset ALL changes to system defaults")
    srd.set_defaults(func=cmd_reset_defaults)

    slc = sub.add_parser("list-changes", help="List all files modified by audioknob-gui")
    slc.set_defaults(func=cmd_list_changes)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

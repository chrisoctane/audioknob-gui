from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from audioknob_gui.core.paths import default_paths
from audioknob_gui.core.transaction import backup_file, new_tx, restore_file, write_manifest
from audioknob_gui.platform.detect import dump_detect
from audioknob_gui.registry import load_registry
from audioknob_gui.worker.ops import preview, restore_sysfs, systemd_restore


def _require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("This command must run as root (use pkexec).")


def _registry_default_path() -> str:
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    return str(repo_root / "config" / "registry.json")


def cmd_detect(_: argparse.Namespace) -> int:
    print(json.dumps(dump_detect(), indent=2, sort_keys=True))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    items = []
    for kid in args.knob:
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")
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
    _require_root()

    paths = default_paths()
    tx_root = Path(paths.var_lib_dir) / "transactions" / args.txid
    manifest_path = tx_root / "manifest.json"

    if not manifest_path.exists():
        raise SystemExit(f"Transaction not found: {args.txid}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for meta in manifest.get("backups", []):
        restore_file(type("Tx", (), {"root": tx_root})(), meta)

    effects = manifest.get("effects", [])
    sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
    systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]

    restore_sysfs(sysfs)
    for e in systemd:
        systemd_restore(e)

    print(json.dumps({"schema": 1, "restored": args.txid}, indent=2))
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

    sa = sub.add_parser("apply", help="Apply knobs (creates a transaction)")
    sa.add_argument("knob", nargs="+")
    sa.set_defaults(func=cmd_apply)

    sr = sub.add_parser("restore", help="Restore a transaction")
    sr.add_argument("txid")
    sr.set_defaults(func=cmd_restore)

    sh = sub.add_parser("history", help="List transactions")
    sh.set_defaults(func=cmd_history)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

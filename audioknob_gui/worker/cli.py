from __future__ import annotations

import argparse
import json


def cmd_preview(_: argparse.Namespace) -> int:
    # Placeholder: real implementation comes in the worker milestone.
    print(json.dumps({"schema": 1, "items": [], "note": "worker skeleton"}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="audioknob-worker")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preview", help="Preview planned changes (skeleton)").set_defaults(func=cmd_preview)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import difflib


def unified_diff(path: str, before: str, after: str) -> str:
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            a,
            b,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )

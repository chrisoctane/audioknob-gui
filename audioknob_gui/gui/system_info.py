from __future__ import annotations

import os
import re
from pathlib import Path


def _kernel_cmdline_tokens() -> list[str]:
    try:
        raw = Path("/proc/cmdline").read_text(encoding="utf-8").strip()
    except Exception:
        return []
    return [t for t in raw.split() if t]


def _param_present(tokens: list[str], param: str) -> bool:
    if "=" in param:
        return param in tokens
    for token in tokens:
        if token == param or token.startswith(param + "="):
            return True
    return False


def _kernel_is_rt() -> bool:
    try:
        rel = os.uname().release.lower()
    except Exception:
        return False
    return bool(re.search(r"(?:^|[-_])rt\\d|(?:^|[-_])rt$|realtime", rel))


def _read_interrupts_map() -> dict[int, str]:
    try:
        raw = Path("/proc/interrupts").read_text(encoding="utf-8")
    except Exception:
        return {}
    lines: dict[int, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or not stripped[:1].isdigit():
            continue
        if ":" not in stripped:
            continue
        irq_str, rest = stripped.split(":", 1)
        irq_str = irq_str.strip()
        if not irq_str.isdigit():
            continue
        try:
            irq = int(irq_str)
        except Exception:
            continue
        lines[irq] = rest.strip()
    return lines

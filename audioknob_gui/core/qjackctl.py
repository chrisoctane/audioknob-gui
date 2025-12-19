from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QjackCtlConfig:
    def_preset: str
    server_cmd: str | None  # The Server value for the active preset


def _normalize_preset_key(preset: str) -> str:
    # QjackCtl uses backslash-escaped keys in INI: "RaydatRT\Server"
    return preset.replace("\\", "\\\\")


def _read_config(path: str | Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    # Preserve case sensitivity
    cp.optionxform = str
    p = Path(path)
    if p.exists():
        cp.read(p, encoding="utf-8")
    return cp


def _get_active_preset(cp: configparser.ConfigParser) -> str | None:
    if "Presets" not in cp:
        return None
    return cp.get("Presets", "DefPreset", fallback=None)


def _get_server_for_preset(cp: configparser.ConfigParser, preset: str) -> str | None:
    if "Settings" not in cp:
        return None
    key = f"{preset}\\Server"
    return cp.get("Settings", key, fallback=None)


def read_config(path: str | Path) -> QjackCtlConfig:
    cp = _read_config(path)
    def_preset = _get_active_preset(cp) or ""
    server_cmd = None
    if def_preset:
        server_cmd = _get_server_for_preset(cp, def_preset)
    return QjackCtlConfig(def_preset=def_preset, server_cmd=server_cmd)


def ensure_server_has_flags(cmd: str, *, ensure_rt: bool = True, ensure_priority: bool = False, cpu_cores: str | None = None) -> str:
    """Ensure command has -R (and optionally -P90) and taskset prefix if cpu_cores provided."""
    parts = cmd.split()
    if not parts:
        # Empty command, build from scratch
        base = "jackd"
    else:
        # Find jackd or jackdmp
        jackd_idx = None
        for i, tok in enumerate(parts):
            if tok in ("jackd", "jackdmp", "jackstart"):
                jackd_idx = i
                break
        if jackd_idx is None:
            # No jackd found, prepend it
            base = "jackd"
            parts = [base] + parts
        else:
            base = parts[jackd_idx]

    # Remove existing -R and -P flags
    parts = [p for p in parts if not (p.startswith("-R") or p.startswith("-P"))]

    # Rebuild: taskset prefix (if cpu_cores) + base + flags
    result: list[str] = []
    if cpu_cores:
        result.append("taskset")
        result.append("-c")
        result.append(str(cpu_cores))
    result.append(base)
    if ensure_rt:
        result.append("-R")
    if ensure_priority:
        result.append("-P90")
    # Append any remaining args (interface, driver, etc.)
    for p in parts:
        if p not in (base, "taskset", "-c", cpu_cores) if cpu_cores else (base,):
            result.append(p)

    return " ".join(result)


def write_config_with_server_update(
    path: str | Path,
    preset: str,
    new_server_cmd: str,
) -> None:
    """Update the Server value for a preset, preserving the rest of the config."""
    cp = _read_config(path)
    if "Settings" not in cp:
        cp.add_section("Settings")
    key = f"{preset}\\Server"
    cp.set("Settings", key, new_server_cmd)

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        cp.write(f, space_around_delimiters=False)


def ensure_server_flags(
    path: str | Path,
    *,
    ensure_rt: bool = True,
    ensure_priority: bool = False,
    cpu_cores: str | None = None,
) -> tuple[str, str]:
    """Read config, ensure Server command has required flags, return (before, after)."""
    cfg = read_config(path)
    if not cfg.def_preset:
        raise ValueError("No active preset (DefPreset) found in QjackCtl config")
    if not cfg.server_cmd:
        # No Server value yet, create a minimal one
        before = ""
        after = _ensure_server_has_flags("", ensure_rt=ensure_rt, ensure_priority=ensure_priority, cpu_cores=cpu_cores)
    else:
        before = cfg.server_cmd
        after = _ensure_server_has_flags(cfg.server_cmd, ensure_rt=ensure_rt, ensure_priority=ensure_priority, cpu_cores=cpu_cores)

    if before != after:
        write_config_with_server_update(path, cfg.def_preset, after)

    return (before, after)

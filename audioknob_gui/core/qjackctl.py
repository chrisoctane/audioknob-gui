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
    """Ensure command has -R (and optionally -P90) and optional taskset prefix.

    cpu_cores semantics:
    - None: keep any existing taskset prefix as-is
    - "":  remove any existing taskset prefix (no pinning)
    - other string: replace taskset prefix with this cpu list (e.g. "2,3" or "4-7")

    Preserves other prefixes like nice, ionice, chrt, etc.
    """
    parts = cmd.split()

    # Extract existing taskset prefix if present: "taskset -c <cores> ..."
    # We need to find it anywhere before jackd, not just at the start
    existing_taskset: str | None = None
    taskset_start_idx: int | None = None
    for i, tok in enumerate(parts):
        if tok == "taskset" and i + 2 < len(parts) and parts[i + 1] == "-c":
            existing_taskset = parts[i + 2]
            taskset_start_idx = i
            break

    # Find jackd/jackdmp/jackstart token position
    base = "jackd"
    jackd_idx: int | None = None
    for i, tok in enumerate(parts):
        if tok in ("jackd", "jackdmp", "jackstart"):
            jackd_idx = i
            base = tok
            break

    # Decide which pinning to use
    if cpu_cores is None:
        pin_cores = existing_taskset
    elif cpu_cores == "":
        pin_cores = None
    else:
        pin_cores = str(cpu_cores)

    # Build the prefix (everything before jackd, excluding any existing taskset)
    prefix: list[str] = []
    if jackd_idx is not None:
        for i in range(jackd_idx):
            # Skip existing taskset tokens if we found them
            if taskset_start_idx is not None and i in (taskset_start_idx, taskset_start_idx + 1, taskset_start_idx + 2):
                continue
            prefix.append(parts[i])

    # Build remainder args (everything after jackd)
    remainder = parts[jackd_idx + 1:] if jackd_idx is not None else []

    # Strip existing realtime/priority flags from remainder
    remainder = [p for p in remainder if not (p.startswith("-R") or p.startswith("-P"))]

    # Rebuild: optional taskset + preserved prefix + base + desired flags + remainder
    result: list[str] = []
    if pin_cores:
        result.extend(["taskset", "-c", pin_cores])
    result.extend(prefix)
    result.append(base)
    if ensure_rt:
        result.append("-R")
    if ensure_priority:
        result.append("-P90")
    result.extend(remainder)

    return " ".join(result)


def write_config_with_server_update(
    path: str | Path,
    preset: str,
    new_server_cmd: str,
) -> None:
    """Update the Server value for a preset, preserving the rest of the config."""
    cp = _read_config(path)
    if "Presets" not in cp:
        cp.add_section("Presets")
    cp.set("Presets", "DefPreset", preset)
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
    cp = _read_config(path)
    def_preset = _get_active_preset(cp)
    defaulted = False
    if not def_preset:
        def_preset = "default"
        defaulted = True

    server_cmd = _get_server_for_preset(cp, def_preset) if def_preset else None
    if not server_cmd:
        before = ""
        after = ensure_server_has_flags("", ensure_rt=ensure_rt, ensure_priority=ensure_priority, cpu_cores=cpu_cores)
    else:
        before = server_cmd
        after = ensure_server_has_flags(server_cmd, ensure_rt=ensure_rt, ensure_priority=ensure_priority, cpu_cores=cpu_cores)

    if before != after or defaulted:
        write_config_with_server_update(path, def_preset, after)

    return (before, after)

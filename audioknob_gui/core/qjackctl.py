from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_PRESET_KEY = "%28default%29"
_TASKSET_MASK_RE = re.compile(r"^(0x[0-9a-fA-F]+|[0-9]+)$")


@dataclass(frozen=True)
class QjackCtlConfig:
    def_preset: str
    server_cmd: str | None  # The Server value for the active preset
    server_prefix: str | None  # The ServerPrefix value for the active preset
    realtime: bool | None  # The Realtime value for the active preset
    priority: int | None  # The Priority value for the active preset
    server_config_enabled: bool
    server_config_name: str | None
    post_startup_enabled: bool
    post_startup_shell: str | None


def _read_config(path: str | Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    # Preserve case sensitivity
    cp.optionxform = str
    p = Path(path)
    if p.exists():
        cp.read(p, encoding="utf-8")
    return cp


def _ensure_combo_item(cp: configparser.ConfigParser, section: str, combo_key: str, value: str) -> None:
    if not value:
        return
    if section not in cp:
        cp.add_section(section)
    item_prefix = f"{combo_key}\\Item"
    max_idx = 0
    for key, val in cp.items(section):
        if not key.startswith(item_prefix):
            continue
        idx = key[len(item_prefix):]
        if idx.isdigit():
            max_idx = max(max_idx, int(idx))
        if str(val).strip() == value:
            return
    cp.set(section, f"{item_prefix}{max_idx + 1}", value)


def _ensure_preset_entry(cp: configparser.ConfigParser, preset: str) -> None:
    if not preset:
        return
    if "Presets" not in cp:
        cp.add_section("Presets")
    max_idx = 0
    for key, val in cp.items("Presets"):
        if key.startswith("Preset"):
            idx = key[len("Preset"):]
            if idx.isdigit():
                max_idx = max(max_idx, int(idx))
            if str(val).strip() == preset:
                return
    cp.set("Presets", f"Preset{max_idx + 1}", preset)


def _ensure_preset_settings(cp: configparser.ConfigParser, preset: str) -> None:
    if "Settings" not in cp:
        return
    for key, val in cp.items("Settings"):
        if "\\" in key:
            continue
        prefixed = f"{preset}\\{key}"
        if prefixed not in cp["Settings"]:
            cp.set("Settings", prefixed, val)


def _get_active_preset(cp: configparser.ConfigParser) -> str | None:
    if "Presets" not in cp:
        return None
    preset = cp.get("Presets", "DefPreset", fallback=None)
    if preset is None:
        return None
    preset = str(preset).strip()
    if preset == "(default)":
        return None
    return preset or None


def _get_server_for_preset(cp: configparser.ConfigParser, preset: str) -> str | None:
    if "Settings" not in cp:
        return None
    key = f"{preset}\\Server"
    return cp.get("Settings", key, fallback=None)


def _get_server_prefix_for_preset(cp: configparser.ConfigParser, preset: str) -> str | None:
    if "Settings" not in cp:
        return None
    key = f"{preset}\\ServerPrefix"
    return cp.get("Settings", key, fallback=None)


def _get_server_unscoped(cp: configparser.ConfigParser) -> str | None:
    if "Settings" not in cp:
        return None
    return cp.get("Settings", "Server", fallback=None)


def _get_server_prefix_unscoped(cp: configparser.ConfigParser) -> str | None:
    if "Settings" not in cp:
        return None
    return cp.get("Settings", "ServerPrefix", fallback=None)


def _parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except Exception:
        return None


def _get_realtime_for_preset(cp: configparser.ConfigParser, preset: str) -> bool | None:
    if "Settings" not in cp:
        return None
    key = f"{preset}\\Realtime"
    return _parse_bool(cp.get("Settings", key, fallback=None))


def _get_priority_for_preset(cp: configparser.ConfigParser, preset: str) -> int | None:
    if "Settings" not in cp:
        return None
    key = f"{preset}\\Priority"
    return _parse_int(cp.get("Settings", key, fallback=None))


def _get_realtime_unscoped(cp: configparser.ConfigParser) -> bool | None:
    if "Settings" not in cp:
        return None
    return _parse_bool(cp.get("Settings", "Realtime", fallback=None))


def _get_priority_unscoped(cp: configparser.ConfigParser) -> int | None:
    if "Settings" not in cp:
        return None
    return _parse_int(cp.get("Settings", "Priority", fallback=None))

def _get_server_config_enabled(cp: configparser.ConfigParser) -> bool:
    raw = None
    if "Options" in cp:
        raw = cp.get("Options", "ServerConfig", fallback=None)
    if raw is None and "Settings" in cp:
        raw = cp.get("Settings", "ServerConfig", fallback=None)
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _get_server_config_name(cp: configparser.ConfigParser) -> str | None:
    name = None
    if "Options" in cp:
        name = cp.get("Options", "ServerConfigName", fallback=None)
    if name is None and "Settings" in cp:
        name = cp.get("Settings", "ServerConfigName", fallback=None)
    if name is None:
        return None
    name = str(name).strip()
    return name or None


def _get_post_startup_enabled(cp: configparser.ConfigParser) -> bool:
    raw = None
    if "Options" in cp:
        raw = cp.get("Options", "PostStartupScript", fallback=None)
    if raw is None and "Settings" in cp:
        raw = cp.get("Settings", "PostStartupScript", fallback=None)
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _get_post_startup_shell(cp: configparser.ConfigParser) -> str | None:
    raw = None
    if "Options" in cp:
        raw = cp.get("Options", "PostStartupScriptShell", fallback=None)
    if raw is None and "Settings" in cp:
        raw = cp.get("Settings", "PostStartupScriptShell", fallback=None)
    if raw is None:
        return None
    raw = str(raw).strip()
    return raw or None


def resolve_server_config_path(name: str | None) -> Path | None:
    if not name:
        return None
    p = Path(name).expanduser()
    if not p.is_absolute():
        p = Path.home() / p
    return p


def default_post_start_script_path() -> Path:
    from audioknob_gui.core.paths import default_paths

    return Path(default_paths().user_state_dir) / "qjackctl-post-start.sh"


def build_post_start_script(cpu_list: str) -> str:
    cpu_list = normalize_cpu_cores(cpu_list)
    if not cpu_list:
        return ""
    lines = [
        "#!/bin/sh",
        "# Generated by audioknob-gui. Do not edit.",
        "set -eu",
        f'CPU_LIST="{cpu_list}"',
        'if command -v taskset >/dev/null 2>&1; then',
        '  if command -v pgrep >/dev/null 2>&1; then',
        '    PIDS="$(pgrep -x jackd || true)"',
        "  else",
        '    PIDS="$(ps -eo pid=,comm= | awk \'$2==\"jackd\"{print $1}\')"',
        "  fi",
        "  for pid in $PIDS; do",
        '    taskset -apc "$CPU_LIST" "$pid" >/dev/null 2>&1 || true',
        "  done",
        "fi",
        "",
    ]
    return "\n".join(lines)


def normalize_cpu_cores(cpu_cores: str | None) -> str | None:
    if cpu_cores is None:
        return None
    cores = str(cpu_cores).strip()
    if not cores:
        return ""
    return re.sub(r"\s+", "", cores)


def _mask_to_cpu_list(token: str) -> str | None:
    try:
        mask = int(str(token).strip(), 0)
    except Exception:
        return None
    if mask <= 0:
        return None
    cores: list[int] = []
    idx = 0
    while mask:
        if mask & 1:
            cores.append(idx)
        mask >>= 1
        idx += 1
    if not cores:
        return None
    return ",".join(str(x) for x in cores)


def _taskset_span(parts: list[str]) -> tuple[str | None, int | None, int | None]:
    existing_taskset: str | None = None
    taskset_start_idx: int | None = None
    taskset_end_idx: int | None = None
    for i, tok in enumerate(parts):
        if tok != "taskset":
            continue
        if i + 1 >= len(parts):
            continue
        if parts[i + 1] == "-c":
            if i + 2 >= len(parts):
                continue
            taskset_start_idx = i
            j = i + 2
            cpu_tokens: list[str] = []
            if j < len(parts):
                cpu_tokens.append(parts[j])
                j += 1
                while j < len(parts) and _CPU_TOKEN_RE.match(parts[j]):
                    cpu_tokens.append(parts[j])
                    j += 1
            taskset_end_idx = j
            if cpu_tokens and all(_CPU_TOKEN_RE.match(t) for t in cpu_tokens):
                existing_taskset = normalize_cpu_cores("".join(cpu_tokens))
            break
        mask_tok = parts[i + 1]
        if _TASKSET_MASK_RE.match(mask_tok):
            taskset_start_idx = i
            taskset_end_idx = i + 2
            existing_taskset = _mask_to_cpu_list(mask_tok)
            break
    return existing_taskset, taskset_start_idx, taskset_end_idx


def read_config(path: str | Path) -> QjackCtlConfig:
    cp = _read_config(path)
    def_preset = _get_active_preset(cp) or ""
    server_cmd = None
    server_prefix = None
    realtime = None
    priority = None
    if def_preset:
        server_cmd = _get_server_for_preset(cp, def_preset)
        server_prefix = _get_server_prefix_for_preset(cp, def_preset)
        realtime = _get_realtime_for_preset(cp, def_preset)
        priority = _get_priority_for_preset(cp, def_preset)
    else:
        server_cmd = _get_server_unscoped(cp)
        server_prefix = _get_server_prefix_unscoped(cp)
        realtime = _get_realtime_unscoped(cp)
        priority = _get_priority_unscoped(cp)
        if not server_cmd:
            server_cmd = _get_server_for_preset(cp, _DEFAULT_PRESET_KEY)
        if not server_prefix:
            server_prefix = _get_server_prefix_for_preset(cp, _DEFAULT_PRESET_KEY)
        if realtime is None:
            realtime = _get_realtime_for_preset(cp, _DEFAULT_PRESET_KEY)
        if priority is None:
            priority = _get_priority_for_preset(cp, _DEFAULT_PRESET_KEY)
    if not server_cmd and not server_prefix:
        server_cmd = _get_server_unscoped(cp)
        server_prefix = _get_server_prefix_unscoped(cp)
        if realtime is None:
            realtime = _get_realtime_unscoped(cp)
        if priority is None:
            priority = _get_priority_unscoped(cp)
    server_config_enabled = _get_server_config_enabled(cp)
    server_config_name = _get_server_config_name(cp)
    post_startup_enabled = _get_post_startup_enabled(cp)
    post_startup_shell = _get_post_startup_shell(cp)
    return QjackCtlConfig(
        def_preset=def_preset,
        server_cmd=server_cmd,
        server_prefix=server_prefix,
        realtime=realtime,
        priority=priority,
        server_config_enabled=server_config_enabled,
        server_config_name=server_config_name,
        post_startup_enabled=post_startup_enabled,
        post_startup_shell=post_startup_shell,
    )


def set_server_config_enabled(path: str | Path, enabled: bool) -> None:
    cp = _read_config(path)
    if "Options" not in cp:
        cp.add_section("Options")
    cp.set("Options", "ServerConfig", "true" if enabled else "false")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        cp.write(f, space_around_delimiters=False)


def ensure_server_has_flags(cmd: str, *, ensure_rt: bool = True, ensure_priority: bool = False, cpu_cores: str | None = None) -> str:
    """Ensure command has -R (and optionally -P90) and optional taskset prefix.

    cpu_cores semantics:
    - None: keep any existing taskset prefix as-is
    - "":  remove any existing taskset prefix (no pinning)
    - other string: replace taskset prefix with this cpu list (e.g. "2,3" or "4-7")

    Preserves other prefixes like nice, ionice, chrt, etc.
    """
    if cpu_cores is not None:
        cpu_cores = normalize_cpu_cores(cpu_cores)
    parts = cmd.split()

    # Extract existing taskset prefix if present: "taskset -c <cores> ..."
    # We need to find it anywhere before jackd, not just at the start.
    existing_taskset, taskset_start_idx, taskset_end_idx = _taskset_span(parts)

    # Find jackd/jackdmp/jackstart token position (accept absolute paths)
    base = "jackd"
    jackd_idx: int | None = None
    for i, tok in enumerate(parts):
        name = Path(tok).name
        if name in ("jackd", "jackdmp", "jackstart"):
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
            if (
                taskset_start_idx is not None
                and taskset_end_idx is not None
                and taskset_start_idx <= i < taskset_end_idx
            ):
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


def ensure_server_prefix(prefix: str | None, *, cpu_cores: str | None) -> str:
    """Update ServerPrefix to include (or remove) taskset pinning without adding jackd flags."""
    if prefix is None:
        prefix = ""
    if cpu_cores is None:
        return prefix
    cpu_cores = normalize_cpu_cores(cpu_cores)

    parts = prefix.split()
    _, taskset_start_idx, taskset_end_idx = _taskset_span(parts)
    cleaned: list[str] = []
    for i, tok in enumerate(parts):
        if (
            taskset_start_idx is not None
            and taskset_end_idx is not None
            and taskset_start_idx <= i < taskset_end_idx
        ):
            continue
        cleaned.append(tok)

    if cpu_cores == "":
        return " ".join(cleaned).strip()

    return " ".join(["taskset", "-c", str(cpu_cores), *cleaned]).strip()




def write_config_with_server_update(
    path: str | Path,
    preset: str | None,
    new_server_cmd: str,
    server_prefix: str | None = None,
    realtime: bool | None = None,
    priority: int | None = None,
    *,
    mirror_unscoped: bool = False,
    server_config_enabled: bool | None = None,
    post_startup_enabled: bool | None = None,
    post_startup_shell: str | None = None,
) -> None:
    """Update the Server value for a preset, preserving the rest of the config."""
    cp = _read_config(path)
    update_config(
        cp,
        preset=preset,
        new_server_cmd=new_server_cmd,
        server_prefix=server_prefix,
        realtime=realtime,
        priority=priority,
        mirror_unscoped=mirror_unscoped,
        server_config_enabled=server_config_enabled,
        post_startup_enabled=post_startup_enabled,
        post_startup_shell=post_startup_shell,
    )

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        cp.write(f, space_around_delimiters=False)


def update_config(
    cp: configparser.ConfigParser,
    *,
    preset: str | None,
    new_server_cmd: str,
    server_prefix: str | None = None,
    realtime: bool | None = None,
    priority: int | None = None,
    mirror_unscoped: bool = False,
    server_config_enabled: bool | None = None,
    post_startup_enabled: bool | None = None,
    post_startup_shell: str | None = None,
) -> None:
    if "Settings" not in cp:
        cp.add_section("Settings")
    use_preset = bool(preset)
    if use_preset:
        if "Presets" not in cp:
            cp.add_section("Presets")
        cp.set("Presets", "DefPreset", str(preset))
        _ensure_preset_entry(cp, str(preset))
        _ensure_preset_settings(cp, str(preset))
        key = f"{preset}\\Server"
        pkey = f"{preset}\\ServerPrefix"
        rkey = f"{preset}\\Realtime"
        prkey = f"{preset}\\Priority"
    else:
        key = "Server"
        pkey = "ServerPrefix"
        rkey = "Realtime"
        prkey = "Priority"
    cp.set("Settings", key, new_server_cmd)
    if server_prefix is not None:
        cp.set("Settings", pkey, server_prefix)
    if realtime is not None:
        cp.set("Settings", rkey, "true" if realtime else "false")
    if priority is not None:
        cp.set("Settings", prkey, str(priority))
    if use_preset and mirror_unscoped:
        cp.set("Settings", "Server", new_server_cmd)
        if server_prefix is not None:
            cp.set("Settings", "ServerPrefix", server_prefix)
        if realtime is not None:
            cp.set("Settings", "Realtime", "true" if realtime else "false")
        if priority is not None:
            cp.set("Settings", "Priority", str(priority))
    if server_prefix:
        _ensure_combo_item(cp, "History", "ServerPrefixComboBox", server_prefix)
    if server_config_enabled is not None:
        if "Options" not in cp:
            cp.add_section("Options")
        cp.set("Options", "ServerConfig", "true" if server_config_enabled else "false")
    if post_startup_enabled is not None:
        if "Options" not in cp:
            cp.add_section("Options")
        cp.set("Options", "PostStartupScript", "true" if post_startup_enabled else "false")
    if post_startup_shell is not None:
        if "Options" not in cp:
            cp.add_section("Options")
        cp.set("Options", "PostStartupScriptShell", post_startup_shell)


def ensure_server_flags(
    path: str | Path,
    *,
    ensure_rt: bool = True,
    ensure_priority: bool = False,
    cpu_cores: str | None = None,
    preset_name: str | None = None,
    use_realtime_settings: bool = True,
    mirror_unscoped: bool = False,
    server_config_enabled: bool | None = None,
    post_startup_enabled: bool | None = None,
    post_startup_shell: str | None = None,
) -> tuple[str, str]:
    """Read config, ensure Server command has required flags, return (before, after)."""
    cp = _read_config(path)
    actual_preset = _get_active_preset(cp) or ""
    target_preset = preset_name if preset_name is not None else actual_preset
    if target_preset is not None:
        target_preset = str(target_preset).strip()
    if not target_preset:
        target_preset = None
    use_preset = bool(target_preset)
    if use_preset:
        server_cmd = _get_server_for_preset(cp, target_preset)
        server_prefix = _get_server_prefix_for_preset(cp, target_preset)
    else:
        server_cmd = _get_server_unscoped(cp)
        server_prefix = _get_server_prefix_unscoped(cp)
    if not server_cmd:
        before = ""
        base_cmd = "jackd"
    else:
        before = server_cmd
        base_cmd = server_cmd

    strip_flags = use_realtime_settings and (ensure_rt or ensure_priority)
    after = ensure_server_has_flags(
        base_cmd,
        ensure_rt=not strip_flags and ensure_rt,
        ensure_priority=not strip_flags and ensure_priority,
        cpu_cores="" if cpu_cores is not None else None,
    )

    prefix_after = ensure_server_prefix(server_prefix, cpu_cores=cpu_cores)
    realtime = True if (use_realtime_settings and ensure_rt) else None
    priority = 90 if (use_realtime_settings and ensure_priority) else None

    force_preset = bool(preset_name) and (target_preset or "") != actual_preset
    if (
        before != after
        or prefix_after != (server_prefix or "")
        or force_preset
        or realtime is not None
        or priority is not None
        or server_config_enabled is not None
        or post_startup_enabled is not None
        or post_startup_shell is not None
    ):
        write_config_with_server_update(
            path,
            target_preset if use_preset else None,
            after,
            server_prefix=prefix_after,
            realtime=realtime,
            priority=priority,
            mirror_unscoped=mirror_unscoped,
            server_config_enabled=server_config_enabled,
            post_startup_enabled=post_startup_enabled,
            post_startup_shell=post_startup_shell,
        )

    return (before, after)
_CPU_TOKEN_RE = re.compile(r"^[0-9,\\-]+$")

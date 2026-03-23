from __future__ import annotations

import functools
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from audioknob_gui.core.runner import run
from audioknob_gui.knob_ids import POWER_PROFILE_PERFORMANCE


RECOMMENDED_SCX_SCHEDULER = "scx_bpfland"
SCX_SCHEDULER_ORDER = (
    "scx_bpfland",
    "scx_lavd",
    "scx_flash",
)
SCX_SERVICE_DROPIN_FILENAME = "99-audioknob-memlock.conf"
SCX_NON_SCHEDULER_NAMES = {
    "scx_loader",
    "scx_show_state",
    "scx_stats",
}
_SCX_NAME_RE = re.compile(r"^scx_[a-z0-9_]+$")
_SCX_SCHEDULER_RE = re.compile(r"^\s*SCX_SCHEDULER\s*=\s*(.+?)\s*$")
_SCX_FLAGS_RE = re.compile(r"^\s*SCX_FLAGS\s*=\s*(.*?)\s*$")
_MISSING = object()
_SCX_GOVERNOR_MANAGED_IDS = (
    POWER_PROFILE_PERFORMANCE,
    "cpu_governor_performance_persistent",
)


@dataclass(frozen=True)
class ScxFlagOption:
    label: str
    value: str
    description: str = ""


def normalize_scx_scheduler_name(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parts = shlex.split(text)
    except Exception:
        parts = text.split()
    if not parts:
        return None
    name = Path(parts[0]).name.strip()
    if not name or not _SCX_NAME_RE.fullmatch(name):
        return None
    return name


def normalize_scx_scheduler_or_ops(value: object) -> str | None:
    normalized = normalize_scx_scheduler_name(value)
    if normalized:
        return normalized
    ops = scx_ops_name(value)
    if not ops:
        return None
    candidate = f"scx_{ops}"
    return candidate if _SCX_NAME_RE.fullmatch(candidate) else None


def scx_ops_name(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parts = shlex.split(text)
    except Exception:
        parts = text.split()
    if not parts:
        return None
    name = Path(parts[0]).name.strip()
    if not name:
        return None
    if name.startswith("scx_") and _SCX_NAME_RE.fullmatch(name):
        return name[4:]
    if re.fullmatch(r"[a-z0-9_]+", name):
        return name
    return None


def list_available_scx_schedulers() -> list[str]:
    candidates: set[str] = set()
    for directory in _search_directories():
        try:
            entries = directory.iterdir()
        except Exception:
            continue
        for entry in entries:
            try:
                if not entry.is_file():
                    continue
            except Exception:
                continue
            name = entry.name.strip()
            if name in SCX_NON_SCHEDULER_NAMES:
                continue
            if not _SCX_NAME_RE.fullmatch(name):
                continue
            if os.access(entry, os.X_OK):
                candidates.add(name)
    return _sort_scx_names(candidates)


def preferred_scx_scheduler(available: Iterable[str]) -> str | None:
    available_set = {name for name in available if normalize_scx_scheduler_name(name)}
    for name in SCX_SCHEDULER_ORDER:
        if name in available_set:
            return name
    if not available_set:
        return None
    return _sort_scx_names(available_set)[0]


def read_scx_scheduler_config(path: str | Path) -> str | None:
    try:
        content = Path(path).read_text(encoding="utf-8")
    except Exception:
        return None
    for line in content.splitlines():
        match = _SCX_SCHEDULER_RE.match(line)
        if not match:
            continue
        return normalize_scx_scheduler_name(match.group(1))
    return None


def normalize_scx_flags(value: object) -> str | None:
    if value is None:
        return None
    parts = _split_scx_flags(value)
    if not parts:
        return ""
    return " ".join(parts)


def read_scx_flags_config(path: str | Path) -> str | None:
    try:
        content = Path(path).read_text(encoding="utf-8")
    except Exception:
        return None
    for line in content.splitlines():
        match = _SCX_FLAGS_RE.match(line)
        if not match:
            continue
        return normalize_scx_flags(match.group(1))
    return None


def scx_flags_reset_required(content: str, scheduler: str) -> bool:
    normalized = normalize_scx_scheduler_name(scheduler)
    if not normalized:
        return False

    configured_scheduler: str | None = None
    configured_flags: tuple[str, ...] = ()
    for line in content.splitlines():
        if configured_scheduler is None:
            match = _SCX_SCHEDULER_RE.match(line)
            if match:
                configured_scheduler = normalize_scx_scheduler_name(match.group(1))
                continue
        if not configured_flags:
            match = _SCX_FLAGS_RE.match(line)
            if match:
                configured_flags = _split_scx_flags(match.group(1))

    return bool(configured_flags) and configured_scheduler != normalized


def update_scx_scheduler_config(content: str, scheduler: str, flags: object = _MISSING) -> str:
    normalized = normalize_scx_scheduler_name(scheduler)
    if not normalized:
        return content

    explicit_flags = flags is not _MISSING
    normalized_flags = normalize_scx_flags(flags) if explicit_flags else None
    reset_flags = scx_flags_reset_required(content, normalized) if not explicit_flags else True
    out_lines: list[str] = []
    replaced = False
    flags_replaced = False
    for line in content.splitlines():
        if _SCX_SCHEDULER_RE.match(line):
            if not replaced:
                out_lines.append(f"SCX_SCHEDULER={normalized}")
                replaced = True
            continue
        if _SCX_FLAGS_RE.match(line):
            if reset_flags:
                if not flags_replaced:
                    out_lines.append(_format_scx_flags_line(normalized_flags or ""))
                    flags_replaced = True
                continue
        out_lines.append(line)

    if not replaced:
        if out_lines and out_lines[-1].strip():
            out_lines.append("")
        out_lines.append(f"SCX_SCHEDULER={normalized}")
    if reset_flags and not flags_replaced:
        out_lines.append(_format_scx_flags_line(normalized_flags or ""))

    return "\n".join(out_lines).rstrip("\n") + "\n"


def list_available_scx_flag_presets(scheduler: object) -> list[ScxFlagOption]:
    normalized = normalize_scx_scheduler_name(scheduler)
    if not normalized:
        return []
    return list(_scheduler_flag_options(normalized))


def read_sched_ext_status(root: str | Path = "/sys/kernel/sched_ext") -> tuple[str | None, str | None]:
    root_path = Path(root)
    if not root_path.exists():
        return None, None
    try:
        state = (root_path / "state").read_text(encoding="utf-8").strip() or None
    except Exception:
        state = None
    try:
        ops = (root_path / "root" / "ops").read_text(encoding="utf-8").strip() or None
    except Exception:
        ops = None
    return state, ops


def scx_service_dropin_path(unit: str = "scx.service", base: str | Path = "/etc/systemd/system") -> str:
    unit_name = str(unit).strip() or "scx.service"
    return str(Path(base) / f"{unit_name}.d" / SCX_SERVICE_DROPIN_FILENAME)


def scx_service_dropin_content() -> str:
    return "[Service]\nLimitMEMLOCK=infinity\n"


def scx_service_dropin_matches(unit: str = "scx.service", base: str | Path = "/etc/systemd/system") -> bool:
    path = Path(scx_service_dropin_path(unit, base))
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return False
    return content == scx_service_dropin_content()


def scx_managed_knob_ids(scheduler: object, flags: object = None) -> tuple[str, ...]:
    normalized = normalize_scx_scheduler_or_ops(scheduler)
    if not normalized:
        return ()
    flag_set = set(_split_scx_flags(flags))
    managed: set[str] = set()

    if normalized == "scx_lavd":
        if "--autopower" not in flag_set:
            managed.add(POWER_PROFILE_PERFORMANCE)
        if "--no-freq-scaling" not in flag_set:
            managed.add("cpu_governor_performance_persistent")
    elif "--cpufreq" in flag_set:
        managed.add("cpu_governor_performance_persistent")

    return tuple(sorted(managed))


def _search_directories() -> list[Path]:
    ordered: list[Path] = []
    seen: set[str] = set()
    raw_dirs = os.environ.get("PATH", "").split(os.pathsep)
    raw_dirs.extend(
        [
            "/usr/bin",
            "/usr/local/bin",
            "/bin",
            "/usr/sbin",
            "/usr/local/sbin",
            "/sbin",
        ]
    )
    for raw in raw_dirs:
        path = raw.strip()
        if not path or path in seen:
            continue
        seen.add(path)
        ordered.append(Path(path))
    return ordered


def _sort_scx_names(names: Iterable[str]) -> list[str]:
    normalized = {name for name in names if normalize_scx_scheduler_name(name)}
    priority = {name: idx for idx, name in enumerate(SCX_SCHEDULER_ORDER)}
    return sorted(normalized, key=lambda name: (priority.get(name, len(priority)), name))


def _split_scx_flags(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if not text:
        return ()
    try:
        parts = shlex.split(text)
    except Exception:
        parts = text.split()
    return tuple(part for part in parts if part)


def _format_scx_flags_line(value: str) -> str:
    normalized = normalize_scx_flags(value)
    if not normalized:
        return "SCX_FLAGS="
    return f"SCX_FLAGS={shlex.quote(normalized)}"


@functools.lru_cache(maxsize=32)
def _scheduler_flag_options(scheduler: str) -> tuple[ScxFlagOption, ...]:
    argv = [scheduler, "--help"]
    try:
        result = run(argv, timeout=5)
    except Exception:
        return ()
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if not text:
        return ()
    return tuple(_parse_scx_flag_options(text))


def _parse_scx_flag_options(help_text: str) -> list[ScxFlagOption]:
    blocks = _parse_help_option_blocks(help_text)
    seen: set[str] = set()
    options: list[ScxFlagOption] = []
    for header, description in blocks:
        if "<" in header or "[" in header and "<" in header:
            continue
        tokens = []
        for part in header.split(","):
            token = part.strip().split()[0].rstrip(",")
            if not token.startswith("-"):
                continue
            token = token.removesuffix("...")
            if token in ("-h", "--help", "-V", "--version"):
                continue
            tokens.append(token)
        if not tokens:
            continue
        long_flags = [token for token in tokens if token.startswith("--")]
        value = long_flags[0] if long_flags else tokens[0]
        if value in seen:
            continue
        seen.add(value)
        label = " / ".join(tokens)
        options.append(ScxFlagOption(label=label, value=value, description=description))
    return options


def _parse_help_option_blocks(help_text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    in_options = False
    current_header: str | None = None
    current_desc: list[str] = []
    for raw_line in help_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "Options:":
            in_options = True
            continue
        if not in_options:
            continue
        if stripped.startswith("-"):
            if current_header is not None:
                blocks.append((current_header, _compact_description(current_desc)))
            current_header = stripped
            current_desc = []
            continue
        if current_header is not None:
            current_desc.append(stripped)
    if current_header is not None:
        blocks.append((current_header, _compact_description(current_desc)))
    return blocks


def _compact_description(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip()).strip()
    if not text:
        return ""
    for sep in (". ", "; "):
        head, found, _tail = text.partition(sep)
        if found:
            return head + sep.strip()
    return text

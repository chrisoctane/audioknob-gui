from __future__ import annotations

from pathlib import Path
from typing import Iterable


_RAW_CONFLICTS: dict[str, list[str]] = {
    "power_profile_performance": [
        "cpu_governor_performance_persistent",
        "kernel_cstate_limit",
        "kernel_intel_idle_cstate_limit",
    ],
    "irq_pinning": [
        "irqbalance_disable",
    ],
    "pipewire_clock_constraints": [
        "pipewire_quantum",
        "pipewire_sample_rate",
    ],
    "pipewire_data_loop_affinity": [
        "kernel_isolcpus",
        "kernel_nohz_full",
        "kernel_rcu_nocbs",
        "kernel_irqaffinity",
        "irq_pinning",
    ],
}


def _build_conflict_map() -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for src, targets in _RAW_CONFLICTS.items():
        for target in targets:
            mapping.setdefault(src, set()).add(target)
            mapping.setdefault(target, set()).add(src)
    return mapping


CONFLICT_MAP = _build_conflict_map()

SECTION_MAP: dict[str, list[str]] = {
    "power_profile_performance": ["Power Profile (powerprofilesctl / tuned)"],
    "cpu_governor_performance_persistent": ["CPU Performance (persistent governor)"],
    "kernel_cstate_limit": ["CPU C-States / Intel C-States limiters"],
    "kernel_intel_idle_cstate_limit": ["CPU C-States / Intel C-States limiters"],
    "pipewire_clock_constraints": [
        "PipeWire Clock Constraints / Mlock / RT Module / Data Loops",
        "PipeWire Quantum / Sample Rate",
    ],
    "pipewire_quantum": ["PipeWire Quantum / Sample Rate"],
    "pipewire_sample_rate": ["PipeWire Quantum / Sample Rate"],
    "pipewire_data_loop_affinity": [
        "PipeWire Clock Constraints / Mlock / RT Module / Data Loops",
        "CPU isolation set (isolcpus / nohz_full / rcu_nocbs / irqaffinity)",
        "IRQ Pinning + IRQ Balance",
    ],
    "kernel_isolcpus": ["CPU isolation set (isolcpus / nohz_full / rcu_nocbs / irqaffinity)"],
    "kernel_nohz_full": ["CPU isolation set (isolcpus / nohz_full / rcu_nocbs / irqaffinity)"],
    "kernel_rcu_nocbs": ["CPU isolation set (isolcpus / nohz_full / rcu_nocbs / irqaffinity)"],
    "kernel_irqaffinity": [
        "CPU isolation set (isolcpus / nohz_full / rcu_nocbs / irqaffinity)",
        "IRQ Housekeeping + kernel irqaffinity",
    ],
    "irq_pinning": ["IRQ Pinning + IRQ Balance"],
    "irqbalance_disable": ["IRQ Pinning + IRQ Balance"],
}


def find_conflicts(
    queued_actions: dict[str, str],
    statuses: dict[str, str],
) -> dict[str, set[str]]:
    conflicts: dict[str, set[str]] = {}
    for src_id, action in queued_actions.items():
        if action != "apply":
            continue
        for other_id in CONFLICT_MAP.get(src_id, set()):
            other_action = queued_actions.get(other_id)
            if other_action == "reset":
                continue
            other_status = statuses.get(other_id, "unknown")
            if other_action == "apply" or other_status in (
                "applied",
                "pending_reboot",
                "running",
                "partial",
            ):
                conflicts.setdefault(src_id, set()).add(other_id)
    return conflicts


def active_conflicts(
    knob_id: str,
    queued_actions: dict[str, str],
    statuses: dict[str, str],
) -> set[str]:
    conflicts: set[str] = set()
    for other_id in CONFLICT_MAP.get(knob_id, set()):
        other_action = queued_actions.get(other_id)
        if other_action == "reset":
            continue
        other_status = statuses.get(other_id, "unknown")
        if other_action == "apply" or other_status in ("applied", "pending_reboot", "running", "partial"):
            conflicts.add(other_id)
    return conflicts


def _load_interactions_sections(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith("### "):
            current = line[4:].strip()
            sections[current] = []
            continue
        if current is None:
            continue
        sections[current].append(line)
    out: dict[str, str] = {}
    for title, body in sections.items():
        text = "\n".join(body).strip()
        out[title] = text
    return out


def build_conflict_details(
    conflict_ids: Iterable[str],
    *,
    interactions_path: Path,
) -> str:
    titles: list[str] = []
    for knob_id in conflict_ids:
        titles.extend(SECTION_MAP.get(knob_id, []))
    titles = list(dict.fromkeys(titles))
    if not titles:
        return "No detailed conflict notes found. See docs/KNOB_INTERACTIONS.md."
    sections = _load_interactions_sections(interactions_path)
    if not sections:
        return "Conflict details file not found. See docs/KNOB_INTERACTIONS.md."
    parts: list[str] = []
    for title in titles:
        body = sections.get(title, "").strip()
        if not body:
            continue
        parts.append(title)
        parts.append("-" * len(title))
        parts.append(body)
        parts.append("")
    return "\n".join(parts).strip() if parts else "No matching sections found."

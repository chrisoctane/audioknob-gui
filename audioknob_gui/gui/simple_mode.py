from __future__ import annotations

from dataclasses import dataclass


MIN_LEVEL = 0
MAX_LEVEL = 11
NON_QUEUE_KNOB_IDS: frozenset[str] = frozenset({"audio_group_membership"})


@dataclass(frozen=True)
class SimpleSetting:
    id: str
    title: str
    level: int
    queue_knob_ids: tuple[str, ...]


SIMPLE_SETTINGS: tuple[SimpleSetting, ...] = (
    SimpleSetting("audio_group_membership", "Audio Groups", 1, ("audio_group_membership",)),
    SimpleSetting("inotify_max_watches", "Inotify Watches", 2, ("inotify_max_watches",)),
    SimpleSetting("swappiness", "Swappiness", 3, ("swappiness",)),
    SimpleSetting("dirty_bytes", "Dirty Bytes", 4, ("dirty_bytes",)),
    SimpleSetting("usb_autosuspend_disable", "USB Power", 5, ("usb_autosuspend_disable",)),
    SimpleSetting("cpu_dma_latency_udev", "DMA Latency", 6, ("cpu_dma_latency_udev",)),
    SimpleSetting("power_profile_performance", "Power Profile", 7, ("power_profile_performance",)),
    SimpleSetting("realtime_clock_access", "Realtime Clock Access", 8, ("realtime_clock_access",)),
    SimpleSetting(
        "cpu_governor_performance_persistent",
        "CPU Performance (persistent)",
        9,
        ("cpu_governor_performance_persistent",),
    ),
    SimpleSetting(
        "pipewire_rt_setup",
        "Safety Latch: Safe RT Stack",
        10,
        (
            "rt_limits_audio_group",
            "pipewire_rt_limits_group",
            "pipewire_rt_module_tuning",
            "pipewire_mlock_policy",
        ),
    ),
    SimpleSetting(
        "safe_irq_stack",
        "Safety Latch: Safe IRQ Stack",
        11,
        (
            "kernel_threadirqs",
            "irqbalance_disable",
            "rtirq_enable",
        ),
    ),
)

# Stable ordering for queue rendering and deterministic serialization.
ORDERED_QUEUE_KNOBS: tuple[str, ...] = (
    "audio_group_membership",
    "inotify_max_watches",
    "swappiness",
    "dirty_bytes",
    "usb_autosuspend_disable",
    "cpu_dma_latency_udev",
    "power_profile_performance",
    "realtime_clock_access",
    "cpu_governor_performance_persistent",
    "rt_limits_audio_group",
    "pipewire_rt_limits_group",
    "pipewire_rt_module_tuning",
    "pipewire_mlock_policy",
    "kernel_threadirqs",
    "irqbalance_disable",
    "rtirq_enable",
)

SIMPLE_MANAGED_KNOB_IDS = frozenset(
    (set(ORDERED_QUEUE_KNOBS) - set(NON_QUEUE_KNOB_IDS))
    | {
        # Concept knob row that mirrors bundle status in full view.
        "pipewire_rt_setup",
    }
)


def clamp_level(value: object) -> int:
    try:
        level = int(value)
    except Exception:
        return MIN_LEVEL
    if level < MIN_LEVEL:
        return MIN_LEVEL
    if level > MAX_LEVEL:
        return MAX_LEVEL
    return level


def settings_for_level(level: int) -> list[SimpleSetting]:
    level = clamp_level(level)
    return [s for s in SIMPLE_SETTINGS if s.level <= level]


def compose_queue_ids(level: int, *, backend_is_tuned: bool) -> list[str]:
    selected = settings_for_level(level)
    selected_ids = {s.id for s in selected}
    queue_ids: set[str] = set()
    for setting in selected:
        queue_ids.update(setting.queue_knob_ids)

    # Hard dependency: RT limits require audio group membership.
    if "rt_limits_audio_group" in selected_ids:
        queue_ids.add("audio_group_membership")

    # Bundle dependency: RT setup always ensures group membership.
    if "pipewire_rt_setup" in selected_ids:
        queue_ids.add("audio_group_membership")

    # Conflict gate: tuned should own governor policy.
    if backend_is_tuned and "power_profile_performance" in queue_ids:
        queue_ids.discard("cpu_governor_performance_persistent")

    ordered = [kid for kid in ORDERED_QUEUE_KNOBS if kid in queue_ids]
    return ordered


def compose_queue_actions(
    level: int,
    *,
    backend_is_tuned: bool,
    managed_knob_ids: set[str] | list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    apply_ids = compose_queue_ids(level, backend_is_tuned=backend_is_tuned)
    actions: dict[str, str] = {kid: "apply" for kid in apply_ids}

    managed = {str(kid) for kid in (managed_knob_ids or ())}
    for kid in ORDERED_QUEUE_KNOBS:
        if kid in managed and kid not in actions:
            actions[kid] = "reset"
    return actions


def normalize_queue_actions(
    actions: dict[str, str],
    *,
    non_queue_knob_ids: set[str] | list[str] | tuple[str, ...] | None = None,
    skip_apply_knob_ids: set[str] | list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    """Drop non-queue kinds and already-applied apply actions."""
    non_queue = {str(kid) for kid in (non_queue_knob_ids or ())}
    skip_apply = {str(kid) for kid in (skip_apply_knob_ids or ())}
    out: dict[str, str] = {}
    for kid, action in actions.items():
        if action not in ("apply", "reset"):
            continue
        if kid in non_queue:
            continue
        if action == "apply" and kid in skip_apply:
            continue
        out[kid] = action
    return out


def apply_fixed_presets(state: dict, *, level: int) -> None:
    selected_ids = {s.id for s in settings_for_level(level)}

    if "power_profile_performance" in selected_ids:
        state["power_profile_backend"] = "auto"

    if "pipewire_rt_setup" in selected_ids:
        # Simple Safe RT preset: keep RTKit/portal paths, do not force
        # explicit module priority/time values.
        state["pipewire_limits_enabled"] = False
        state["pipewire_limits_group"] = "audio"
        state["pipewire_rt_prio"] = None
        state["pipewire_rt_time_soft"] = None
        state["pipewire_rt_time_hard"] = None
        state["pipewire_nice_level"] = None
        state["pipewire_rlimits_enabled"] = False
        state["pipewire_rtkit_enabled"] = True
        state["pipewire_rtportal_enabled"] = True
        state["pipewire_rt_setup_dirty"] = False

    if "pipewire_mlock_policy" in selected_ids or "pipewire_rt_setup" in selected_ids:
        state["pipewire_mlock_allow"] = True
        state["pipewire_mlock_all"] = False

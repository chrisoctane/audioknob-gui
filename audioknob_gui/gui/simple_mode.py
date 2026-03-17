from __future__ import annotations

from dataclasses import dataclass

from audioknob_gui.knob_ids import (
    AUDIO_GROUP_MEMBERSHIP,
    IRQBALANCE_DISABLE,
    PIPEWIRE_MLOCK_POLICY,
    PIPEWIRE_RT_LIMITS_GROUP,
    PIPEWIRE_RT_MODULE_TUNING,
    PIPEWIRE_RT_SETUP,
    POWER_PROFILE_PERFORMANCE,
    RT_LIMITS_AUDIO_GROUP,
)

MIN_LEVEL = 0
MAX_LEVEL = 11
NON_QUEUE_KNOB_IDS: frozenset[str] = frozenset({AUDIO_GROUP_MEMBERSHIP})
TUNED_MANAGED_QUEUE_KNOB_IDS: tuple[str, ...] = (
    "swappiness",
    "dirty_bytes",
    "cpu_governor_performance_persistent",
)


@dataclass(frozen=True)
class SimpleSetting:
    id: str
    title: str
    level: int
    queue_knob_ids: tuple[str, ...]


SIMPLE_SETTINGS: tuple[SimpleSetting, ...] = (
    SimpleSetting(AUDIO_GROUP_MEMBERSHIP, "Audio Groups", 1, (AUDIO_GROUP_MEMBERSHIP,)),
    SimpleSetting("inotify_max_watches", "Inotify Watches", 2, ("inotify_max_watches",)),
    SimpleSetting("swappiness", "Swappiness", 3, ("swappiness",)),
    SimpleSetting("dirty_bytes", "Dirty Bytes", 4, ("dirty_bytes",)),
    SimpleSetting("usb_autosuspend_disable", "USB Power", 5, ("usb_autosuspend_disable",)),
    SimpleSetting("cpu_dma_latency_udev", "DMA Latency", 6, ("cpu_dma_latency_udev",)),
    SimpleSetting(POWER_PROFILE_PERFORMANCE, "Power Profile", 7, (POWER_PROFILE_PERFORMANCE,)),
    SimpleSetting("realtime_clock_access", "Realtime Clock Access", 8, ("realtime_clock_access",)),
    SimpleSetting(
        "cpu_governor_performance_persistent",
        "CPU Performance (persistent)",
        9,
        ("cpu_governor_performance_persistent",),
    ),
    SimpleSetting(
        PIPEWIRE_RT_SETUP,
        "Safety Latch: Safe RT Stack",
        10,
        (
            RT_LIMITS_AUDIO_GROUP,
            PIPEWIRE_RT_LIMITS_GROUP,
            PIPEWIRE_RT_MODULE_TUNING,
            PIPEWIRE_MLOCK_POLICY,
        ),
    ),
    SimpleSetting(
        "safe_irq_stack",
        "Safety Latch: Safe IRQ Stack",
        11,
        (
            "kernel_threadirqs",
            IRQBALANCE_DISABLE,
            "rtirq_enable",
        ),
    ),
)

# Stable ordering for queue rendering and deterministic serialization.
ORDERED_QUEUE_KNOBS: tuple[str, ...] = (
    AUDIO_GROUP_MEMBERSHIP,
    "inotify_max_watches",
    "swappiness",
    "dirty_bytes",
    "usb_autosuspend_disable",
    "cpu_dma_latency_udev",
    POWER_PROFILE_PERFORMANCE,
    "realtime_clock_access",
    "cpu_governor_performance_persistent",
    RT_LIMITS_AUDIO_GROUP,
    PIPEWIRE_RT_LIMITS_GROUP,
    PIPEWIRE_RT_MODULE_TUNING,
    PIPEWIRE_MLOCK_POLICY,
    "kernel_threadirqs",
    IRQBALANCE_DISABLE,
    "rtirq_enable",
)

SIMPLE_MANAGED_KNOB_IDS = frozenset(
    (set(ORDERED_QUEUE_KNOBS) - set(NON_QUEUE_KNOB_IDS))
    | {
        # Concept knob row that mirrors bundle status in full view.
        PIPEWIRE_RT_SETUP,
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


def tuned_managed_queue_ids(
    level: int,
    *,
    backend_is_tuned: bool,
    tuned_owned_after_apply: bool = False,
) -> list[str]:
    selected_ids = {s.id for s in settings_for_level(level)}
    if not backend_is_tuned:
        return []
    if POWER_PROFILE_PERFORMANCE not in selected_ids and not tuned_owned_after_apply:
        return []
    return [kid for kid in ORDERED_QUEUE_KNOBS if kid in TUNED_MANAGED_QUEUE_KNOB_IDS]


def compose_requested_queue_ids(level: int) -> list[str]:
    selected = settings_for_level(level)
    selected_ids = {s.id for s in selected}
    queue_ids: set[str] = set()
    for setting in selected:
        queue_ids.update(setting.queue_knob_ids)

    # Hard dependency: RT limits require audio group membership.
    if RT_LIMITS_AUDIO_GROUP in selected_ids:
        queue_ids.add(AUDIO_GROUP_MEMBERSHIP)

    # Bundle dependency: RT setup always ensures group membership.
    if PIPEWIRE_RT_SETUP in selected_ids:
        queue_ids.add(AUDIO_GROUP_MEMBERSHIP)

    return [kid for kid in ORDERED_QUEUE_KNOBS if kid in queue_ids]


def compose_queue_ids(
    level: int,
    *,
    backend_is_tuned: bool,
    tuned_owned_after_apply: bool = False,
) -> list[str]:
    queue_ids = set(compose_requested_queue_ids(level))

    # Conflict gate: tuned should own governor/swappiness/dirty policy.
    for kid in tuned_managed_queue_ids(
        level,
        backend_is_tuned=backend_is_tuned,
        tuned_owned_after_apply=tuned_owned_after_apply,
    ):
        queue_ids.discard(kid)

    return [kid for kid in ORDERED_QUEUE_KNOBS if kid in queue_ids]


def compose_queue_actions(
    level: int,
    *,
    backend_is_tuned: bool,
    tuned_owned_after_apply: bool = False,
    managed_knob_ids: set[str] | list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    tuned_managed = set(
        tuned_managed_queue_ids(
            level,
            backend_is_tuned=backend_is_tuned,
            tuned_owned_after_apply=tuned_owned_after_apply,
        )
    )
    apply_ids = compose_queue_ids(
        level,
        backend_is_tuned=backend_is_tuned,
        tuned_owned_after_apply=tuned_owned_after_apply,
    )
    actions: dict[str, str] = {kid: "apply" for kid in apply_ids}

    managed = {str(kid) for kid in (managed_knob_ids or ())}
    for kid in ORDERED_QUEUE_KNOBS:
        if kid in managed and kid not in actions:
            if kid in tuned_managed:
                continue
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

    if POWER_PROFILE_PERFORMANCE in selected_ids:
        state["power_profile_backend"] = "auto"

    if PIPEWIRE_RT_SETUP in selected_ids:
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

    if PIPEWIRE_MLOCK_POLICY in selected_ids or PIPEWIRE_RT_SETUP in selected_ids:
        state["pipewire_mlock_allow"] = True
        state["pipewire_mlock_all"] = False

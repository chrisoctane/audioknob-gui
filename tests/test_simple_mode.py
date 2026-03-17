from __future__ import annotations

from audioknob_gui.gui import simple_mode


def test_clamp_level_bounds() -> None:
    assert simple_mode.clamp_level(None) == 0
    assert simple_mode.clamp_level(-5) == 0
    assert simple_mode.clamp_level(99) == 11
    assert simple_mode.clamp_level(7) == 7


def test_level_zero_queues_nothing() -> None:
    queue_ids = simple_mode.compose_queue_ids(0, backend_is_tuned=False)
    assert queue_ids == []


def test_compose_queue_includes_rt_bundle() -> None:
    queue_ids = simple_mode.compose_queue_ids(10, backend_is_tuned=False)
    assert "rt_limits_audio_group" in queue_ids
    assert "pipewire_rt_limits_group" in queue_ids
    assert "pipewire_rt_module_tuning" in queue_ids
    assert "pipewire_mlock_policy" in queue_ids
    assert "audio_group_membership" in queue_ids
    assert "kernel_threadirqs" not in queue_ids


def test_compose_queue_includes_realtime_clock_access_before_cpu_governor_tier() -> None:
    queue_ids = simple_mode.compose_queue_ids(8, backend_is_tuned=False)
    assert "realtime_clock_access" in queue_ids
    assert "cpu_governor_performance_persistent" not in queue_ids


def test_compose_queue_includes_safe_irq_stack_at_top_tier() -> None:
    queue_ids = simple_mode.compose_queue_ids(11, backend_is_tuned=False)
    assert "kernel_threadirqs" in queue_ids
    assert "irqbalance_disable" in queue_ids
    assert "rtirq_enable" in queue_ids


def test_compose_queue_skips_governor_when_tuned() -> None:
    queue_ids = simple_mode.compose_queue_ids(9, backend_is_tuned=True)
    assert "power_profile_performance" in queue_ids
    assert "cpu_governor_performance_persistent" not in queue_ids
    assert "swappiness" not in queue_ids
    assert "dirty_bytes" not in queue_ids


def test_tuned_managed_queue_ids_only_appear_with_power_profile_and_tuned() -> None:
    assert simple_mode.tuned_managed_queue_ids(6, backend_is_tuned=True) == []
    assert simple_mode.tuned_managed_queue_ids(9, backend_is_tuned=False) == []
    assert simple_mode.tuned_managed_queue_ids(9, backend_is_tuned=True) == [
        "swappiness",
        "dirty_bytes",
        "cpu_governor_performance_persistent",
    ]


def test_compose_queue_skips_tuned_managed_knobs_when_tuned_stays_active() -> None:
    queue_ids = simple_mode.compose_queue_ids(
        4,
        backend_is_tuned=True,
        tuned_owned_after_apply=True,
    )
    assert "swappiness" not in queue_ids
    assert "dirty_bytes" not in queue_ids


def test_compose_queue_actions_do_not_reset_tuned_managed_knobs_when_tuned_stays_active() -> None:
    actions = simple_mode.compose_queue_actions(
        4,
        backend_is_tuned=True,
        tuned_owned_after_apply=True,
        managed_knob_ids={
            "swappiness",
            "dirty_bytes",
            "cpu_governor_performance_persistent",
        },
    )
    assert "swappiness" not in actions
    assert "dirty_bytes" not in actions
    assert "cpu_governor_performance_persistent" not in actions


def test_compose_queue_actions_reapply_lower_tier_knobs_when_tuned_will_reset() -> None:
    actions = simple_mode.compose_queue_actions(
        4,
        backend_is_tuned=True,
        tuned_owned_after_apply=False,
        managed_knob_ids={
            "power_profile_performance",
            "swappiness",
            "dirty_bytes",
            "cpu_governor_performance_persistent",
        },
    )
    assert actions["power_profile_performance"] == "reset"
    assert actions["swappiness"] == "apply"
    assert actions["dirty_bytes"] == "apply"
    assert actions["cpu_governor_performance_persistent"] == "reset"


def test_apply_fixed_presets_sets_safe_rt_and_mlock() -> None:
    state: dict = {}
    simple_mode.apply_fixed_presets(state, level=10)
    assert state["power_profile_backend"] == "auto"
    assert state["pipewire_limits_enabled"] is False
    assert state["pipewire_limits_group"] == "audio"
    assert state["pipewire_rlimits_enabled"] is False
    assert state["pipewire_rtkit_enabled"] is True
    assert state["pipewire_rtportal_enabled"] is True
    assert state["pipewire_mlock_allow"] is True
    assert state["pipewire_mlock_all"] is False


def test_compose_queue_actions_adds_resets_for_managed_knobs_when_level_drops() -> None:
    actions = simple_mode.compose_queue_actions(
        9,
        backend_is_tuned=False,
        managed_knob_ids={"rt_limits_audio_group", "pipewire_rt_module_tuning", "kernel_threadirqs"},
    )
    assert actions.get("rt_limits_audio_group") == "reset"
    assert actions.get("pipewire_rt_module_tuning") == "reset"
    assert actions.get("kernel_threadirqs") == "reset"
    assert actions.get("cpu_governor_performance_persistent") == "apply"


def test_simple_managed_knobs_exclude_group_membership() -> None:
    assert "audio_group_membership" not in simple_mode.SIMPLE_MANAGED_KNOB_IDS


def test_normalize_queue_actions_drops_non_queue_and_already_applied() -> None:
    raw_actions = {
        "audio_group_membership": "apply",
        "inotify_max_watches": "apply",
        "cpu_dma_latency_udev": "apply",
        "swappiness": "reset",
    }
    normalized = simple_mode.normalize_queue_actions(
        raw_actions,
        non_queue_knob_ids={"audio_group_membership"},
        skip_apply_knob_ids={"cpu_dma_latency_udev"},
    )
    assert normalized == {
        "inotify_max_watches": "apply",
        "swappiness": "reset",
    }

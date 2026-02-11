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
    assert "pipewire_rt_limits_group" in queue_ids
    assert "pipewire_rt_module_tuning" in queue_ids
    assert "pipewire_mlock_policy" in queue_ids
    assert "audio_group_membership" in queue_ids
    assert "kernel_threadirqs" not in queue_ids


def test_compose_queue_skips_governor_when_tuned() -> None:
    queue_ids = simple_mode.compose_queue_ids(9, backend_is_tuned=True)
    assert "power_profile_performance" in queue_ids
    assert "cpu_governor_performance_persistent" not in queue_ids


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

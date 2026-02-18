"""Tests for conflict participant filtering."""

from audioknob_gui.gui.conflicts import (
    active_conflicts,
    filtered_active_conflicts,
    find_conflicts,
    is_conflict_participant,
    prune_power_profile_conflicts,
)


def test_is_conflict_participant_requires_active_or_apply() -> None:
    assert is_conflict_participant("not_applied", None) is False
    assert is_conflict_participant("sys_default", None) is False
    assert is_conflict_participant("applied", None) is True
    assert is_conflict_participant("partial", None) is True


def test_is_conflict_participant_respects_queued_actions() -> None:
    assert is_conflict_participant("not_applied", "apply") is True
    assert is_conflict_participant("applied", "reset") is False


def test_filtered_active_conflicts_requires_source_participation() -> None:
    statuses = {
        "power_profile_performance": "sys_default",
        "cpu_governor_performance_persistent": "partial",
    }
    queued = {}
    assert (
        filtered_active_conflicts("power_profile_performance", queued, statuses, state={}) == set()
    )


def test_filtered_active_conflicts_accepts_queued_source() -> None:
    statuses = {
        "pipewire_sample_rate": "not_applied",
        "pipewire_clock_constraints": "applied",
    }
    queued = {"pipewire_sample_rate": "apply"}
    assert filtered_active_conflicts("pipewire_sample_rate", queued, statuses, state={}) == {
        "pipewire_clock_constraints"
    }


def test_prune_power_profile_conflicts_when_not_tuned() -> None:
    conflict_ids = {"power_profile_performance", "kernel_cstate_limit"}
    assert (
        prune_power_profile_conflicts(
            "cpu_governor_performance_persistent",
            conflict_ids,
            backend_is_tuned=False,
        )
        == {"kernel_cstate_limit"}
    )
    assert (
        prune_power_profile_conflicts(
            "power_profile_performance",
            conflict_ids,
            backend_is_tuned=False,
        )
        == set()
    )


def test_audio_isolation_conflicts_detect_only_audio_role_mismatch() -> None:
    statuses = {
        "kernel_isolcpus": "applied",
        "kernel_nohz_full": "applied",
        "kernel_rcu_nocbs": "applied",
    }
    queued = {}
    state = {
        "kernel_isolcpus_cores": [2, 3],
        "kernel_nohz_full_cores": [4, 5],
        "kernel_rcu_nocbs_cores": [2, 3],
    }

    conflicts = filtered_active_conflicts("kernel_isolcpus", queued, statuses, state=state)
    assert "kernel_nohz_full" in conflicts
    assert "kernel_rcu_nocbs" not in conflicts


def test_irq_housekeeping_does_not_conflict_with_audio_isolation_inverse() -> None:
    statuses = {
        "kernel_irqaffinity": "applied",
        "kernel_isolcpus": "applied",
        "kernel_nohz_full": "applied",
        "kernel_rcu_nocbs": "applied",
    }
    queued = {}
    state = {
        "kernel_irqaffinity_cores": [0, 1],
        "kernel_isolcpus_cores": [2, 3],
        "kernel_nohz_full_cores": [2, 3],
        "kernel_rcu_nocbs_cores": [2, 3],
    }

    assert active_conflicts("kernel_irqaffinity", queued, statuses, state=state) == set()
    assert filtered_active_conflicts("kernel_irqaffinity", queued, statuses, state=state) == set()
    assert find_conflicts({"kernel_irqaffinity": "apply"}, statuses, state=state) == {}

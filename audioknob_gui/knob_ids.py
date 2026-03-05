"""
String constants for knob IDs.

These match the ``id`` field in ``config/registry.json``.  Using constants
instead of bare string literals prevents silent typo bugs and makes
grep/rename operations trivial.
"""

from __future__ import annotations

# Permissions / groups
AUDIO_GROUP_MEMBERSHIP = "audio_group_membership"
RT_LIMITS_AUDIO_GROUP = "rt_limits_audio_group"

# IRQ
IRQBALANCE_DISABLE = "irqbalance_disable"
IRQ_PINNING = "irq_pinning"

# Power
POWER_PROFILE_PERFORMANCE = "power_profile_performance"

# Kernel cmdline — CPU isolation / tickless / IRQ affinity
KERNEL_ISOLCPUS = "kernel_isolcpus"
KERNEL_NOHZ_FULL = "kernel_nohz_full"
KERNEL_RCU_NOCBS = "kernel_rcu_nocbs"
KERNEL_IRQAFFINITY = "kernel_irqaffinity"

# PipeWire
PIPEWIRE_QUANTUM = "pipewire_quantum"
PIPEWIRE_RT_SETUP = "pipewire_rt_setup"
PIPEWIRE_RT_LIMITS_GROUP = "pipewire_rt_limits_group"
PIPEWIRE_RT_MODULE_TUNING = "pipewire_rt_module_tuning"
PIPEWIRE_MLOCK_POLICY = "pipewire_mlock_policy"
PIPEWIRE_PULSE_APP_RULES = "pipewire_pulse_app_rules"

# Testing / monitoring
ALSA_XRUN_MONITOR = "alsa_xrun_monitor"

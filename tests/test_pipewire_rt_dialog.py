from __future__ import annotations

from audioknob_gui.gui.dialogs.pipewire import (
    PIPEWIRE_RT_FULL_LIMITS,
    PIPEWIRE_RT_FULL_MODULE,
    PIPEWIRE_RT_SAFE_LIMITS,
    PIPEWIRE_RT_SAFE_MODULE,
    infer_pipewire_rt_preset,
)


def test_infer_pipewire_rt_preset_detects_full_rt() -> None:
    assert infer_pipewire_rt_preset(PIPEWIRE_RT_FULL_LIMITS, PIPEWIRE_RT_FULL_MODULE) == "full_rt"


def test_infer_pipewire_rt_preset_detects_safe_rt() -> None:
    limits = dict(PIPEWIRE_RT_SAFE_LIMITS)
    limits["group"] = "audio"
    assert infer_pipewire_rt_preset(limits, PIPEWIRE_RT_SAFE_MODULE) == "safe_rt"


def test_infer_pipewire_rt_preset_detects_custom_values() -> None:
    custom_module = dict(PIPEWIRE_RT_FULL_MODULE)
    custom_module["rt_prio"] = 90
    assert infer_pipewire_rt_preset(PIPEWIRE_RT_FULL_LIMITS, custom_module) == "custom"

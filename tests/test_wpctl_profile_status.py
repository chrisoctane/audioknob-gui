"""Tests for wpctl_profile status detection."""

from dataclasses import replace
from typing import Callable


def _pro_audio_knob(device_id: str = "42"):
    from audioknob_gui.registry import load_registry

    reg = load_registry("config/registry.json")
    knob = next(k for k in reg if k.id == "pipewire_pro_audio_profile")
    params = dict(knob.impl.params)
    params["device_id"] = device_id
    return replace(knob, impl=replace(knob.impl, params=params))


def _patch_commands(monkeypatch, *, has_pactl: bool = True) -> None:
    import audioknob_gui.platform.packages as packages

    def fake_which_command(name: str) -> str | None:
        if name == "wpctl":
            return "wpctl"
        if name == "pactl":
            return "pactl" if has_pactl else None
        return None

    monkeypatch.setattr(packages, "which_command", fake_which_command)


def _patch_subprocess_run(monkeypatch, fn: Callable[[list[str]], tuple[int, str, str]]) -> None:
    import subprocess

    def fake_run(argv, **_kwargs):
        rc, out, err = fn([str(x) for x in argv])
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr=err)

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_wpctl_profile_status_applied_with_space_name(monkeypatch) -> None:
    """Detect applied state when current profile is displayed as 'Pro Audio'."""
    from audioknob_gui.worker import ops

    _patch_commands(monkeypatch, has_pactl=False)

    inspect_out = """
device.name = "alsa_card.pci-0000_01_00.1"
Profiles:
  1. Analog Stereo
  2. Pro Audio
Active Profile: Pro Audio
"""

    def fake_cmd(argv: list[str]) -> tuple[int, str, str]:
        if argv[:2] == ["wpctl", "inspect"]:
            return 0, inspect_out, ""
        raise AssertionError(f"unexpected command: {argv}")

    _patch_subprocess_run(monkeypatch, fake_cmd)
    assert ops.check_knob_status(_pro_audio_knob()) == "applied"


def test_wpctl_profile_status_applied_with_pactl_hyphen_fallback(monkeypatch) -> None:
    """Fallback to pactl should detect 'pro-audio' and mark applied."""
    from audioknob_gui.worker import ops

    _patch_commands(monkeypatch, has_pactl=True)

    inspect_out = """
device.name = "alsa_card.usb-My_Interface-00"
"""
    pactl_out = """
Card #33
    Name: alsa_card.usb-My_Interface-00
    Profiles:
        analog-stereo: Analog Stereo Output
        pro-audio: Pro Audio
    Active Profile: pro-audio
"""

    def fake_cmd(argv: list[str]) -> tuple[int, str, str]:
        if argv[:2] == ["wpctl", "inspect"]:
            return 0, inspect_out, ""
        if argv[:3] == ["pactl", "list", "cards"]:
            return 0, pactl_out, ""
        raise AssertionError(f"unexpected command: {argv}")

    _patch_subprocess_run(monkeypatch, fake_cmd)
    assert ops.check_knob_status(_pro_audio_knob()) == "applied"


def test_wpctl_profile_status_not_applied_when_pro_available_but_inactive(monkeypatch) -> None:
    """If Pro Audio exists but another profile is active, status is not_applied."""
    from audioknob_gui.worker import ops

    _patch_commands(monkeypatch, has_pactl=False)

    inspect_out = """
device.name = "alsa_card.pci-0000_01_00.1"
Profiles:
  1. Analog Stereo
  2. Pro Audio
Active Profile: Analog Stereo
"""

    def fake_cmd(argv: list[str]) -> tuple[int, str, str]:
        if argv[:2] == ["wpctl", "inspect"]:
            return 0, inspect_out, ""
        raise AssertionError(f"unexpected command: {argv}")

    _patch_subprocess_run(monkeypatch, fake_cmd)
    assert ops.check_knob_status(_pro_audio_knob()) == "not_applied"


def test_wpctl_profile_status_not_applicable_when_no_pro_profile(monkeypatch) -> None:
    """If no Pro Audio profile exists, status is not_applicable."""
    from audioknob_gui.worker import ops

    _patch_commands(monkeypatch, has_pactl=False)

    inspect_out = """
device.name = "alsa_card.pci-0000_01_00.1"
Profiles:
  1. Analog Stereo
Active Profile: Analog Stereo
"""

    def fake_cmd(argv: list[str]) -> tuple[int, str, str]:
        if argv[:2] == ["wpctl", "inspect"]:
            return 0, inspect_out, ""
        raise AssertionError(f"unexpected command: {argv}")

    _patch_subprocess_run(monkeypatch, fake_cmd)
    assert ops.check_knob_status(_pro_audio_knob()) == "not_applicable"

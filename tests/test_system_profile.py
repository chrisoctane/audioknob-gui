"""Tests for system profile path mapping."""

from pathlib import Path

from audioknob_gui.registry import load_registry
from audioknob_gui.worker.ops import DistroInfo, build_knob_paths


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_real_registry():
    registry_path = _repo_root() / "config" / "registry.json"
    return load_registry(str(registry_path))


def _sample_paths() -> dict[str, str]:
    return {
        "kernel_cmdline_file": "/etc/default/grub",
        "cpupower_config": "/etc/default/cpufrequtils",
        "rtirq_config": "/etc/default/rtirq",
        "pipewire_user_conf_dir": "/home/test/.config/pipewire/pipewire.conf.d",
        "pipewire_system_conf_dir": "/etc/pipewire/pipewire.conf.d",
        "qjackctl_config": "/home/test/.config/rncbc.org/QjackCtl.conf",
        "limits_dir": "/etc/security/limits.d",
        "sysctl_dir": "/etc/sysctl.d",
        "udev_rules_dir": "/etc/udev/rules.d",
    }


def _sample_distro(paths: dict[str, str]) -> DistroInfo:
    return DistroInfo(
        distro_id="ubuntu",
        boot_system="grub2",
        kernel_cmdline_file=paths["kernel_cmdline_file"],
        kernel_cmdline_update_cmd=["update-grub"],
    )


def test_build_knob_paths_covers_all_knobs() -> None:
    knobs = _load_real_registry()
    paths = _sample_paths()
    distro = _sample_distro(paths)

    knob_paths = build_knob_paths(paths=paths, distro=distro, knobs=knobs)

    assert set(k.id for k in knobs) == set(knob_paths.keys())

    for knob in knobs:
        entry = knob_paths[knob.id]
        assert entry["kind"] == (knob.impl.kind if knob.impl else "none")
        if knob.impl is None:
            continue
        targets = entry["targets"]
        assert isinstance(targets, list)
        assert targets, f"{knob.id} has no targets"


def test_build_knob_paths_user_service_mask() -> None:
    knobs = _load_real_registry()
    paths = _sample_paths()
    distro = _sample_distro(paths)

    knob_paths = build_knob_paths(paths=paths, distro=distro, knobs=knobs)
    entry = knob_paths["disable_tracker"]
    targets = entry["targets"]
    assert targets
    assert targets[0]["type"] == "user_services"
    values = targets[0]["value"]
    assert "tracker-miner-fs.service" in values

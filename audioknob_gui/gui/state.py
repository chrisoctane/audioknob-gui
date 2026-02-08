from __future__ import annotations

import json
import os
from pathlib import Path


def _state_path() -> Path:
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        d = Path(xdg_state) / "audioknob-gui"
    else:
        d = Path.home() / ".local" / "state" / "audioknob-gui"
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.json"


def load_state() -> dict:
    p = _state_path()
    default = {
        "schema": 1,
        "last_txid": None,
        "last_user_txid": None,
        "last_root_txid": None,
        "font_size": 11,
        "queued_knobs": [],
        "queued_actions": {},
        # Per-knob UI state
        "qjackctl_cpu_cores": None,  # list[int] or None
        "kernel_isolcpus_cores": None,  # list[int] or None
        "kernel_nohz_full_cores": None,  # list[int] or None
        "kernel_rcu_nocbs_cores": None,  # list[int] or None
        "kernel_irqaffinity_cores": None,  # list[int] or None
        "irq_housekeeping_auto": True,  # bool
        "irq_pinning_devices": [],  # list[str]
        "irq_pinning_cpu_cores": None,  # list[int] or None
        "audio_core_plan_count": 4,  # int
        "audio_core_plan_expanded": True,  # bool
        "view_tab": "all",  # str
        "advanced_mode_enabled": False,  # bool
        "show_technical_columns": False,  # bool (Req/Risk/CLI)
        "pipewire_quantum": None,  # int (32..1024) or None
        "pipewire_sample_rate": None,  # int (44100/48000/88200/96000/192000) or None
        "pipewire_clock_allowed_rates": None,  # list[int] | None
        "pipewire_clock_min_quantum": None,  # int | None
        "pipewire_clock_max_quantum": None,  # int | None
        "pipewire_clock_quantum_limit": None,  # int | None
        "pipewire_clock_quantum_floor": None,  # int | None
        "pipewire_clock_power_of_two": None,  # bool | None
        "pipewire_mlock_allow": None,  # bool | None
        "pipewire_mlock_all": None,  # bool | None
        "pipewire_limits_group": None,  # str | None
        "pipewire_limits_enabled": True,  # bool
        "pipewire_rt_prio": None,  # int | None
        "pipewire_rt_time_soft": None,  # int | None
        "pipewire_rt_time_hard": None,  # int | None
        "pipewire_nice_level": None,  # int | None
        "pipewire_rlimits_enabled": None,  # bool | None
        "pipewire_rtkit_enabled": None,  # bool | None
        "pipewire_rtportal_enabled": None,  # bool | None
        "pipewire_num_data_loops": None,  # int | None
        "pipewire_data_loops": None,  # list[dict] | None
        "wireplumber_alsa_period_size": None,  # int | None
        "wireplumber_alsa_period_num": None,  # int | None
        "wireplumber_alsa_headroom": None,  # int | None
        "wireplumber_alsa_disable_batch": None,  # bool | None
        "pipewire_pro_audio_device_id": None,  # str | int | None
        "power_profile_backend": "auto",  # auto | powerprofilesctl | tuned
        "jitter_test_last": None,  # dict payload from last run or None
        "system_profile": None,  # dict from startup scan or None
        "baseline_statuses": {},  # knob_id -> status string (first-run baseline)
        "baseline_checks": {},  # knob_id -> list[str] lines (first-run snapshot)
        "baseline_captured_at": None,  # ISO timestamp
        "baseline_txid_user": None,  # last_user_txid at capture time
        "baseline_txid_root": None,  # last_root_txid at capture time
        "baseline_source": "initial",  # initial | capture | import
        "baseline_config": {},  # per-knob config snapshot for baseline restore
        "baseline_profile": None,  # system_profile captured with baseline snapshot
        "baseline_import_path": None,  # last imported baseline path
        "baseline_preimport_path": None,  # last pre-import backup path
        "factory_statuses": {},  # knob_id -> status string (factory defaults)
        "factory_checks": {},  # knob_id -> list[str] lines (factory snapshot)
        "factory_captured_at": None,  # ISO timestamp
        "factory_source": None,  # capture | import | None
        "factory_config": {},  # per-knob config snapshot for factory restore
        "factory_profile": None,  # system_profile captured with factory snapshot
        "factory_import_path": None,  # last imported factory path
        "factory_preimport_path": None,  # last pre-import backup path
    }
    if not p.exists():
        return default
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # Migrate old state format
        if "last_txid" in data and "last_user_txid" not in data:
            data["last_root_txid"] = data.get("last_txid")
            data["last_user_txid"] = None
        if "font_size" not in data:
            data["font_size"] = 11
        if "qjackctl_cpu_cores" not in data:
            data["qjackctl_cpu_cores"] = None
        if "kernel_isolcpus_cores" not in data:
            data["kernel_isolcpus_cores"] = None
        if "kernel_nohz_full_cores" not in data:
            data["kernel_nohz_full_cores"] = None
        if "kernel_rcu_nocbs_cores" not in data:
            data["kernel_rcu_nocbs_cores"] = None
        if "kernel_irqaffinity_cores" not in data:
            data["kernel_irqaffinity_cores"] = None
        if "irq_housekeeping_auto" not in data:
            manual = data.get("kernel_irqaffinity_cores")
            has_manual = isinstance(manual, list) and any(isinstance(x, int) for x in manual)
            data["irq_housekeeping_auto"] = not has_manual
        if "irq_pinning_devices" not in data:
            data["irq_pinning_devices"] = []
        if "irq_pinning_cpu_cores" not in data:
            data["irq_pinning_cpu_cores"] = None
        if "audio_core_plan_count" not in data:
            data["audio_core_plan_count"] = 4
        if "audio_core_plan_expanded" not in data:
            data["audio_core_plan_expanded"] = True
        if "view_tab" not in data:
            data["view_tab"] = "all"
        if "advanced_mode_enabled" not in data:
            data["advanced_mode_enabled"] = bool(data.get("audio_session_enabled", False))
        if "show_technical_columns" not in data:
            data["show_technical_columns"] = False
        data.pop("audio_session_enabled", None)
        data.pop("audio_session_knobs", None)
        if "pipewire_quantum" not in data:
            data["pipewire_quantum"] = None
        if "pipewire_sample_rate" not in data:
            data["pipewire_sample_rate"] = None
        if "pipewire_clock_allowed_rates" not in data:
            data["pipewire_clock_allowed_rates"] = None
        if "pipewire_clock_min_quantum" not in data:
            data["pipewire_clock_min_quantum"] = None
        if "pipewire_clock_max_quantum" not in data:
            data["pipewire_clock_max_quantum"] = None
        if "pipewire_clock_quantum_limit" not in data:
            data["pipewire_clock_quantum_limit"] = None
        if "pipewire_clock_quantum_floor" not in data:
            data["pipewire_clock_quantum_floor"] = None
        if "pipewire_clock_power_of_two" not in data:
            data["pipewire_clock_power_of_two"] = None
        if "pipewire_mlock_allow" not in data:
            data["pipewire_mlock_allow"] = None
        if "pipewire_mlock_all" not in data:
            data["pipewire_mlock_all"] = None
        if "pipewire_limits_group" not in data:
            data["pipewire_limits_group"] = None
        if "pipewire_limits_enabled" not in data:
            data["pipewire_limits_enabled"] = True
        if "pipewire_rt_prio" not in data:
            data["pipewire_rt_prio"] = None
        if "pipewire_rt_time_soft" not in data:
            data["pipewire_rt_time_soft"] = None
        if "pipewire_rt_time_hard" not in data:
            data["pipewire_rt_time_hard"] = None
        if "pipewire_nice_level" not in data:
            data["pipewire_nice_level"] = None
        if "pipewire_rlimits_enabled" not in data:
            data["pipewire_rlimits_enabled"] = None
        if "pipewire_rtkit_enabled" not in data:
            data["pipewire_rtkit_enabled"] = None
        if "pipewire_rtportal_enabled" not in data:
            data["pipewire_rtportal_enabled"] = None
        if "pipewire_num_data_loops" not in data:
            data["pipewire_num_data_loops"] = None
        if "pipewire_data_loops" not in data:
            data["pipewire_data_loops"] = None
        if "wireplumber_alsa_period_size" not in data:
            data["wireplumber_alsa_period_size"] = None
        if "wireplumber_alsa_period_num" not in data:
            data["wireplumber_alsa_period_num"] = None
        if "wireplumber_alsa_headroom" not in data:
            data["wireplumber_alsa_headroom"] = None
        if "wireplumber_alsa_disable_batch" not in data:
            data["wireplumber_alsa_disable_batch"] = None
        if "pipewire_pro_audio_device_id" not in data:
            data["pipewire_pro_audio_device_id"] = None
        if "power_profile_backend" not in data:
            data["power_profile_backend"] = "auto"
        if "jitter_test_last" not in data:
            data["jitter_test_last"] = None
        if "system_profile" not in data:
            data["system_profile"] = None
        if "baseline_statuses" not in data:
            data["baseline_statuses"] = {}
        if "baseline_checks" not in data:
            data["baseline_checks"] = {}
        if "baseline_captured_at" not in data:
            data["baseline_captured_at"] = None
        if "baseline_txid_user" not in data:
            data["baseline_txid_user"] = None
        if "baseline_txid_root" not in data:
            data["baseline_txid_root"] = None
        if "baseline_source" not in data:
            data["baseline_source"] = "initial"
        if "baseline_config" not in data:
            data["baseline_config"] = {}
        if "baseline_profile" not in data:
            data["baseline_profile"] = None
        if "baseline_import_path" not in data:
            data["baseline_import_path"] = None
        if "baseline_preimport_path" not in data:
            data["baseline_preimport_path"] = None
        if "factory_statuses" not in data:
            data["factory_statuses"] = {}
        if "factory_checks" not in data:
            data["factory_checks"] = {}
        if "factory_captured_at" not in data:
            data["factory_captured_at"] = None
        if "factory_source" not in data:
            data["factory_source"] = None
        if "factory_config" not in data:
            data["factory_config"] = {}
        if "factory_profile" not in data:
            data["factory_profile"] = None
        if "factory_import_path" not in data:
            data["factory_import_path"] = None
        if "factory_preimport_path" not in data:
            data["factory_preimport_path"] = None
        if "enable_reboot_knobs" not in data:
            data["enable_reboot_knobs"] = False
        if "queued_knobs" not in data:
            data["queued_knobs"] = []
        if "queued_actions" not in data:
            if isinstance(data.get("queued_knobs"), list):
                data["queued_actions"] = {
                    k: "apply" for k in data["queued_knobs"] if isinstance(k, str)
                }
            else:
                data["queued_actions"] = {}
        if not isinstance(data.get("queued_knobs"), list):
            data["queued_knobs"] = []
        else:
            data["queued_knobs"] = [x for x in data["queued_knobs"] if isinstance(x, str)]
        if not isinstance(data.get("queued_actions"), dict):
            data["queued_actions"] = {}
        else:
            cleaned = {}
            for k, v in data["queued_actions"].items():
                if isinstance(k, str) and v in ("apply", "reset"):
                    cleaned[k] = v
            data["queued_actions"] = cleaned
        if data.get("jitter_test_last") is not None and not isinstance(data.get("jitter_test_last"), dict):
            data["jitter_test_last"] = None
        if data.get("irq_pinning_devices") is not None and not isinstance(data.get("irq_pinning_devices"), list):
            data["irq_pinning_devices"] = []
        else:
            data["irq_pinning_devices"] = [
                str(x) for x in data.get("irq_pinning_devices", []) if isinstance(x, (str, int))
            ]
        if data.get("irq_pinning_cpu_cores") is not None and not isinstance(data.get("irq_pinning_cpu_cores"), list):
            data["irq_pinning_cpu_cores"] = None
        else:
            cores = data.get("irq_pinning_cpu_cores")
            if isinstance(cores, list) and all(isinstance(x, int) for x in cores):
                data["irq_pinning_cpu_cores"] = cores
            else:
                data["irq_pinning_cpu_cores"] = None
        if data.get("audio_core_plan_count") is not None and not isinstance(data.get("audio_core_plan_count"), int):
            data["audio_core_plan_count"] = 4
        if data.get("view_tab") not in ("all", "cores", "dev"):
            data["view_tab"] = "all"
        for key in (
            "kernel_isolcpus_cores",
            "kernel_nohz_full_cores",
            "kernel_rcu_nocbs_cores",
            "kernel_irqaffinity_cores",
        ):
            if data.get(key) is not None and not isinstance(data.get(key), list):
                data[key] = None
            else:
                cores = data.get(key)
                if isinstance(cores, list) and all(isinstance(x, int) for x in cores):
                    data[key] = cores
                else:
                    data[key] = None
        if data.get("advanced_mode_enabled") is not None and not isinstance(data.get("advanced_mode_enabled"), bool):
            data["advanced_mode_enabled"] = False
        if data.get("show_technical_columns") is not None and not isinstance(
            data.get("show_technical_columns"), bool
        ):
            data["show_technical_columns"] = False
        if data.get("irq_housekeeping_auto") is not None and not isinstance(data.get("irq_housekeeping_auto"), bool):
            data["irq_housekeeping_auto"] = True
        if data.get("system_profile") is not None and not isinstance(data.get("system_profile"), dict):
            data["system_profile"] = None
        if data.get("baseline_statuses") is not None and not isinstance(data.get("baseline_statuses"), dict):
            data["baseline_statuses"] = {}
        if data.get("baseline_checks") is not None and not isinstance(data.get("baseline_checks"), dict):
            data["baseline_checks"] = {}
        if data.get("baseline_txid_user") is not None and not isinstance(data.get("baseline_txid_user"), str):
            data["baseline_txid_user"] = None
        if data.get("baseline_txid_root") is not None and not isinstance(data.get("baseline_txid_root"), str):
            data["baseline_txid_root"] = None
        if data.get("baseline_source") is not None and not isinstance(data.get("baseline_source"), str):
            data["baseline_source"] = "initial"
        if data.get("baseline_source") not in ("initial", "capture", "import"):
            data["baseline_source"] = "initial"
        if data.get("baseline_config") is not None and not isinstance(data.get("baseline_config"), dict):
            data["baseline_config"] = {}
        if data.get("baseline_profile") is not None and not isinstance(data.get("baseline_profile"), dict):
            data["baseline_profile"] = None
        if data.get("baseline_import_path") is not None and not isinstance(data.get("baseline_import_path"), str):
            data["baseline_import_path"] = None
        if data.get("baseline_preimport_path") is not None and not isinstance(data.get("baseline_preimport_path"), str):
            data["baseline_preimport_path"] = None
        if data.get("factory_profile") is not None and not isinstance(data.get("factory_profile"), dict):
            data["factory_profile"] = None
        if data.get("factory_import_path") is not None and not isinstance(data.get("factory_import_path"), str):
            data["factory_import_path"] = None
        if data.get("factory_preimport_path") is not None and not isinstance(data.get("factory_preimport_path"), str):
            data["factory_preimport_path"] = None
        # Sanitize known UI config values (can be corrupted by older bugs / manual edits).
        try:
            q = data.get("pipewire_quantum")
            qv = int(q) if q is not None else None
            if qv not in (32, 64, 128, 256, 512, 1024):
                data["pipewire_quantum"] = None
        except Exception:
            data["pipewire_quantum"] = None
        try:
            r = data.get("pipewire_sample_rate")
            rv = int(r) if r is not None else None
            if rv not in (44100, 48000, 88200, 96000, 192000):
                data["pipewire_sample_rate"] = None
        except Exception:
            data["pipewire_sample_rate"] = None
        # PipeWire advanced settings
        rates_raw = data.get("pipewire_clock_allowed_rates")
        if rates_raw is not None:
            if not isinstance(rates_raw, list):
                data["pipewire_clock_allowed_rates"] = None
            else:
                rates: list[int] = []
                for item in rates_raw:
                    try:
                        rates.append(int(item))
                    except Exception:
                        continue
                data["pipewire_clock_allowed_rates"] = rates or None
        for key in (
            "pipewire_clock_min_quantum",
            "pipewire_clock_max_quantum",
            "pipewire_clock_quantum_limit",
            "pipewire_clock_quantum_floor",
            "pipewire_rt_prio",
            "pipewire_rt_time_soft",
            "pipewire_rt_time_hard",
            "pipewire_nice_level",
            "pipewire_num_data_loops",
            "wireplumber_alsa_period_size",
            "wireplumber_alsa_period_num",
            "wireplumber_alsa_headroom",
        ):
            raw = data.get(key)
            if raw is None:
                continue
            try:
                data[key] = int(raw)
            except Exception:
                data[key] = None
        for key in (
            "pipewire_clock_power_of_two",
            "pipewire_mlock_allow",
            "pipewire_mlock_all",
            "pipewire_rlimits_enabled",
            "pipewire_rtkit_enabled",
            "pipewire_rtportal_enabled",
            "wireplumber_alsa_disable_batch",
        ):
            raw = data.get(key)
            if raw is not None and not isinstance(raw, bool):
                data[key] = None
        group = data.get("pipewire_limits_group")
        if group is not None and not isinstance(group, str):
            data["pipewire_limits_group"] = None
        if data.get("pipewire_limits_enabled") is not None and not isinstance(
            data.get("pipewire_limits_enabled"), bool
        ):
            data["pipewire_limits_enabled"] = True
        loops = data.get("pipewire_data_loops")
        if loops is not None and not (isinstance(loops, list) and all(isinstance(x, dict) for x in loops)):
            data["pipewire_data_loops"] = None
        device_id = data.get("pipewire_pro_audio_device_id")
        if device_id is not None and not isinstance(device_id, (str, int)):
            data["pipewire_pro_audio_device_id"] = None
        backend = str(data.get("power_profile_backend") or "").strip().lower()
        if backend not in ("auto", "powerprofilesctl", "tuned"):
            data["power_profile_backend"] = "auto"
        return data
    except Exception:
        return default


def save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

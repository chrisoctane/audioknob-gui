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
        "pipewire_quantum": None,  # int (32..1024) or None
        "pipewire_sample_rate": None,  # int (44100/48000/88200/96000/192000) or None
        "power_profile_backend": "auto",  # auto | powerprofilesctl | tuned
        "jitter_test_last": None,  # dict payload from last run or None
        "system_profile": None,  # dict from startup scan or None
        "baseline_statuses": {},  # knob_id -> status string (first-run baseline)
        "baseline_checks": {},  # knob_id -> list[str] lines (first-run snapshot)
        "baseline_captured_at": None,  # ISO timestamp
        "baseline_txid_user": None,  # last_user_txid at capture time
        "baseline_txid_root": None,  # last_root_txid at capture time
        "baseline_source": "initial",  # initial | capture | import
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
        data.pop("audio_session_enabled", None)
        data.pop("audio_session_knobs", None)
        if "pipewire_quantum" not in data:
            data["pipewire_quantum"] = None
        if "pipewire_sample_rate" not in data:
            data["pipewire_sample_rate"] = None
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
        if data.get("view_tab") not in ("all", "cores"):
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
        backend = str(data.get("power_profile_backend") or "").strip().lower()
        if backend not in ("auto", "powerprofilesctl", "tuned"):
            data["power_profile_backend"] = "auto"
        return data
    except Exception:
        return default


def save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

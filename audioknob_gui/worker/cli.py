from __future__ import annotations

import argparse
import json
import logging
import os
import pwd
import shlex
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from audioknob_gui.core.paths import default_paths
from audioknob_gui.core.audit import log_audit_event
from audioknob_gui.core.transaction import (
    RESET_BACKUP,
    RESET_DELETE,
    RESET_PACKAGE,
    backup_file,
    list_transactions,
    new_tx,
    reset_file_to_default,
    restore_file,
    write_manifest,
)
from audioknob_gui.knob_ids import (
    KERNEL_IRQAFFINITY,
    PIPEWIRE_MLOCK_POLICY,
    PIPEWIRE_PULSE_APP_RULES,
    PIPEWIRE_RT_LIMITS_GROUP,
    PIPEWIRE_RT_MODULE_TUNING,
    PIPEWIRE_RT_SETUP,
    POWER_PROFILE_PERFORMANCE,
)
from audioknob_gui.platform.detect import dump_detect
from audioknob_gui.registry import load_registry
from audioknob_gui.worker.ops import (
    apply_jackd_affinity,
    check_knob_status,
    preview,
    restore_irq_affinity,
    restore_sysfs,
    resolve_user_services,
)
import audioknob_gui.worker.ops as worker_ops


def _setup_worker_logging() -> logging.Logger:
    is_root = os.geteuid() == 0
    paths = default_paths()
    base = Path(paths.var_lib_dir) if is_root else Path(paths.user_state_dir)
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "worker.log"

    logger = logging.getLogger("audioknob.worker")
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    logger.info("start euid=%s argv=%s", os.geteuid(), " ".join(sys.argv))
    return logger


def _log_audit_event(action: str, payload: dict[str, Any]) -> None:
    logger = logging.getLogger("audioknob.worker")
    log_audit_event(logger, action, payload)


def _require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("This command must run as root (use pkexec).")


def _registry_default_path() -> str:
    from audioknob_gui.core.paths import get_registry_path
    return get_registry_path()


def _load_gui_state() -> dict:
    """Best-effort load of GUI state.json (user-scope)."""
    candidates: list[Path] = []
    env_state = os.environ.get("AUDIOKNOB_STATE_DIR")
    if env_state:
        candidates.append(Path(env_state))

    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        candidates.append(Path(xdg_state) / "audioknob-gui")

    paths = default_paths()
    candidates.append(Path(paths.user_state_dir))

    if os.geteuid() == 0:
        uid = None
        for key in ("PKEXEC_UID", "SUDO_UID"):
            raw = os.environ.get(key, "")
            if raw.isdigit():
                uid = int(raw)
                break
        if uid is None:
            user = os.environ.get("SUDO_USER") or os.environ.get("PKEXEC_USER")
            if user:
                try:
                    uid = pwd.getpwnam(user).pw_uid
                except KeyError:
                    uid = None
        if uid is not None:
            try:
                home = pwd.getpwuid(uid).pw_dir
            except KeyError:
                home = None
            if home:
                candidates.insert(0, Path(home) / ".local" / "state" / "audioknob-gui")

    seen: set[str] = set()
    for base in candidates:
        key = str(base)
        if key in seen:
            continue
        seen.add(key)
        p = base / "state.json"
        try:
            if not p.exists():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            continue
    return {}


def _is_qjackctl_running() -> bool:
    if shutil.which("pgrep"):
        for name in ("qjackctl", "qjackctl6"):
            r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
            if r.returncode == 0:
                return True
    r = subprocess.run(["ps", "-eo", "comm"], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    for line in r.stdout.splitlines():
        cmd = line.strip()
        if cmd in ("qjackctl", "qjackctl6"):
            return True
    return False


def _qjackctl_cpu_cores_override(state: dict) -> str | None:
    """Return comma-separated cpu list for taskset, or None if unset."""
    raw = state.get("qjackctl_cpu_cores")
    if raw is None:
        return None
    if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
        if not raw:
            # Explicitly configured as "no pinning"
            return ""
        return ",".join(str(int(x)) for x in raw)
    return None


def _pipewire_quantum_override(state: dict) -> int | None:
    """Return selected PipeWire quantum (buffer size), or None if unset/invalid."""
    raw = state.get("pipewire_quantum")
    if raw is None:
        return None
    try:
        v = int(raw)
    except Exception:
        return None
    if v in (32, 64, 128, 256, 512, 1024):
        return v
    return None


def _pipewire_sample_rate_override(state: dict) -> int | None:
    """Return selected PipeWire sample rate, or None if unset/invalid."""
    raw = state.get("pipewire_sample_rate")
    if raw is None:
        return None
    try:
        v = int(raw)
    except Exception:
        return None
    if v in (44100, 48000, 88200, 96000, 192000):
        return v
    return None


def _state_int(state: dict, key: str) -> int | None:
    raw = state.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _state_bool(state: dict, key: str) -> bool | None:
    raw = state.get(key)
    if isinstance(raw, bool):
        return raw
    return None


def _state_int_list(state: dict, key: str) -> list[int] | None:
    raw = state.get(key)
    if not isinstance(raw, list):
        return None
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except Exception:
            continue
    return out or None


def _state_cpu_list(state: dict, key: str) -> str | None:
    cores = _state_int_list(state, key)
    if not cores:
        return None
    try:
        from audioknob_gui.core.irq import cpu_list_from_cores

        return cpu_list_from_cores(cores)
    except Exception:
        return None


def _pipewire_clock_constraints_override(state: dict) -> dict[str, Any]:
    props: dict[str, Any] = {}
    allowed_rates = _state_int_list(state, "pipewire_clock_allowed_rates")
    if allowed_rates:
        props["default.clock.allowed-rates"] = allowed_rates
    min_q = _state_int(state, "pipewire_clock_min_quantum")
    if min_q is not None:
        props["default.clock.min-quantum"] = min_q
    max_q = _state_int(state, "pipewire_clock_max_quantum")
    if max_q is not None:
        props["default.clock.max-quantum"] = max_q
    q_limit = _state_int(state, "pipewire_clock_quantum_limit")
    if q_limit is not None:
        props["default.clock.quantum-limit"] = q_limit
    q_floor = _state_int(state, "pipewire_clock_quantum_floor")
    if q_floor is not None:
        props["default.clock.quantum-floor"] = q_floor
    pow2 = _state_bool(state, "pipewire_clock_power_of_two")
    if pow2 is not None:
        props["clock.power-of-two-quantum"] = pow2
    return props


def _pipewire_mlock_override(state: dict) -> dict[str, Any]:
    props: dict[str, Any] = {}
    allow = _state_bool(state, "pipewire_mlock_allow")
    if allow is not None:
        props["mem.allow-mlock"] = allow
    mlock_all = _state_bool(state, "pipewire_mlock_all")
    if mlock_all is not None:
        props["mem.mlock-all"] = mlock_all
    return props


def _pipewire_rt_module_override(state: dict) -> dict[str, Any]:
    args: dict[str, Any] = {}
    rt_prio = _state_int(state, "pipewire_rt_prio")
    if rt_prio is not None:
        args["rt.prio"] = rt_prio
    rt_soft = _state_int(state, "pipewire_rt_time_soft")
    if rt_soft is not None:
        args["rt.time.soft"] = rt_soft
    rt_hard = _state_int(state, "pipewire_rt_time_hard")
    if rt_hard is not None:
        args["rt.time.hard"] = rt_hard
    nice_level = _state_int(state, "pipewire_nice_level")
    if nice_level is not None:
        args["nice.level"] = nice_level
    rlimits = _state_bool(state, "pipewire_rlimits_enabled")
    if rlimits is not None:
        args["rlimits.enabled"] = rlimits
    rtkit = _state_bool(state, "pipewire_rtkit_enabled")
    if rtkit is not None:
        args["rtkit.enabled"] = rtkit
    rtportal = _state_bool(state, "pipewire_rtportal_enabled")
    if rtportal is not None:
        args["rtportal.enabled"] = rtportal
    uclamp_min = _state_int(state, "pipewire_uclamp_min")
    if uclamp_min is not None:
        args["uclamp.min"] = uclamp_min
    uclamp_max = _state_int(state, "pipewire_uclamp_max")
    if uclamp_max is not None:
        args["uclamp.max"] = uclamp_max
    zero_denormals = _state_bool(state, "pipewire_cpu_zero_denormals")
    if zero_denormals is not None:
        args["cpu.zero.denormals"] = zero_denormals
    return args


def _pipewire_pulse_latency_override(state: dict) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for prop, state_key in (
        ("pulse.min.req", "pipewire_pulse_min_req"),
        ("pulse.default.req", "pipewire_pulse_default_req"),
        ("pulse.min.quantum", "pipewire_pulse_min_quantum"),
    ):
        raw = state.get(state_key)
        if isinstance(raw, str) and raw.strip():
            props[prop] = raw.strip()
    return props


def _pipewire_pulse_rules_override(state: dict) -> list[dict[str, Any]]:
    profiles = state.get(PIPEWIRE_PULSE_APP_RULES)
    if not isinstance(profiles, list):
        return []
    rules: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        match_raw = profile.get("match")
        if not isinstance(match_raw, dict):
            continue
        match = {str(k): v for k, v in match_raw.items() if isinstance(k, str) and v is not None}
        if not match:
            continue
        latency = profile.get("latency")
        if not (isinstance(latency, str) and latency.strip()):
            continue
        props: dict[str, Any] = {"pulse.min.req": latency.strip()}
        default_req = profile.get("default_req")
        if isinstance(default_req, str) and default_req.strip():
            props["pulse.default.req"] = default_req.strip()
        min_quantum = profile.get("min_quantum")
        if isinstance(min_quantum, str) and min_quantum.strip():
            props["pulse.min.quantum"] = min_quantum.strip()
        rule = {
            "matches": [match],
            "actions": {"update-props": props},
        }
        rules.append(rule)
    return rules


def _pipewire_data_loops_override(state: dict) -> dict[str, Any]:
    context: dict[str, Any] = {}
    num_loops = _state_int(state, "pipewire_num_data_loops")
    if num_loops is not None:
        context["num-data-loops"] = num_loops
    loops = state.get("pipewire_data_loops")
    if isinstance(loops, list) and all(isinstance(x, dict) for x in loops):
        context["data-loops"] = loops
    return context


def _wireplumber_alsa_override(state: dict) -> dict[str, Any]:
    props: dict[str, Any] = {}
    period_size = _state_int(state, "wireplumber_alsa_period_size")
    if period_size is not None:
        props["api.alsa.period-size"] = period_size
    period_num = _state_int(state, "wireplumber_alsa_period_num")
    if period_num is not None:
        props["api.alsa.period-num"] = period_num
    headroom = _state_int(state, "wireplumber_alsa_headroom")
    if headroom is not None:
        props["api.alsa.headroom"] = headroom
    disable_batch = _state_bool(state, "wireplumber_alsa_disable_batch")
    if disable_batch is not None:
        props["api.alsa.disable-batch"] = disable_batch
    return props


def _pipewire_limits_group_override(state: dict) -> str | None:
    raw = state.get("pipewire_limits_group")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _systemd_service_policy(state: dict, prefix: str) -> str:
    raw = str(state.get(f"{prefix}_policy") or "").strip().lower()
    if raw in ("fifo", "rr", "other"):
        return raw
    return "fifo"


def _systemd_service_priority(state: dict, prefix: str, *, fallback: int) -> int:
    value = _state_int(state, f"{prefix}_priority")
    if value is None:
        return fallback
    return max(1, min(99, value))


def _systemd_service_lines(state: dict, prefix: str, *, fallback_prio: int) -> list[str]:
    policy = _systemd_service_policy(state, prefix)
    prio = _systemd_service_priority(state, prefix, fallback=fallback_prio)
    lines = [
        "[Service]",
        f"CPUSchedulingPolicy={policy}",
    ]
    if policy in ("fifo", "rr"):
        lines.append(f"CPUSchedulingPriority={prio}")
    cpu_list = _state_cpu_list(state, f"{prefix}_cpus")
    if cpu_list:
        lines.append(f"CPUAffinity={cpu_list.replace(',', ' ')}")
    return lines


def _user_slice_allowed_cpus_lines(state: dict) -> list[str]:
    lines = ["[Slice]"]
    cpu_list = _state_cpu_list(state, "cgroup_user_slice_allowed_cores")
    if cpu_list:
        lines.append(f"AllowedCPUs={cpu_list.replace(',', ' ')}")
    lines.append("CPUWeight=100")
    return lines


def _resolve_existing_group(preferred: str | None, candidates: list[str]) -> str | None:
    try:
        import grp
    except Exception:
        return preferred or (candidates[0] if candidates else None)
    seen: set[str] = set()
    for name in [preferred, *candidates]:
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            grp.getgrnam(name)
            return name
        except KeyError:
            continue
        except Exception:
            break
    return preferred or (candidates[0] if candidates else None)


def _rewrite_limits_lines(lines: list[str], group: str) -> list[str]:
    out: list[str] = []
    for line in lines:
        raw = str(line).strip()
        if not raw:
            continue
        parts = raw.split()
        if parts and parts[0].startswith("@"):
            parts[0] = f"@{group}"
            out.append(" ".join(parts))
        else:
            out.append(raw)
    return out


def _pipewire_pro_audio_device_override(state: dict) -> str | None:
    raw = state.get("pipewire_pro_audio_device_id")
    if raw is None:
        return None
    try:
        return str(int(raw))
    except Exception:
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _apply_pipewire_state_overrides(kid: str, params: dict[str, Any], state: dict) -> dict[str, Any]:
    new_params = dict(params)
    if kid == "pipewire_quantum":
        quantum = _pipewire_quantum_override(state)
        if quantum is not None:
            new_params["quantum"] = quantum
    elif kid == "pipewire_sample_rate":
        rate = _pipewire_sample_rate_override(state)
        if rate is not None:
            new_params["rate"] = rate
    elif kid == "pipewire_clock_constraints":
        props = dict(new_params.get("properties") or {})
        props.update(_pipewire_clock_constraints_override(state))
        new_params["properties"] = props
    elif kid == PIPEWIRE_MLOCK_POLICY:
        props = dict(new_params.get("properties") or {})
        props.update(_pipewire_mlock_override(state))
        new_params["properties"] = props
    elif kid == "pipewire_pulse_latency":
        props = dict(new_params.get("properties") or {})
        props.update(_pipewire_pulse_latency_override(state))
        new_params["properties"] = props
        new_params["properties_section"] = "pulse.properties"
    elif kid == PIPEWIRE_PULSE_APP_RULES:
        rules = _pipewire_pulse_rules_override(state)
        if rules:
            new_params["rules"] = rules
        new_params["rules_section"] = "pulse.rules"
    elif kid == PIPEWIRE_RT_MODULE_TUNING:
        args = dict(new_params.get("module_rt_args") or {})
        args.update(_pipewire_rt_module_override(state))
        new_params["module_rt_args"] = args
    elif kid == "pipewire_data_loop_affinity":
        context = dict(new_params.get("context") or {})
        context.update(_pipewire_data_loops_override(state))
        new_params["context"] = context
    elif kid == "wireplumber_alsa_usb_tuning":
        props = dict(new_params.get("props") or {})
        props.update(_wireplumber_alsa_override(state))
        new_params["props"] = props
    elif kid == PIPEWIRE_RT_LIMITS_GROUP:
        group = _pipewire_limits_group_override(state) or str(new_params.get("group") or "").strip() or None
        group = _resolve_existing_group(group, ["pipewire", "audio", "realtime"])
        if group:
            new_params["group"] = group
            base_lines = [str(x) for x in new_params.get("lines", [])]
            new_params["lines"] = _rewrite_limits_lines(base_lines, group)
    elif kid == "pipewire_pro_audio_profile":
        device_id = _pipewire_pro_audio_device_override(state)
        if device_id:
            new_params["device_id"] = device_id
    return new_params


def _power_profile_backend_override(state: dict) -> str | None:
    raw = str(state.get("power_profile_backend") or "").strip().lower()
    if raw in ("auto", "powerprofilesctl", "tuned"):
        return raw
    return None


def _irq_pinning_override(state: dict) -> tuple[list[str] | None, str | None]:
    devices_raw = state.get("irq_pinning_devices")
    devices: list[str] | None = None
    if isinstance(devices_raw, list):
        devices = [str(x) for x in devices_raw if isinstance(x, (str, int)) and str(x).strip()]

    cores_raw = state.get("irq_pinning_cpu_cores")
    cpu_list: str | None = None
    if isinstance(cores_raw, list) and all(isinstance(x, int) for x in cores_raw):
        from audioknob_gui.core.irq import cpu_list_from_cores

        cpu_list = cpu_list_from_cores(cores_raw)
    return devices, cpu_list


def _state_int_list_with_presence(state: dict, key: str) -> tuple[list[int] | None, bool]:
    raw = state.get(key)
    if raw is None:
        return None, False
    if not isinstance(raw, list):
        return None, False
    out: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            return None, False
        try:
            out.append(int(item))
        except Exception:
            return None, False
    return out, True


def _kernel_cmdline_clear_param(state: dict, knob_id: str) -> str | None:
    """Return param prefix for an explicit clear request, else None."""
    prefix_map = {
        "kernel_isolcpus": ("kernel_isolcpus_cores", "isolcpus"),
        "kernel_nohz_full": ("kernel_nohz_full_cores", "nohz_full"),
        "kernel_rcu_nocbs": ("kernel_rcu_nocbs_cores", "rcu_nocbs"),
        "kernel_irqaffinity": ("kernel_irqaffinity_cores", "irqaffinity"),
    }
    meta = prefix_map.get(knob_id)
    if not meta:
        return None
    key, prefix = meta

    if knob_id == KERNEL_IRQAFFINITY and state.get("irq_housekeeping_auto", True):
        audio_raw, audio_configured = _state_int_list_with_presence(state, "irq_pinning_cpu_cores")
        if audio_configured and _kernel_cmdline_override(state, knob_id) is None:
            return prefix
        return None

    cores_raw, configured = _state_int_list_with_presence(state, key)
    if configured and not cores_raw:
        return prefix
    return None


def _resolve_housekeeping_cores(state: dict, audio_set: set[int], warnings: list[str] | None = None) -> set[int] | None:
    warn = warnings if warnings is not None else []
    auto = state.get("irq_housekeeping_auto")
    if not isinstance(auto, bool):
        auto = True

    housekeeping: set[int] | None = None
    if auto:
        from audioknob_gui.core.irq import read_cpu_present

        housekeeping = read_cpu_present() - set(audio_set)
    else:
        raw = state.get("irq_housekeeping_cores")
        if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
            housekeeping = {int(x) for x in raw} or None
        if housekeeping is None:
            raw = state.get("kernel_irqaffinity_cores")
            if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
                housekeeping = {int(x) for x in raw}
        if housekeeping is None:
            warn.append("Housekeeping cores not set; skipping non-audio IRQ sweep.")
            return None

    if audio_set & housekeeping:
        housekeeping = housekeeping - set(audio_set)
        warn.append("Housekeeping cores overlap audio cores; removing audio cores from housekeeping set.")

    if not housekeeping:
        warn.append("Housekeeping core list is empty; skipping non-audio IRQ sweep.")
        return None

    return housekeeping


def _irq_housekeeping_override(state: dict, audio_cpu_list: str | None) -> str | None:
    if not audio_cpu_list:
        return None
    from audioknob_gui.core.irq import cpu_list_from_cores, parse_cpu_list

    audio_set = parse_cpu_list(audio_cpu_list)
    if not audio_set:
        return None
    housekeeping = _resolve_housekeeping_cores(state, audio_set)
    if not housekeeping:
        return None
    return cpu_list_from_cores(housekeeping)


def _kernel_cmdline_override(state: dict, knob_id: str) -> str | None:
    if knob_id == KERNEL_IRQAFFINITY and state.get("irq_housekeeping_auto", True):
        audio_raw = state.get("irq_pinning_cpu_cores")
        audio_set: set[int] = set()
        if isinstance(audio_raw, list) and all(isinstance(x, int) for x in audio_raw):
            audio_set = {int(x) for x in audio_raw}
        if not audio_set:
            # Auto housekeeping needs an explicit audio-core set; otherwise we'd
            # compute "all CPUs" which is effectively the system default.
            return None
        from audioknob_gui.core.irq import cpu_list_from_cores, read_cpu_present

        housekeeping = read_cpu_present() - audio_set
        if not housekeeping:
            return None
        cpu_list = cpu_list_from_cores(sorted(housekeeping))
        if not cpu_list:
            return None
        return f"irqaffinity={cpu_list}"
    mapping = {
        "kernel_isolcpus": ("kernel_isolcpus_cores", "isolcpus"),
        "kernel_nohz_full": ("kernel_nohz_full_cores", "nohz_full"),
        "kernel_rcu_nocbs": ("kernel_rcu_nocbs_cores", "rcu_nocbs"),
        "kernel_irqaffinity": ("kernel_irqaffinity_cores", "irqaffinity"),
    }
    meta = mapping.get(knob_id)
    if not meta:
        return None
    key, prefix = meta
    cores_raw = state.get(key)
    if not (isinstance(cores_raw, list) and all(isinstance(x, int) for x in cores_raw)):
        return None
    from audioknob_gui.core.irq import cpu_list_from_cores

    cpu_list = cpu_list_from_cores(cores_raw)
    if not cpu_list:
        return None
    return f"{prefix}={cpu_list}"


def _kernel_cmdline_status_param(state: dict, knob_id: str) -> str | None:
    """Resolve kernel cmdline param for status checks.

    Dynamic core-list knobs can be status-checked by key name even before the
    user configures cores, so they report not_applied/applied instead of unknown.
    """
    override = _kernel_cmdline_override(state, knob_id)
    if override:
        return override
    clear_param = _kernel_cmdline_clear_param(state, knob_id)
    if clear_param:
        return clear_param
    fallback = {
        "kernel_isolcpus": "isolcpus",
        "kernel_nohz_full": "nohz_full",
        "kernel_rcu_nocbs": "rcu_nocbs",
    }
    return fallback.get(knob_id)


def _apply_root_state_overrides(kid: str, params: dict[str, Any], state: dict) -> dict[str, Any]:
    new_params = dict(params)
    if kid == "kernel_workqueue_cpumask":
        cores_raw, configured = _state_int_list_with_presence(state, "kernel_workqueue_cpumask_cores")
        if configured and not cores_raw:
            try:
                from audioknob_gui.core.irq import cpu_list_from_cores, read_cpu_present

                all_cores = sorted(read_cpu_present())
                if all_cores:
                    new_params["value"] = cpu_list_from_cores(all_cores)
            except Exception:
                pass
            return new_params
        cpu_list = _state_cpu_list(state, "kernel_workqueue_cpumask_cores")
        if cpu_list:
            new_params["value"] = cpu_list
        return new_params

    if kid == "irqbalance_banned_cpulist":
        distro_id = worker_ops.read_os_release().get("ID", "")
        new_params["path"] = worker_ops.resolve_irqbalance_config_path(distro_id)
        cores_raw, configured = _state_int_list_with_presence(state, "irqbalance_banned_cpulist_cores")
        if configured and not cores_raw:
            new_params["lines"] = []
            new_params["clear_prefixes"] = ["IRQBALANCE_BANNED_CPULIST="]
        else:
            cpu_list = _state_cpu_list(state, "irqbalance_banned_cpulist_cores")
            if cpu_list:
                new_params["lines"] = [f"IRQBALANCE_BANNED_CPULIST={cpu_list}"]
        new_params["replace_prefixes"] = ["IRQBALANCE_BANNED_CPULIST="]
        new_params["post_apply"] = [["systemctl", "try-restart", "irqbalance.service"]]
        return new_params

    if kid == "cgroup_user_slice_allowed_cpus":
        cores_raw, configured = _state_int_list_with_presence(state, "cgroup_user_slice_allowed_cores")
        if configured and not cores_raw:
            new_params["clear_file"] = True
            new_params["post_apply"] = [["systemctl", "daemon-reload"]]
            new_params.pop("replace_file", None)
            return new_params
        cpu_list = _state_cpu_list(state, "cgroup_user_slice_allowed_cores")
        if cpu_list:
            new_params["lines"] = _user_slice_allowed_cpus_lines(state)
            new_params["replace_file"] = True
            new_params.pop("clear_file", None)
            new_params["post_apply"] = [["systemctl", "daemon-reload"]]
        return new_params

    if kid == "systemd_pipewire_service_rt":
        has_override = any(
            state.get(key) is not None
            for key in (
                "systemd_pipewire_service_rt_policy",
                "systemd_pipewire_service_rt_priority",
                "systemd_pipewire_service_rt_cpus",
            )
        )
        if has_override:
            new_params["lines"] = _systemd_service_lines(
                state, "systemd_pipewire_service_rt", fallback_prio=88
            )
            new_params["replace_file"] = True
            new_params["post_apply"] = [["systemctl", "daemon-reload"]]
        return new_params

    if kid == "systemd_wireplumber_service_rt":
        has_override = any(
            state.get(key) is not None
            for key in (
                "systemd_wireplumber_service_rt_policy",
                "systemd_wireplumber_service_rt_priority",
                "systemd_wireplumber_service_rt_cpus",
            )
        )
        if has_override:
            new_params["lines"] = _systemd_service_lines(
                state, "systemd_wireplumber_service_rt", fallback_prio=80
            )
            new_params["replace_file"] = True
            new_params["post_apply"] = [["systemctl", "daemon-reload"]]
        return new_params

    return new_params


def _kernel_cmdline_param_from_manifest(manifest: dict, knob_id: str) -> str | None:
    prefix_map = {
        "kernel_isolcpus": "isolcpus",
        "kernel_nohz_full": "nohz_full",
        "kernel_rcu_nocbs": "rcu_nocbs",
        "kernel_irqaffinity": "irqaffinity",
    }
    prefix = prefix_map.get(knob_id)
    if not prefix:
        return None
    for entry in manifest.get("effects", []):
        if entry.get("kind") != "kernel_cmdline":
            continue
        param = str(entry.get("param", "")).strip()
        if not param:
            continue
        if param == prefix or param.startswith(prefix + "="):
            return param
    return None


def _backup_once(
    tx,
    backups: list[dict],
    path: str,
    *,
    we_created: bool = False,
    knob_id: str | None = None,
) -> dict:
    """Backup a path at most once per transaction.

    The worker batches multiple knob applies into a single transaction. To keep
    per-knob restore surgical, we annotate each backup with the knob(s) that
    touched it.
    """
    for meta in backups:
        if meta.get("path") == path:
            if knob_id:
                knob_ids = meta.get("knob_ids")
                if not isinstance(knob_ids, list):
                    knob_ids = []
                if knob_id not in knob_ids:
                    knob_ids.append(knob_id)
                meta["knob_ids"] = knob_ids
            return meta
    meta = backup_file(tx, path, we_created=we_created)
    if knob_id:
        meta["knob_ids"] = [knob_id]
    backups.append(meta)
    return meta


def _restore_power_profile_effects(effects: list[dict[str, Any]], errors: list[str]) -> int:
    from audioknob_gui.platform.packages import which_command

    restored = 0
    for effect in effects:
        if effect.get("kind") != "power_profile":
            continue
        backend = str(effect.get("backend", "")).strip()
        before = str(effect.get("before", "")).strip()
        if not backend or not before:
            continue
        if backend == "powerprofilesctl":
            cmd = which_command("powerprofilesctl") or "powerprofilesctl"
            argv = [cmd, "set", before]
        elif backend == "tuned":
            cmd = which_command("tuned-adm") or "tuned-adm"
            argv = [cmd, "profile", before]
        else:
            errors.append(f"Unknown power profile backend: {backend}")
            continue
        result = subprocess.run(argv, capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            errors.append(f"Failed to restore power profile ({backend}): {detail}")
            continue
        restored += 1
    return restored


def cmd_detect(_: argparse.Namespace) -> int:
    print(json.dumps(dump_detect(), indent=2, sort_keys=True))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    state = _load_gui_state()
    qjackctl_override = _qjackctl_cpu_cores_override(state)
    power_profile_backend = _power_profile_backend_override(state)
    irq_devices_override, irq_cpu_override = _irq_pinning_override(state)

    items = []
    for kid in args.knob:
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")

        # Apply per-user overrides from GUI state (non-root knobs)
        if (
            qjackctl_override is not None
            and k.impl is not None
            and k.impl.kind == "qjackctl_server_prefix"
        ):
            new_params = dict(k.impl.params)
            new_params["cpu_cores"] = qjackctl_override
            k = replace(k, impl=replace(k.impl, params=new_params))

        if k.impl is not None and k.id.startswith("pipewire_") and k.impl.kind in ("pipewire_conf", "wpctl_profile"):
            new_params = _apply_pipewire_state_overrides(k.id, k.impl.params, state)
            k = replace(k, impl=replace(k.impl, params=new_params))
        if k.impl is not None and k.impl.kind == "wireplumber_conf":
            new_params = _apply_pipewire_state_overrides(k.id, k.impl.params, state)
            k = replace(k, impl=replace(k.impl, params=new_params))
        if k.impl is not None and k.id == PIPEWIRE_RT_LIMITS_GROUP and k.impl.kind == "pam_limits_audio_group":
            new_params = _apply_pipewire_state_overrides(k.id, k.impl.params, state)
            k = replace(k, impl=replace(k.impl, params=new_params))
        if (
            power_profile_backend is not None
            and k.id == POWER_PROFILE_PERFORMANCE
            and k.impl is not None
            and k.impl.kind == "power_profile"
        ):
            new_params = dict(k.impl.params)
            new_params["backend"] = power_profile_backend
            k = replace(k, impl=replace(k.impl, params=new_params))
        kernel_override = _kernel_cmdline_override(state, k.id)
        if k.impl is not None and k.impl.kind == "kernel_cmdline":
            if kernel_override:
                new_params = dict(k.impl.params)
                new_params["param"] = kernel_override
                k = replace(k, impl=replace(k.impl, params=new_params))
            else:
                clear_param = _kernel_cmdline_clear_param(state, k.id)
                if clear_param:
                    new_params = dict(k.impl.params)
                    new_params["remove_param"] = clear_param
                    k = replace(k, impl=replace(k.impl, params=new_params))
        if (
            (irq_devices_override or irq_cpu_override)
            and k.impl is not None
            and k.impl.kind == "irq_affinity"
        ):
            new_params = dict(k.impl.params)
            if irq_devices_override is not None:
                new_params["device_keys"] = irq_devices_override
            if irq_cpu_override is not None:
                new_params["cpu_cores"] = irq_cpu_override
            k = replace(k, impl=replace(k.impl, params=new_params))
        if k.impl is not None:
            new_params = _apply_root_state_overrides(k.id, k.impl.params, state)
            if new_params != k.impl.params:
                k = replace(k, impl=replace(k.impl, params=new_params))
        items.append(preview(k, action=args.action))

    payload = {
        "schema": 1,
        "items": [
            {
                "knob_id": i.knob_id,
                "title": i.title,
                "description": i.description,
                "requires_root": i.requires_root,
                "requires_reboot": i.requires_reboot,
                "risk_level": i.risk_level,
                "action": i.action,
                "file_changes": [
                    {"path": fc.path, "action": fc.action, "diff": fc.diff}
                    for fc in i.file_changes
                ],
                "would_run": i.would_run,
                "would_write": i.would_write,
                "notes": i.notes,
            }
            for i in items
        ],
    }

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_apply_user(args: argparse.Namespace) -> int:
    """Apply non-root knobs (user-scope transactions)."""
    logger = logging.getLogger("audioknob.worker")
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    paths = default_paths()
    tx = new_tx(paths.user_state_dir)

    state = _load_gui_state()
    qjackctl_override = _qjackctl_cpu_cores_override(state)

    backups: list[dict] = []
    effects: list[dict] = []
    applied: list[str] = []
    warnings: list[str] = []

    for kid in args.knob:
        logger.info("apply-user knob=%s", kid)
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")
        if k.requires_root:
            raise SystemExit(f"Knob {kid} requires root; use 'apply' command with pkexec")
        if not k.capabilities.apply:
            continue
        if not k.impl:
            continue

        kind = k.impl.kind
        params = k.impl.params

        if kind == "qjackctl_server_prefix":
            if _is_qjackctl_running():
                raise SystemExit(
                    "QjackCtl is running. Quit QjackCtl before applying QjackCtl RT so changes persist."
                )
            path_str = str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))
            path = Path(path_str).expanduser()
            _backup_once(tx, backups, str(path), knob_id=kid)

            from audioknob_gui.core.qjackctl import (
                build_post_start_script,
                default_post_start_script_path,
                ensure_server_flags,
                normalize_cpu_cores,
                read_config,
            )

            ensure_rt = bool(params.get("ensure_rt", True))
            ensure_priority = bool(params.get("ensure_priority", False))
            cpu_cores = qjackctl_override if qjackctl_override is not None else params.get("cpu_cores")
            if cpu_cores is not None:
                cpu_cores = str(cpu_cores)
            cpu_cores_norm = normalize_cpu_cores(cpu_cores) if cpu_cores is not None else None

            post_startup_enabled = False
            post_startup_shell = ""
            post_script_path = default_post_start_script_path()
            if cpu_cores_norm:
                script_body = build_post_start_script(cpu_cores_norm)
                _backup_once(tx, backups, str(post_script_path), knob_id=kid)
                post_script_path.parent.mkdir(parents=True, exist_ok=True)
                post_script_path.write_text(script_body, encoding="utf-8")
                try:
                    os.chmod(post_script_path, 0o700)
                except Exception:
                    pass
                post_startup_enabled = True
                post_startup_shell = str(post_script_path)
            else:
                if post_script_path.exists():
                    _backup_once(tx, backups, str(post_script_path), knob_id=kid)
                    try:
                        post_script_path.unlink()
                    except Exception:
                        pass
                post_startup_enabled = False
                post_startup_shell = ""

            try:
                cfg = read_config(path)
            except Exception:
                cfg = None

            if cfg is not None and cfg.server_config_enabled:
                warnings.append(
                    "QjackCtl ServerConfig was enabled and has been disabled so the GUI settings are used."
                )
                logger.info("qjackctl ServerConfig disabled path=%s", path)

            before, after = ensure_server_flags(
                path,
                ensure_rt=ensure_rt,
                ensure_priority=ensure_priority,
                cpu_cores="",
                mirror_unscoped=True,
                server_config_enabled=False,
                post_startup_enabled=post_startup_enabled,
                post_startup_shell=post_startup_shell,
            )
            if cpu_cores_norm:
                try:
                    result = apply_jackd_affinity(cpu_cores_norm)
                    effects.append({"kind": "jackd_affinity", "knob_id": kid, "result": result})
                    if result.get("status") == "not_running":
                        warnings.append("JACK is not running; CPU pinning will apply the next time you start it.")
                    elif result.get("status") in ("partial", "invalid_cpu_list"):
                        warnings.append("Failed to update running jackd CPU affinity; see logs for details.")
                except Exception as e:
                    effects.append({"kind": "jackd_affinity", "knob_id": kid, "error": str(e)})
                    warnings.append("Failed to update running jackd CPU affinity; see logs for details.")

        elif kind == "pipewire_conf":
            import subprocess

            params = _apply_pipewire_state_overrides(kid, params, state)
            if not worker_ops._pipewire_has_settings(params):
                raise SystemExit("No PipeWire settings configured; configure this knob before applying.")

            path_str = str(params.get("path", "~/.config/pipewire/pipewire.conf.d/99-audioknob.conf"))
            path = Path(path_str).expanduser()
            _backup_once(tx, backups, str(path), knob_id=kid)

            content = worker_ops.build_pipewire_conf_content(params)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            # Apply immediately: restart PipeWire user services (best-effort).
            # Avoid failing the whole knob if restart is unsupported on the system.
            try:
                r = subprocess.run(
                    ["systemctl", "--user", "restart", "pipewire.service", "pipewire-pulse.service"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                effects.append(
                    {
                        "kind": "pipewire_restart",
                        "knob_id": kid,
                        "result": {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr},
                    }
                )
            except Exception as e:
                effects.append({"kind": "pipewire_restart", "knob_id": kid, "error": str(e)})

        elif kind == "wireplumber_conf":
            import subprocess

            params = _apply_pipewire_state_overrides(kid, params, state)
            if not worker_ops._wireplumber_has_settings(params):
                raise SystemExit("No WirePlumber ALSA properties configured; configure this knob before applying.")

            path_str = str(
                params.get(
                    "path",
                    "~/.config/wireplumber/wireplumber.conf.d/90-audioknob-alsa.conf",
                )
            )
            path = Path(path_str).expanduser()
            _backup_once(tx, backups, str(path), knob_id=kid)
            content = worker_ops.build_wireplumber_conf_content(params)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            try:
                r = subprocess.run(
                    ["systemctl", "--user", "restart", "wireplumber.service"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                effects.append(
                    {
                        "kind": "wireplumber_restart",
                        "knob_id": kid,
                        "result": {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr},
                    }
                )
            except Exception as e:
                effects.append({"kind": "wireplumber_restart", "knob_id": kid, "error": str(e)})

        elif kind == "wpctl_profile":
            import subprocess
            import re
            from audioknob_gui.platform.packages import which_command

            params = _apply_pipewire_state_overrides(kid, params, state)
            device_id = params.get("device_id")
            if device_id is None or str(device_id).strip() == "":
                raise SystemExit("No device selected. Configure the Pro Audio knob first.")
            applied_via_pactl = False
            cmd = which_command("wpctl") or "wpctl"
            inspect = subprocess.run(
                [cmd, "inspect", str(device_id)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if inspect.returncode != 0:
                detail = inspect.stderr.strip() or inspect.stdout.strip() or "wpctl inspect failed"
                raise SystemExit(detail)
            text = inspect.stdout or ""
            current = None
            profiles: list[dict[str, str]] = []
            in_profiles = False
            card_name = None
            for line in text.splitlines():
                s = line.strip()
                clean = s.lstrip("* ").strip()
                if not clean:
                    continue
                low = clean.lower()
                if low.startswith("device.name"):
                    _, _, value = clean.partition("=")
                    name = value.strip().strip('"')
                    if name:
                        card_name = name
                if low.startswith("profiles:"):
                    in_profiles = True
                    continue
                if in_profiles and ":" in clean and not re.match(r"^\d+\.", clean):
                    in_profiles = False
                if low.startswith("active profile:"):
                    current = clean.split(":", 1)[1].strip()
                    continue
                if in_profiles:
                    m = re.match(r"^(\d+)\.\s*(.+)$", clean)
                    if m:
                        idx = m.group(1).strip()
                        name_raw = m.group(2).strip()
                        name = name_raw.split("(", 1)[0].strip()
                        profiles.append({"index": idx, "name": name})
            target = None
            for prof in profiles:
                name = prof.get("name", "")
                if "pro audio" in name.lower() or "pro-audio" in name.lower():
                    target = prof.get("index") or name
                    break
            if not target and card_name:
                pactl = which_command("pactl")
                if pactl:
                    pactl_current = None
                    pactl_list = subprocess.run(
                        [pactl, "list", "cards"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    text_cards = pactl_list.stdout or ""
                    in_card = False
                    in_profiles = False
                    for line in text_cards.splitlines():
                        raw = line.rstrip()
                        if raw.strip().startswith("Name:"):
                            name = raw.split(":", 1)[1].strip()
                            in_card = name == card_name
                            in_profiles = False
                            continue
                        if not in_card:
                            continue
                        if raw.strip().startswith("Profiles:"):
                            in_profiles = True
                            continue
                        if raw.strip().startswith("Active Profile:"):
                            pactl_current = raw.split(":", 1)[1].strip()
                            continue
                        if in_profiles:
                            stripped = raw.strip()
                            if stripped and ":" in stripped:
                                profile_key = stripped.split(":", 1)[0].strip().lower()
                                if profile_key == "pro-audio":
                                    target = "pro-audio"
                                    break
                        if target:
                            break
                    if current is None and pactl_current:
                        current = pactl_current
                if target and pactl:
                    set_result = subprocess.run(
                        [pactl, "set-card-profile", str(card_name), str(target)],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if set_result.returncode != 0:
                        detail = set_result.stderr.strip() or set_result.stdout.strip() or "pactl set-card-profile failed"
                        raise SystemExit(detail)
                    if current:
                        effects.append(
                            {
                                "kind": "pactl_profile",
                                "knob_id": kid,
                                "card": str(card_name),
                                "before": current,
                                "after": str(target),
                            }
                        )
                    applied_via_pactl = True
            if applied_via_pactl:
                applied.append(kid)
                continue
            if not target:
                raise SystemExit("Pro Audio profile not found for the selected device.")
            set_result = subprocess.run(
                [cmd, "set-profile", str(device_id), str(target)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if set_result.returncode != 0:
                detail = set_result.stderr.strip() or set_result.stdout.strip() or "wpctl set-profile failed"
                raise SystemExit(detail)
            if current:
                effects.append(
                    {
                        "kind": "wpctl_profile",
                        "knob_id": kid,
                        "device_id": str(device_id),
                        "before": current,
                        "after": str(target),
                    }
                )

        elif kind == "user_service_mask":
            import subprocess
            
            services = params.get("services", [])
            if isinstance(services, str):
                services = [services]

            existing = resolve_user_services(services)
            if not existing:
                raise SystemExit("No matching user services found to mask")

            masked_services: list[dict] = []
            for svc in existing:
                # Capture pre-state so restore doesn't unmask services that were already masked.
                pre_enabled = subprocess.run(
                    ["systemctl", "--user", "is-enabled", svc],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                pre_active = subprocess.run(
                    ["systemctl", "--user", "is-active", svc],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

                # Stop and mask the service
                subprocess.run(["systemctl", "--user", "stop", svc], check=False, capture_output=True)
                result = subprocess.run(["systemctl", "--user", "mask", svc], check=False, capture_output=True)
                if result.returncode == 0:
                    masked_services.append({"unit": svc, "pre_enabled": pre_enabled, "pre_active": pre_active})
            
            if masked_services:
                effects.append({
                    "kind": "user_service_mask",
                    "knob_id": kid,
                    "services": masked_services,
                })

        elif kind == "baloo_disable":
            import shutil
            import subprocess
            
            from audioknob_gui.platform.packages import which_command
            cmd = which_command("balooctl")
            if cmd:
                try:
                    result = subprocess.run([cmd, "disable"], check=False, capture_output=True, text=True, timeout=10)
                except subprocess.TimeoutExpired:
                    raise SystemExit("balooctl disable timed out")
                if result.returncode != 0:
                    err = result.stderr.strip() or result.stdout.strip() or "balooctl disable failed"
                    raise SystemExit(err)
                # Verify state if possible (balooctl6 can write to stderr)
                try:
                    status = subprocess.run([cmd, "status"], check=False, capture_output=True, text=True, timeout=5)
                    out = (status.stdout + "\n" + status.stderr).lower()
                    if "running" in out and "disabled" not in out and "not running" not in out and "stopped" not in out:
                        raise SystemExit("balooctl reports running after disable")
                except subprocess.TimeoutExpired:
                    pass
                effects.append({
                    "kind": "baloo_disable",
                    "knob_id": kid,
                    "result": {"returncode": result.returncode},
                })
            else:
                raise SystemExit("balooctl not found (balooctl/balooctl6) - KDE may not be installed")

        else:
            raise SystemExit(f"Unsupported non-root knob kind: {kind}")

        applied.append(kid)

    manifest = {
        "schema": 1,
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": effects,
    }
    if warnings:
        manifest["warnings"] = warnings
    write_manifest(tx, manifest)
    audit_payload = {
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": effects,
        "manifest": str(tx.root / "manifest.json"),
    }
    if warnings:
        audit_payload["warnings"] = warnings
    _log_audit_event(
        "apply-user",
        audit_payload,
    )

    logger.info("apply-user done txid=%s applied=%s", tx.txid, ",".join(applied))
    result = {"schema": 1, "txid": tx.txid, "applied": applied}
    if warnings:
        result["warnings"] = warnings
    print(json.dumps(result, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    logger = logging.getLogger("audioknob.worker")
    _require_root()

    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}

    paths = default_paths()
    tx = new_tx(paths.var_lib_dir)

    state = _load_gui_state()
    irq_devices_override, irq_cpu_override = _irq_pinning_override(state)
    power_profile_backend = _power_profile_backend_override(state)

    effects: list[dict] = []
    backups: list[dict] = []
    applied: list[str] = []
    warnings: list[str] = []
    followups: list[dict] = []

    for kid in args.knob:
        logger.info("apply knob=%s", kid)
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")
        if not k.capabilities.apply:
            continue
        if not k.impl:
            continue

        kind = k.impl.kind
        params = k.impl.params

        kernel_override = _kernel_cmdline_override(state, k.id)
        if k.impl.kind == "kernel_cmdline" and k.id in (
            "kernel_isolcpus",
            "kernel_nohz_full",
            "kernel_rcu_nocbs",
            "kernel_irqaffinity",
        ):
            if kernel_override:
                new_params = dict(k.impl.params)
                new_params["param"] = kernel_override
                params = new_params
            else:
                clear_param = _kernel_cmdline_clear_param(state, k.id)
                if clear_param:
                    new_params = dict(k.impl.params)
                    new_params["remove_param"] = clear_param
                    params = new_params
                else:
                    raise SystemExit(f"{k.title} requires CPU cores. Configure cores first.")

        if (
            (irq_devices_override or irq_cpu_override)
            and k.impl is not None
            and k.impl.kind == "irq_affinity"
        ):
            new_params = dict(k.impl.params)
            if irq_devices_override is not None:
                new_params["device_keys"] = irq_devices_override
            if irq_cpu_override is not None:
                new_params["cpu_cores"] = irq_cpu_override
            params = new_params
        if (
            power_profile_backend is not None
            and k.id == POWER_PROFILE_PERFORMANCE
            and k.impl is not None
            and k.impl.kind == "power_profile"
        ):
            new_params = dict(k.impl.params)
            new_params["backend"] = power_profile_backend
            params = new_params
        if k.impl is not None and k.id == PIPEWIRE_RT_LIMITS_GROUP and k.impl.kind == "pam_limits_audio_group":
            params = _apply_pipewire_state_overrides(k.id, params, state)
        params = _apply_root_state_overrides(k.id, params, state)

        if kind == "pam_limits_audio_group":
            path = str(params["path"])
            _backup_once(tx, backups, path, knob_id=kid)

            want_lines = [str(x) for x in params.get("lines", [])]
            before = ""
            try:
                before = Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""
            before_lines = before.splitlines()
            after_lines = list(before_lines)
            for line in want_lines:
                if line not in after_lines:
                    after_lines.append(line)
            after = "\n".join(after_lines).rstrip("\n") + "\n"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(after, encoding="utf-8")

        elif kind == "sysctl_conf":
            path = str(params["path"])
            _backup_once(tx, backups, path, knob_id=kid)

            want_lines = [str(x) for x in params.get("lines", [])]
            replace_file = bool(params.get("replace_file", False))
            replace_prefixes = [
                str(prefix).strip()
                for prefix in params.get("replace_prefixes", [])
                if str(prefix).strip()
            ]
            clear_prefixes = [
                str(prefix).strip()
                for prefix in params.get("clear_prefixes", [])
                if str(prefix).strip()
            ]
            clear_file = bool(params.get("clear_file", False))
            before = ""
            try:
                before = Path(path).read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""
            if clear_file:
                if Path(path).exists():
                    try:
                        Path(path).unlink()
                    except Exception as exc:
                        raise SystemExit(f"Failed to delete {path}: {exc}")
                post_apply = params.get("post_apply")
                if isinstance(post_apply, list):
                    for command in post_apply:
                        if not (
                            isinstance(command, list)
                            and command
                            and all(isinstance(x, str) and x.strip() for x in command)
                        ):
                            continue
                        try:
                            result = subprocess.run(command, capture_output=True, text=True)
                        except Exception as exc:
                            warnings.append(f"Post-apply command failed ({' '.join(command)}): {exc}")
                            continue
                        if result.returncode != 0:
                            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                            warnings.append(
                                f"Post-apply command failed ({' '.join(command)}): {detail}"
                            )
                effects.append(
                    {
                        "kind": "sysctl_conf_clear",
                        "knob_id": kid,
                        "path": path,
                        "message": f"Deleted {path}" if before else f"Missing {path} (already default)",
                    }
                )
                applied.append(kid)
                continue
            if replace_file:
                after_lines = [line for line in want_lines if line.strip()]
            else:
                before_lines = before.splitlines()
                after_lines = list(before_lines)
                for prefix in replace_prefixes:
                    should_remove = any(line.strip().startswith(prefix) for line in want_lines)
                    if not should_remove and prefix in clear_prefixes:
                        should_remove = True
                    if should_remove:
                        after_lines = [
                            line for line in after_lines if not line.strip().startswith(prefix)
                        ]
                for prefix in clear_prefixes:
                    if prefix in replace_prefixes:
                        continue
                    after_lines = [
                        line for line in after_lines if not line.strip().startswith(prefix)
                    ]
                for line in want_lines:
                    if line not in after_lines:
                        after_lines.append(line)
            after = "\n".join(after_lines).rstrip("\n") + "\n"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(after, encoding="utf-8")

            post_apply = params.get("post_apply")
            if isinstance(post_apply, list):
                for command in post_apply:
                    if not (isinstance(command, list) and command and all(isinstance(x, str) and x.strip() for x in command)):
                        continue
                    try:
                        result = subprocess.run(command, capture_output=True, text=True)
                    except Exception as exc:
                        warnings.append(f"Post-apply command failed ({' '.join(command)}): {exc}")
                        continue
                    if result.returncode != 0:
                        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                        warnings.append(
                            f"Post-apply command failed ({' '.join(command)}): {detail}"
                        )

        elif kind == "systemd_unit_toggle":
            from audioknob_gui.worker.ops import systemd_disable_now, systemd_enable_now

            unit = str(params["unit"])
            action = str(params.get("action", ""))
            if action == "disable_now":
                effect = systemd_disable_now(unit)
            elif action == "enable_now":
                effect = systemd_enable_now(unit)
            elif action == "enable":
                effect = systemd_enable_now(unit, start=False)
            elif action == "disable":
                effect = systemd_disable_now(unit)
            else:
                raise SystemExit(f"Unsupported systemd action: {action}")
            effect["knob_id"] = kid
            effects.append(effect)

        elif kind == "rtirq_config":
            from audioknob_gui.core.rtirq import apply_rtirq_block, normalize_rtirq_list
            from audioknob_gui.worker.ops import read_os_release, resolve_rtirq_config_path, systemd_enable_now

            distro_id = read_os_release().get("ID", "")
            cfg_path = resolve_rtirq_config_path(distro_id)
            path = Path(cfg_path)

            name_list = normalize_rtirq_list(params.get("name_list", ["snd", "usb"]))
            high_list = normalize_rtirq_list(params.get("high_list", name_list))
            prio_high = int(params.get("prio_high", 90))
            prio_decr = int(params.get("prio_decr", 5))
            unit = str(params.get("unit", "rtirq.service"))
            if not worker_ops._systemd_unit_exists(unit):
                warnings.append(
                    f"{k.title}: systemd unit not found ({unit}). Install rtirq and try again."
                )
                continue

            before = ""
            try:
                before = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""
            after = apply_rtirq_block(
                before,
                name_list=name_list,
                high_list=high_list,
                prio_high=prio_high,
                prio_decr=prio_decr,
            )
            if before != after:
                _backup_once(tx, backups, str(path), we_created=not path.exists(), knob_id=kid)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(after, encoding="utf-8")

            effect = systemd_enable_now(unit)
            effect["knob_id"] = kid
            effects.append(effect)
            if effect.get("pre", {}).get("active") == "active":
                try:
                    subprocess.run(["systemctl", "restart", unit], check=False, capture_output=True, text=True)
                except Exception:
                    pass

        elif kind == "irq_affinity":
            from audioknob_gui.core.irq import (
                build_irq_pinning_unit,
                collect_target_irqs,
                cpu_list_from_cores,
                is_irq_affinity_writable,
                list_irqs,
                parse_cpu_list,
                read_irq_affinity_list,
                resolve_selected_devices,
            )

            irq_cores_raw, irq_cores_configured = _state_int_list_with_presence(state, "irq_pinning_cpu_cores")
            if irq_cores_configured and not irq_cores_raw:
                persist_state_path = str(params.get("persist_state_path", "")).strip()
                state_path = (
                    Path(persist_state_path)
                    if persist_state_path
                    else Path(default_paths().var_lib_dir) / "state.json"
                )
                persist_unit = str(params.get("persist_unit", "")).strip() or "audioknob-irq-pinning.service"
                persist_unit_path = str(params.get("persist_unit_path", "")).strip()
                unit_path = (
                    Path(persist_unit_path)
                    if persist_unit_path
                    else Path("/etc/systemd/system") / persist_unit
                )
                if state_path.exists():
                    _backup_once(tx, backups, str(state_path), knob_id=kid)
                if unit_path.exists():
                    _backup_once(tx, backups, str(unit_path), knob_id=kid)

                def _read_unit_state(state_cmd: str) -> str:
                    try:
                        result = subprocess.run(
                            ["systemctl", state_cmd, persist_unit],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        return result.stdout.strip() or result.stderr.strip()
                    except Exception:
                        return ""

                pre_enabled = _read_unit_state("is-enabled")
                pre_active = _read_unit_state("is-active")

                pre_irq_affinity: dict[int, str] = {}
                for irq in list_irqs():
                    path_list = Path(f"/proc/irq/{irq}/smp_affinity_list")
                    if not path_list.exists():
                        continue
                    try:
                        pre_irq_affinity[irq] = path_list.read_text(encoding="utf-8").strip()
                    except Exception:
                        continue

                ok, message = _force_reset_irq_affinity(params)
                if not ok:
                    raise SystemExit("IRQ pinning clear failed: " + message)
                effects.append(
                    {
                        "kind": "systemd_unit_toggle",
                        "knob_id": kid,
                        "unit": persist_unit,
                        "pre": {
                            "enabled": pre_enabled,
                            "active": pre_active,
                        },
                        "result": {"returncode": 0, "stdout": "", "stderr": ""},
                    }
                )
                for irq, before in pre_irq_affinity.items():
                    path_list = Path(f"/proc/irq/{irq}/smp_affinity_list")
                    if not path_list.exists():
                        continue
                    try:
                        after = path_list.read_text(encoding="utf-8").strip()
                    except Exception:
                        continue
                    if before == after:
                        continue
                    effects.append(
                        {
                            "kind": "irq_affinity",
                            "knob_id": kid,
                            "irq": irq,
                            "before": before,
                            "after": after,
                        }
                    )
                effects.append(
                    {
                        "kind": "irq_affinity_clear",
                        "knob_id": kid,
                        "message": message,
                    }
                )
                applied.append(kid)
                continue

            device_keys = params.get("device_keys") or []
            cpu_cores = str(params.get("cpu_cores", "")).strip()
            if not device_keys:
                raise SystemExit("IRQ pinning requires device selection. Configure devices first.")
            if not cpu_cores:
                raise SystemExit("IRQ pinning requires CPU cores. Configure cores first.")

            expected_set = parse_cpu_list(cpu_cores)
            if not expected_set:
                raise SystemExit("IRQ pinning CPU list is invalid or empty.")

            selected, missing = resolve_selected_devices(device_keys)
            if missing:
                warnings.append(f"Missing devices: {', '.join(missing)}")
            if not selected:
                raise SystemExit("No selected audio devices found. Connect devices or update selection.")

            target_irqs = collect_target_irqs(selected)
            if not target_irqs:
                raise SystemExit("No IRQs found for selected devices.")

            for device in selected:
                warning = device.get("warning")
                if warning:
                    warnings.append(str(warning))

            try:
                active = subprocess.run(
                    ["systemctl", "is-active", "irqbalance.service"],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
                if active == "active":
                    warnings.append("irqbalance is active and can override IRQ pinning.")
            except Exception:
                pass

            errors: list[str] = []
            for irq in target_irqs:
                path = Path(f"/proc/irq/{irq}/smp_affinity_list")
                if not path.exists():
                    errors.append(f"Missing {path}")
                    continue
                if not is_irq_affinity_writable(irq):
                    errors.append(f"IRQ {irq} affinity is read-only (managed by kernel)")
                    continue
                try:
                    before = path.read_text(encoding="utf-8").strip()
                except Exception as exc:
                    errors.append(f"Failed to read {path}: {exc}")
                    continue
                if parse_cpu_list(before) == expected_set:
                    continue
                try:
                    path.write_text(cpu_cores + "\n", encoding="utf-8")
                except Exception as exc:
                    errors.append(f"Failed to write {path}: {exc}")
                    continue
                effects.append(
                    {"kind": "irq_affinity", "knob_id": kid, "irq": irq, "before": before, "after": cpu_cores}
                )

            if errors:
                raise SystemExit("IRQ affinity update failed: " + "; ".join(errors))

            housekeeping_set = _resolve_housekeeping_cores(state, expected_set, warnings)
            if housekeeping_set:
                housekeeping_list = cpu_list_from_cores(housekeeping_set)
                readonly_irqs: list[int] = []
                for irq in list_irqs():
                    if irq in target_irqs:
                        continue
                    current = read_irq_affinity_list(irq)
                    if current is None:
                        continue
                    current_set = parse_cpu_list(current)
                    if not current_set or not (current_set & expected_set):
                        continue
                    if current_set == housekeeping_set:
                        continue
                    if not is_irq_affinity_writable(irq):
                        readonly_irqs.append(irq)
                        continue
                    path = Path(f"/proc/irq/{irq}/smp_affinity_list")
                    try:
                        path.write_text(housekeeping_list + "\n", encoding="utf-8")
                    except Exception as exc:
                        warnings.append(f"Failed to move IRQ {irq} to housekeeping cores: {exc}")
                        continue
                    effects.append(
                        {"kind": "irq_affinity", "knob_id": kid, "irq": irq, "before": current, "after": housekeeping_list}
                    )
                if readonly_irqs:
                    preview = ",".join(str(x) for x in readonly_irqs[:12])
                    suffix = f" (+{len(readonly_irqs) - 12} more)" if len(readonly_irqs) > 12 else ""
                    warnings.append(
                        "Skipped read-only IRQs (kernel-managed): " + preview + suffix
                    )

            if os.environ.get("AUDIOKNOB_IRQ_PINNING_SERVICE") != "1":
                persist_state_path = str(params.get("persist_state_path", "")).strip()
                state_path = Path(persist_state_path) if persist_state_path else Path(default_paths().var_lib_dir) / "state.json"
                persist_unit = str(params.get("persist_unit", "")).strip() or "audioknob-irq-pinning.service"
                persist_unit_path = str(params.get("persist_unit_path", "")).strip()
                unit_path = Path(persist_unit_path) if persist_unit_path else Path("/etc/systemd/system") / persist_unit

                try:
                    _backup_once(tx, backups, str(state_path), we_created=not state_path.exists(), knob_id=kid)
                    state_payload: dict[str, Any] = {}
                    if state_path.exists():
                        try:
                            existing = json.loads(state_path.read_text(encoding="utf-8"))
                            if isinstance(existing, dict):
                                state_payload.update(existing)
                        except Exception:
                            state_payload = {}
                    state_payload["irq_pinning_devices"] = [str(x) for x in device_keys]
                    state_payload["irq_pinning_cpu_cores"] = sorted(expected_set)
                    auto_housekeeping = state.get("irq_housekeeping_auto")
                    if not isinstance(auto_housekeeping, bool):
                        auto_housekeeping = True
                    state_payload["irq_housekeeping_auto"] = bool(auto_housekeeping)
                    if auto_housekeeping:
                        state_payload.pop("irq_housekeeping_cores", None)
                    else:
                        state_payload["irq_housekeeping_cores"] = sorted(housekeeping_set) if housekeeping_set else []
                    state_path.parent.mkdir(parents=True, exist_ok=True)
                    state_path.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")
                except Exception as exc:
                    warnings.append(f"Failed to persist IRQ pinning config: {exc}")

                try:
                    _backup_once(tx, backups, str(unit_path), we_created=not unit_path.exists(), knob_id=kid)
                    unit_content = build_irq_pinning_unit(str(state_path.parent))
                    unit_path.parent.mkdir(parents=True, exist_ok=True)
                    unit_path.write_text(unit_content, encoding="utf-8")
                    subprocess.run(["systemctl", "daemon-reload"], check=False, capture_output=True, text=True)
                    from audioknob_gui.worker.ops import systemd_enable_now
                    effect = systemd_enable_now(persist_unit)
                    effect["knob_id"] = kid
                    effects.append(effect)
                except Exception as exc:
                    warnings.append(f"Failed to enable IRQ pinning service: {exc}")

        elif kind == "sysfs_glob_kv":
            from audioknob_gui.worker.ops import write_sysfs_values

            glob_pat = params["glob"]
            value = str(params["value"])
            if kid == "kernel_workqueue_cpumask":
                cores_raw, configured = _state_int_list_with_presence(state, "kernel_workqueue_cpumask_cores")
                if configured and not cores_raw:
                    from audioknob_gui.core.irq import cpu_list_from_cores, read_cpu_present

                    all_cores = sorted(read_cpu_present())
                    if not all_cores:
                        raise SystemExit("Failed to read CPU topology for workqueue cpumask reset.")
                    value = cpu_list_from_cores(all_cores)
            try:
                sysfs_effects = write_sysfs_values(glob_pat, value)
            except OSError as exc:
                raise SystemExit(
                    f"{k.title}: failed to write sysfs value '{value}' to {glob_pat}: {exc}"
                ) from exc
            if not sysfs_effects:
                raise SystemExit(f"No sysfs entries found for: {glob_pat}")
            for e in sysfs_effects:
                if isinstance(e, dict):
                    e["knob_id"] = kid
            effects.extend(sysfs_effects)

            # Special case: persistent CPU governor requires additional config to survive reboot.
            if kid == "cpu_governor_performance_persistent":
                from audioknob_gui.worker.ops import (
                    read_os_release,
                    resolve_cpupower_config_path,
                    resolve_cpu_governor_service,
                    systemd_enable_now,
                )

                distro_id = read_os_release().get("ID", "")
                cfg_path = resolve_cpupower_config_path(distro_id)
                key = "GOVERNOR"

                _backup_once(tx, backups, cfg_path, knob_id=kid)

                before = ""
                try:
                    before = Path(cfg_path).read_text(encoding="utf-8")
                except FileNotFoundError:
                    before = ""

                lines = before.splitlines()
                out_lines: list[str] = []
                replaced = False
                for line in lines:
                    if line.strip().startswith(key + "="):
                        out_lines.append(f'{key}="performance"')
                        replaced = True
                    else:
                        out_lines.append(line)
                if not replaced:
                    if out_lines and out_lines[-1].strip() != "":
                        out_lines.append("")
                    out_lines.append('# Added by audioknob-gui (persistent CPU governor)')
                    out_lines.append(f'{key}="performance"')

                after = "\n".join(out_lines).rstrip("\n") + "\n"
                Path(cfg_path).parent.mkdir(parents=True, exist_ok=True)
                Path(cfg_path).write_text(after, encoding="utf-8")

                service = resolve_cpu_governor_service(distro_id)
                if service:
                    # Best-effort: enable service so the setting persists.
                    effect = systemd_enable_now(service)
                    effect["knob_id"] = kid
                    effects.append(effect)
                else:
                    warnings.append(
                        "No cpupower/cpufrequtils systemd service found; "
                        "governor persistence may not survive reboot."
                    )

        elif kind == "power_profile":
            from audioknob_gui.worker.ops import select_power_profile_backend, read_power_profile, systemd_enable_now

            backend = select_power_profile_backend(params)
            if not backend:
                raise SystemExit("No power profile backend found (powerprofilesctl or tuned-adm).")

            service = backend.get("service")
            if service:
                svc_effect = systemd_enable_now(service)
                svc_effect["knob_id"] = kid
                effects.append(svc_effect)
                if svc_effect.get("result", {}).get("returncode") not in (0, None):
                    detail = svc_effect.get("result", {}).get("stderr") or svc_effect.get("result", {}).get("stdout")
                    if detail:
                        warnings.append(f"Failed to enable {service}: {detail.strip()}")

            current = read_power_profile(backend["backend"], backend["cmd"])
            if current is None:
                raise SystemExit("Failed to read current power profile")

            if backend["backend"] == "powerprofilesctl":
                def _list_powerprofilesctl_profiles(cmd: str) -> list[str]:
                    try:
                        res = subprocess.run([cmd, "list"], capture_output=True, text=True)
                    except Exception:
                        return []
                    if res.returncode != 0:
                        return []
                    profiles: list[str] = []
                    for line in res.stdout.splitlines():
                        line = line.strip()
                        if not line or ":" not in line:
                            continue
                        if line.startswith("*"):
                            line = line[1:].strip()
                        name = line.split(":", 1)[0].strip()
                        if name:
                            profiles.append(name)
                    return profiles

                target = str(params.get("ppd_profile", "performance")).strip() or "performance"
                available = _list_powerprofilesctl_profiles(backend["cmd"])
                if available and target not in available:
                    warnings.append(
                        "Power profile 'performance' is not supported on this system. "
                        f"Available profiles: {', '.join(available)}."
                    )
                    continue
                cmd = [backend["cmd"], "set", target]
            else:
                target = str(params.get("tuned_profile", "latency-performance")).strip() or "latency-performance"
                cmd = [backend["cmd"], "profile", target]

            result = subprocess.run(cmd, capture_output=True, text=True)
            effects.append(
                {
                    "kind": "power_profile",
                    "knob_id": kid,
                    "backend": backend["backend"],
                    "before": current,
                    "after": target,
                    "cmd": cmd,
                    "result": {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
                }
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                raise SystemExit(f"Failed to set power profile: {detail}")

        elif kind == "udev_rule":
            path = str(params["path"])
            content = str(params["content"])
            _backup_once(tx, backups, path, knob_id=kid)
            
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content.rstrip("\n") + "\n", encoding="utf-8")
            
            # Reload udev rules
            subprocess.run(["udevadm", "control", "--reload-rules"], check=False)
            subprocess.run(["udevadm", "trigger"], check=False)

        elif kind == "kernel_cmdline":
            from audioknob_gui.worker.ops import detect_distro
            
            param = str(params.get("param", "")).strip()
            remove_param = str(params.get("remove_param", "")).strip()
            if not param and not remove_param:
                raise SystemExit("No kernel parameter specified")
            
            distro = detect_distro()
            if distro.boot_system == "unknown" or not distro.kernel_cmdline_file:
                raise SystemExit(f"Unknown boot system for {distro.distro_id}; cannot modify kernel cmdline")
            
            cmdline_file = distro.kernel_cmdline_file
            _backup_once(tx, backups, cmdline_file, knob_id=kid)
            
            before = ""
            try:
                before = Path(cmdline_file).read_text(encoding="utf-8")
            except FileNotFoundError:
                before = ""

            def _tokens_for_existing(before_text: str, boot_system: str) -> list[str]:
                if boot_system in ("grub2-bls", "bls", "systemd-boot"):
                    return before_text.strip().split()
                if boot_system == "grub2":
                    for line in before_text.splitlines():
                        if not line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                            continue
                        _, _, rhs = line.partition("=")
                        rhs = rhs.strip()
                        if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                            rhs = rhs[1:-1]
                        try:
                            return shlex.split(rhs)
                        except Exception:
                            return rhs.split()
                    return []
                return before_text.strip().split()

            def _param_present(param_str: str, tokens: list[str]) -> bool:
                if not param_str:
                    return False
                if "=" in param_str:
                    return any(t == param_str for t in tokens)
                return any(t == param_str or t.startswith(param_str + "=") for t in tokens)

            def _remove_param(tokens: list[str], param_str: str) -> list[str]:
                if not param_str:
                    return list(tokens)
                if "=" in param_str:
                    return [t for t in tokens if t != param_str]
                return [t for t in tokens if t != param_str and not t.startswith(param_str + "=")]

            tokens = _tokens_for_existing(before, distro.boot_system)
            effect_param = param
            effect_mode = "add"
            if remove_param:
                effect_param = remove_param
                effect_mode = "remove"
                if distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                    after_tokens = _remove_param(tokens, remove_param)
                    after = " ".join(after_tokens).strip()
                    if after:
                        after += "\n"
                    Path(cmdline_file).parent.mkdir(parents=True, exist_ok=True)
                    Path(cmdline_file).write_text(after, encoding="utf-8")
                elif distro.boot_system == "grub2":
                    before_lines = before.splitlines() if before else []
                    after_lines: list[str] = []
                    found = False
                    for line in before_lines:
                        if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                            _, _, rhs = line.partition("=")
                            rhs = rhs.strip()
                            if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                                inner = rhs[1:-1]
                            else:
                                inner = rhs
                            try:
                                line_tokens = shlex.split(inner)
                            except Exception:
                                line_tokens = inner.split()
                            new_tokens = _remove_param(line_tokens, remove_param)
                            after_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{" ".join(new_tokens)}"')
                            found = True
                        else:
                            after_lines.append(line)
                    if found:
                        after = "\n".join(after_lines)
                        if after and not after.endswith("\n"):
                            after += "\n"
                        Path(cmdline_file).write_text(after, encoding="utf-8")
            elif _param_present(param, tokens):
                # Already present, skip
                pass
            elif distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                # BLS style: single line file
                after = before.strip() + " " + param + "\n" if before.strip() else param + "\n"
                Path(cmdline_file).parent.mkdir(parents=True, exist_ok=True)
                Path(cmdline_file).write_text(after, encoding="utf-8")
            elif distro.boot_system == "grub2":
                # GRUB2 style: modify GRUB_CMDLINE_LINUX_DEFAULT
                before_lines = before.splitlines() if before else []
                after_lines = list(before_lines)
                found = False
                for i, line in enumerate(after_lines):
                    if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                        if '="' in line and line.rstrip().endswith('"'):
                            after_lines[i] = line.rstrip()[:-1] + " " + param + '"'
                        else:
                            after_lines[i] = line.rstrip() + " " + param
                        found = True
                        break
                if not found:
                    after_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{param}"')
                after = "\n".join(after_lines)
                if after and not after.endswith("\n"):
                    after += "\n"
                Path(cmdline_file).write_text(after, encoding="utf-8")
            
            # Run bootloader update command
            if distro.kernel_cmdline_update_cmd:
                result = subprocess.run(distro.kernel_cmdline_update_cmd, capture_output=True, text=True)
                effects.append({
                    "kind": "kernel_cmdline",
                    "knob_id": kid,
                    "param": effect_param,
                    "mode": effect_mode,
                    "file": cmdline_file,
                    "update_cmd": distro.kernel_cmdline_update_cmd,
                    "result": {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
                })
                if result.returncode != 0:
                    cmd_str = " ".join(distro.kernel_cmdline_update_cmd)
                    detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                    warnings.append(
                        "Bootloader update failed for kernel cmdline.\n"
                        f"Command: {cmd_str}\n"
                        f"Error: {detail}\n"
                        "Run the command manually and reboot."
                    )
                    followups.append({
                        "label": f"Run: {cmd_str}",
                        "cmd": distro.kernel_cmdline_update_cmd,
                    })
            elif distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                warnings.append(
                    "Kernel cmdline updated but no bootloader update command is configured.\n"
                    "Run sdbootutil update-all-entries and reboot."
                )
                followups.append({
                    "label": "Run: sdbootutil update-all-entries",
                    "cmd": ["sdbootutil", "update-all-entries"],
                })
            elif distro.boot_system == "grub2":
                warnings.append(
                    "Kernel cmdline updated but no bootloader update command is configured.\n"
                    "Run grub2-mkconfig -o /boot/grub2/grub.cfg (or your distro's update-grub) and reboot."
                )
                followups.append({
                    "label": "Run: grub2-mkconfig -o /boot/grub2/grub.cfg",
                    "cmd": ["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"],
                })

        elif kind == "read_only":
            pass
        else:
            raise SystemExit(f"Unsupported knob kind: {kind}")

        applied.append(kid)

    manifest = {
        "schema": 1,
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": effects,
    }
    write_manifest(tx, manifest)
    audit_payload = {
        "txid": tx.txid,
        "applied": applied,
        "backups": backups,
        "effects": effects,
        "manifest": str(tx.root / "manifest.json"),
    }
    if warnings:
        audit_payload["warnings"] = warnings
    if followups:
        audit_payload["followups"] = followups
    _log_audit_event("apply", audit_payload)

    logger.info("apply done txid=%s applied=%s", tx.txid, ",".join(applied))
    result = {"schema": 1, "txid": tx.txid, "applied": applied}
    if warnings:
        result["warnings"] = warnings
    if followups:
        result["followups"] = followups
    print(json.dumps(result, indent=2))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Restore a transaction (root or user-scope)."""
    paths = default_paths()

    # Try root transactions first, then user
    tx_root = Path(paths.var_lib_dir) / "transactions" / args.txid
    manifest_path = tx_root / "manifest.json"
    is_root = manifest_path.exists()

    if not is_root:
        tx_root = Path(paths.user_state_dir) / "transactions" / args.txid
        manifest_path = tx_root / "manifest.json"
        if not manifest_path.exists():
            raise SystemExit(f"Transaction not found: {args.txid}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Restore files (works for both root and user)
    for meta in manifest.get("backups", []):
        restore_file(type("Tx", (), {"root": tx_root})(), meta)

    # Restore effects
    effects = manifest.get("effects", [])
    
    if is_root:
        _require_root()
        sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
        systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]
        irq_affinity = [e for e in effects if e.get("kind") == "irq_affinity"]

        sysfs_errors = restore_sysfs(sysfs)
        for e in systemd:
            worker_ops.systemd_restore(e)
        irq_errors = restore_irq_affinity(irq_affinity)
        power_errors: list[str] = []
        _restore_power_profile_effects(effects, power_errors)
        if sysfs_errors:
            power_errors.extend(sysfs_errors)
        if irq_errors:
            power_errors.extend(irq_errors)
    
    # User-scope effects
    from audioknob_gui.worker.ops import user_service_restore, baloo_enable
    from audioknob_gui.platform.packages import which_command
    
    for e in effects:
        if e.get("kind") == "user_service_mask":
            user_service_restore(e)
        elif e.get("kind") == "baloo_disable":
            baloo_enable()
        elif e.get("kind") == "pactl_profile":
            card = e.get("card")
            before = e.get("before")
            if card and before:
                pactl = which_command("pactl") or "pactl"
                try:
                    subprocess.run(
                        [pactl, "set-card-profile", str(card), str(before)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                except Exception:
                    pass
        elif e.get("kind") == "wpctl_profile":
            device_id = e.get("device_id")
            before = e.get("before")
            if device_id and before:
                cmd = which_command("wpctl") or "wpctl"
                try:
                    subprocess.run(
                        [cmd, "set-profile", str(device_id), str(before)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                except Exception:
                    pass

    _log_audit_event(
        "restore",
        {
            "txid": args.txid,
            "was_root": is_root,
            "backups": manifest.get("backups", []),
            "effects": effects,
            "manifest": str(manifest_path),
            "errors": power_errors if is_root else [],
        },
    )
    print(json.dumps({"schema": 1, "restored": args.txid, "was_root": is_root}, indent=2))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """List transactions for user/root scope."""
    paths = default_paths()
    scope = getattr(args, "scope", "all")
    items: list[dict] = []
    root_unavailable = False

    if scope in ("root", "all"):
        if os.geteuid() != 0:
            if scope == "root":
                raise SystemExit("history --scope root requires pkexec")
            root_unavailable = True
        else:
            for tx in list_transactions(paths.var_lib_dir):
                tx["scope"] = "root"
                items.append(tx)

    if scope in ("user", "all"):
        for tx in list_transactions(paths.user_state_dir):
            tx["scope"] = "user"
            items.append(tx)

    items.sort(key=lambda item: float(item.get("timestamp") or 0), reverse=True)
    print(
        json.dumps(
            {
                "schema": 1,
                "items": items,
                "scope": scope,
                "root_unavailable": root_unavailable,
            },
            indent=2,
        )
    )
    return 0


def cmd_reset_defaults(args: argparse.Namespace) -> int:
    """Reset all audioknob-gui changes to system defaults.
    
    This uses the reset_strategy stored in each backup:
    - Files we created: delete them
    - Modified files: restore from our backup (transaction baseline)
      - Package ownership is recorded for diagnostics only; package-manager
        "restore" mechanisms are not a reliable content reset for config files.
    
    Use --scope to filter:
    - 'user': only user-scope transactions (no root needed); silently skips root txs
    - 'root': only root-scope transactions (needs pkexec); errors if not root
    - 'all': both (default); silently skips root txs if not root (for GUI two-phase use)
    
    The GUI uses two-phase reset: first --scope user, then pkexec --scope root.
    """
    paths = default_paths()
    results: list[dict] = []
    errors: list[str] = []
    scope_filter = getattr(args, "scope", "all")
    
    # Gather transactions based on scope filter
    all_txs = []
    
    if scope_filter in ("root", "all"):
        root_txs = list_transactions(paths.var_lib_dir)
        for tx_info in root_txs:
            tx_info["scope"] = "root"
            all_txs.append(tx_info)
    
    if scope_filter in ("user", "all"):
        user_txs = list_transactions(paths.user_state_dir)
        for tx_info in user_txs:
            tx_info["scope"] = "user"
            all_txs.append(tx_info)
    
    # If running the user phase, also compute whether there is pending root work
    # (for GUI two-phase resets) even when there are no user transactions.
    needs_root_reset = False
    if scope_filter == "user":
        root_txs = list_transactions(paths.var_lib_dir)
        for tx_info in root_txs:
            # Pending files: file still exists
            for meta in tx_info.get("backups", []):
                file_path = meta.get("path", "")
                if file_path and Path(file_path).exists():
                    needs_root_reset = True
                    break
            if needs_root_reset:
                break
            # Pending effects: restorable effects
            for effect in tx_info.get("effects", []):
                kind = effect.get("kind", "")
                if kind in ("sysfs_write", "systemd_unit_toggle", "kernel_cmdline", "power_profile"):
                    needs_root_reset = True
                    break
            if needs_root_reset:
                break

    if not all_txs:
        payload = {
            "schema": 1,
            "message": "No transactions found - nothing to reset",
            "reset_count": 0,
            "results": [],
            "errors": [],
            "scope": scope_filter,
            "needs_root_reset": needs_root_reset,
            "needs_reboot": False,
        }
        _log_audit_event(
            "reset-defaults",
            {
                "scope": scope_filter,
                "reset_count": 0,
                "results": [],
                "errors": [],
                "needs_root_reset": needs_root_reset,
                "needs_reboot": False,
            },
        )
        print(json.dumps(payload, indent=2))
        return 0
    
    # Track files to reset (oldest backup wins for true baseline reset)
    reset_paths: set[str] = set()
    file_targets: dict[str, dict[str, Any]] = {}
    needs_bootloader_update = False
    kernel_params: set[str] = set()
    kernel_cmdline_updated = False
    needs_reboot = False
    
    # Process all transactions (newest first - they're already sorted)
    for tx_info in all_txs:
        txid = tx_info["txid"]
        scope = tx_info["scope"]
        backups = tx_info.get("backups", [])
        
        # Check if this is a root transaction and we need root
        if scope == "root" and os.geteuid() != 0:
            # Can't reset root transactions without root privileges
            # Only report as error if scope_filter is "all" (mixed mode)
            # If scope_filter is "root", this is a real error
            if scope_filter == "root":
                errors.append(f"Transaction {txid} needs root; run with pkexec")
            # If scope_filter is "all", we silently skip (GUI will call root separately)
            continue
        
        # Create a Transaction object for backup restore
        from audioknob_gui.core.transaction import Transaction
        tx_root = Path(tx_info["root"])
        tx = Transaction(txid=txid, root=tx_root)

        # Record file backups (keep OLDEST entry per transaction; older tx overrides)
        seen_paths: set[str] = set()
        for meta in backups:
            file_path = meta.get("path", "")
            if not file_path or file_path in seen_paths:
                continue
            seen_paths.add(file_path)
            file_targets[file_path] = {"tx": tx, "meta": meta}
        
        # Handle effects (sysfs, systemd, user services, etc.)
        effects = tx_info.get("effects", [])
        for e in effects:
            if e.get("kind") != "kernel_cmdline":
                continue
            needs_bootloader_update = True
            param = e.get("param")
            if isinstance(param, str) and param:
                kernel_params.add(param)
        
        if scope == "root" and effects and os.geteuid() == 0:
            sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
            systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]
            irq_affinity = [e for e in effects if e.get("kind") == "irq_affinity"]

            try:
                sysfs_errors = restore_sysfs(sysfs)
                for e in systemd:
                    worker_ops.systemd_restore(e)
                irq_errors = restore_irq_affinity(irq_affinity)
                power_errors: list[str] = []
                power_restored = _restore_power_profile_effects(effects, power_errors)
                if sysfs or systemd or irq_affinity or power_restored:
                    results.append({
                        "path": "(root effects)",
                        "strategy": "effects",
                        "success": True,
                        "message": (
                            f"Restored {len(sysfs)} sysfs + {len(systemd)} systemd + "
                            f"{len(irq_affinity)} irq + {power_restored} power profile effects"
                        ),
                    })
                if power_errors:
                    errors.extend(power_errors)
                if sysfs_errors:
                    errors.extend(sysfs_errors)
                if irq_errors:
                    errors.extend(irq_errors)
            except Exception as ex:
                errors.append(f"Failed to restore root effects: {ex}")
        
        # User-scope effects (services, baloo)
        if scope == "user" and effects:
            from audioknob_gui.worker.ops import user_service_restore, baloo_enable
            from audioknob_gui.platform.packages import which_command
            
            user_effects_restored = 0
            for e in effects:
                try:
                    if e.get("kind") == "user_service_mask":
                        user_service_restore(e)
                        user_effects_restored += 1
                    elif e.get("kind") == "baloo_disable":
                        baloo_enable()
                        user_effects_restored += 1
                    elif e.get("kind") == "wpctl_profile":
                        device_id = e.get("device_id")
                        before = e.get("before")
                        if device_id and before:
                            cmd = which_command("wpctl") or "wpctl"
                            subprocess.run(
                                [cmd, "set-profile", str(device_id), str(before)],
                                check=False,
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            user_effects_restored += 1
                except Exception as ex:
                    errors.append(f"Failed to restore user effect: {ex}")
            
            if user_effects_restored:
                results.append({
                    "path": "(user effects)",
                    "strategy": "effects",
                    "success": True,
                    "message": f"Restored {user_effects_restored} user effect(s)",
                })

    # Reset files using oldest backups (true baseline)
    for file_path in sorted(file_targets.keys()):
        entry = file_targets[file_path]
        meta = entry["meta"]
        tx = entry["tx"]
        if file_path in reset_paths:
            continue

        strategy = meta.get("reset_strategy", RESET_BACKUP)
        if strategy == RESET_PACKAGE and os.geteuid() != 0:
            errors.append(f"Need root to restore {file_path} from package")
            continue

        success, message = reset_file_to_default(meta, tx)
        results.append({
            "path": file_path,
            "strategy": strategy,
            "success": success,
            "message": message,
        })

        if success:
            reset_paths.add(file_path)
        else:
            errors.append(message)

    kernel_params_to_remove = set(kernel_params)
    if kernel_params and scope_filter in ("root", "all") and os.geteuid() == 0:
        try:
            from audioknob_gui.worker.ops import detect_distro

            distro = detect_distro()
            cmdline_path = distro.kernel_cmdline_file
            if cmdline_path and cmdline_path in file_targets:
                entry = file_targets[cmdline_path]
                meta = entry["meta"]
                tx = entry["tx"]
                backup_key = meta.get("backup_key")
                if backup_key:
                    backup_path = tx.root / "backups" / backup_key
                    if backup_path.exists():
                        baseline_text = backup_path.read_text(encoding="utf-8")
                        tokens = _kernel_cmdline_tokens(baseline_text, distro.boot_system)
                        baseline_params = {
                            param
                            for param in kernel_params
                            if _kernel_cmdline_param_present(param, tokens)
                        }
                        kernel_params_to_remove = kernel_params - baseline_params
        except Exception:
            kernel_params_to_remove = set(kernel_params)
    
    # Check if there are pending root changes (for informing GUI)
    # Use list-pending semantics: only count files that still exist + restorable effects
    if scope_filter == "user" and not needs_root_reset:
        root_txs = list_transactions(paths.var_lib_dir)
        for tx_info in root_txs:
            # Check for pending files
            for meta in tx_info.get("backups", []):
                file_path = meta.get("path", "")
                if file_path and Path(file_path).exists():
                    needs_root_reset = True
                    break
            if needs_root_reset:
                break
            # Check for restorable effects (sysfs, systemd - not pipewire_restart)
            for effect in tx_info.get("effects", []):
                kind = effect.get("kind", "")
                if kind in ("sysfs_write", "systemd_unit_toggle", "kernel_cmdline"):
                    needs_root_reset = True
                    break
            if needs_root_reset:
                break

    # Ensure kernel cmdline params are removed even if backups still contain them.
    if scope_filter in ("root", "all") and os.geteuid() == 0 and kernel_params_to_remove:
        success, message = _force_reset_kernel_cmdline_params(kernel_params_to_remove, run_update=True)
        if success:
            kernel_cmdline_updated = True
            results.append({
                "path": "(kernel cmdline)",
                "strategy": "kernel_cmdline",
                "success": True,
                "message": message,
            })
        else:
            errors.append(message)

        try:
            cmdline = Path("/proc/cmdline").read_text(encoding="utf-8")
            running_tokens = cmdline.split()

            def _param_in_tokens(p: str, tokens: list[str]) -> bool:
                for token in tokens:
                    if token == p:
                        return True
                    if "=" in p:
                        param_key = p.split("=")[0]
                        if token.startswith(param_key + "=") and token == p:
                            return True
                return False

            needs_reboot = any(_param_in_tokens(p, running_tokens) for p in kernel_params_to_remove)
        except Exception:
            pass

    # If kernel cmdline was reset, update the bootloader so changes stick after reboot.
    if scope_filter in ("root", "all") and os.geteuid() == 0 and not kernel_cmdline_updated:
        try:
            from audioknob_gui.worker.ops import detect_distro
            distro = detect_distro()
            if distro.kernel_cmdline_file and distro.kernel_cmdline_file in reset_paths:
                needs_bootloader_update = True
            if needs_bootloader_update:
                if distro.kernel_cmdline_update_cmd:
                    result = subprocess.run(
                        distro.kernel_cmdline_update_cmd,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        cmd_str = " ".join(distro.kernel_cmdline_update_cmd)
                        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                        errors.append(
                            "Bootloader update failed after reset.\n"
                            f"Command: {cmd_str}\n"
                            f"Error: {detail}\n"
                            "Run the command manually and reboot."
                        )
                    else:
                        results.append({
                            "path": "(bootloader update)",
                            "strategy": "kernel_cmdline",
                            "success": True,
                            "message": f"Ran: {' '.join(distro.kernel_cmdline_update_cmd)}",
                        })
                elif distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                    errors.append(
                        "Kernel cmdline reset but no bootloader update command is configured.\n"
                        "Run sdbootutil update-all-entries and reboot."
                    )
                elif distro.boot_system == "grub2":
                    errors.append(
                        "Kernel cmdline reset but no bootloader update command is configured.\n"
                        "Run grub2-mkconfig -o /boot/grub2/grub.cfg (or your distro's update-grub) and reboot."
                    )
        except Exception as ex:
            errors.append(f"Bootloader update check failed: {ex}")

    _log_audit_event(
        "reset-defaults",
        {
            "scope": scope_filter,
            "reset_count": len(reset_paths),
            "results": results,
            "errors": errors,
            "needs_root_reset": needs_root_reset,
            "needs_reboot": needs_reboot,
        },
    )
    print(json.dumps({
        "schema": 1,
        "message": f"Reset {len(reset_paths)} files to system defaults",
        "reset_count": len(reset_paths),
        "results": results,
        "errors": errors,
        "scope": scope_filter,
        "needs_root_reset": needs_root_reset,
        "needs_reboot": needs_reboot,
    }, indent=2))
    
    return 1 if errors else 0


def cmd_list_changes(_: argparse.Namespace) -> int:
    """List all files/effects modified by audioknob-gui across all transactions."""
    paths = default_paths()

    root_txs = list_transactions(paths.var_lib_dir)
    user_txs = list_transactions(paths.user_state_dir)

    all_files: dict[str, dict] = {}
    all_effects: list[dict] = []
    has_root_effects = False
    has_user_effects = False

    for tx_info in root_txs + user_txs:
        scope = "root" if tx_info in root_txs else "user"
        
        # Collect file backups
        for meta in tx_info.get("backups", []):
            file_path = meta.get("path", "")
            if file_path and file_path not in all_files:
                all_files[file_path] = {
                    "path": file_path,
                    "scope": scope,
                    "txid": tx_info["txid"],
                    "reset_strategy": meta.get("reset_strategy", RESET_BACKUP),
                    "package": meta.get("package"),
                    "we_created": meta.get("we_created", False),
                }
        
        # Collect effects (sysfs, systemd, user services, etc.)
        for effect in tx_info.get("effects", []):
            effect_copy = dict(effect)
            effect_copy["scope"] = scope
            effect_copy["txid"] = tx_info["txid"]
            all_effects.append(effect_copy)
            
            if scope == "root":
                has_root_effects = True
            else:
                has_user_effects = True

    print(json.dumps({
        "schema": 1,
        "files": list(all_files.values()),
        "count": len(all_files),
        "effects": all_effects,
        "effects_count": len(all_effects),
        "has_root_effects": has_root_effects,
        "has_user_effects": has_user_effects,
    }, indent=2))
    return 0


def cmd_list_pending(_: argparse.Namespace) -> int:
    """List files/effects that are still pending reset (files exist, not yet restored).
    
    Unlike list-changes (historical audit), this only shows what CURRENTLY needs resetting.
    Use this for GUI preview of "Reset All".
    """
    paths = default_paths()

    root_txs = list_transactions(paths.var_lib_dir)
    user_txs = list_transactions(paths.user_state_dir)

    pending_files: dict[str, dict] = {}
    pending_effects: list[dict] = []
    has_root_files = False
    has_user_files = False
    has_root_effects = False
    has_user_effects = False

    for tx_info in root_txs + user_txs:
        scope = "root" if tx_info in root_txs else "user"
        
        # Collect file backups - but only if file still exists (or we created it and it's there).
        # Keep OLDEST entry per file (older transactions replace newer).
        seen_paths: set[str] = set()
        for meta in tx_info.get("backups", []):
            file_path = meta.get("path", "")
            if not file_path or file_path in seen_paths:
                continue
            seen_paths.add(file_path)
            
            # Check if file still exists (meaning we still need to reset it)
            from pathlib import Path
            p = Path(file_path).expanduser()
            we_created = meta.get("we_created", False)
            
            if we_created:
                # We created this file - only pending if it still exists
                if not p.exists():
                    continue
            else:
                # We modified existing file - check if our backup exists
                # (if backup exists, we can restore; if file is gone, nothing to do)
                tx_root = Path(tx_info["root"])
                backup_key = meta.get("backup_key", "")
                backup_path = tx_root / "backups" / backup_key if backup_key else None
                if backup_path and not backup_path.exists():
                    continue
                if not p.exists():
                    continue
            
            pending_files[file_path] = {
                "path": file_path,
                "scope": scope,
                "txid": tx_info["txid"],
                "reset_strategy": meta.get("reset_strategy", RESET_BACKUP),
                "package": meta.get("package"),
                "we_created": we_created,
            }
            
            if scope == "root":
                has_root_files = True
            else:
                has_user_files = True
        
        # For effects, deduplicate by kind+path. Transactions are newest-first.
        # We keep the OLDEST entry (original "before" state) to restore to true baseline.
        # So we DON'T skip duplicates here; we let later (older) entries overwrite.
        for effect in tx_info.get("effects", []):
            kind = effect.get("kind", "")
            # Skip pipewire_restart - those are just notifications, not reversible
            if kind == "pipewire_restart":
                continue
            
            # For sysfs_write, deduplicate by path - we only need to restore once
            effect_path = effect.get("path", "")
            effect_key = f"{kind}:{effect_path}"
            
            # Find if we already have this effect (from a newer transaction)
            # We want the OLDEST entry (original before state), so replace if found
            existing_idx = next(
                (i for i, e in enumerate(pending_effects)
                 if e.get("kind") == kind and e.get("path") == effect_path),
                None
            )
            
            effect_copy = dict(effect)
            effect_copy["scope"] = scope
            effect_copy["txid"] = tx_info["txid"]
            
            if existing_idx is not None:
                # Replace with older (current) entry to get original before state
                pending_effects[existing_idx] = effect_copy
            else:
                pending_effects.append(effect_copy)
            
            if scope == "root":
                has_root_effects = True
            else:
                has_user_effects = True

    print(json.dumps({
        "schema": 1,
        "files": list(pending_files.values()),
        "count": len(pending_files),
        "effects": pending_effects,
        "effects_count": len(pending_effects),
        "has_root_files": has_root_files,
        "has_user_files": has_user_files,
        "has_root_effects": has_root_effects,
        "has_user_effects": has_user_effects,
    }, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Check current status of all knobs."""
    reg = load_registry(args.registry)

    # Apply per-user overrides so status reflects GUI-configured values.
    state = _load_gui_state()
    qjackctl_override = _qjackctl_cpu_cores_override(state)
    power_profile_backend = _power_profile_backend_override(state)
    irq_devices_override, irq_cpu_override = _irq_pinning_override(state)
    
    statuses = []
    for k in reg:
        if (
            qjackctl_override is not None
            and k.impl is not None
            and k.impl.kind == "qjackctl_server_prefix"
        ):
            new_params = dict(k.impl.params)
            new_params["cpu_cores"] = qjackctl_override
            k = replace(k, impl=replace(k.impl, params=new_params))
        if k.impl is not None and k.id.startswith("pipewire_") and k.impl.kind in ("pipewire_conf", "wpctl_profile"):
            new_params = _apply_pipewire_state_overrides(k.id, k.impl.params, state)
            k = replace(k, impl=replace(k.impl, params=new_params))
        if k.impl is not None and k.impl.kind == "wireplumber_conf":
            new_params = _apply_pipewire_state_overrides(k.id, k.impl.params, state)
            k = replace(k, impl=replace(k.impl, params=new_params))
        if k.impl is not None and k.id == PIPEWIRE_RT_LIMITS_GROUP and k.impl.kind == "pam_limits_audio_group":
            new_params = _apply_pipewire_state_overrides(k.id, k.impl.params, state)
            k = replace(k, impl=replace(k.impl, params=new_params))
        if (
            power_profile_backend is not None
            and k.id == POWER_PROFILE_PERFORMANCE
            and k.impl is not None
            and k.impl.kind == "power_profile"
        ):
            new_params = dict(k.impl.params)
            new_params["backend"] = power_profile_backend
            k = replace(k, impl=replace(k.impl, params=new_params))
        kernel_param = _kernel_cmdline_status_param(state, k.id)
        if kernel_param and k.impl is not None and k.impl.kind == "kernel_cmdline":
            new_params = dict(k.impl.params)
            new_params["param"] = kernel_param
            k = replace(k, impl=replace(k.impl, params=new_params))
        if k.impl is not None and k.impl.kind == "irq_affinity":
            new_params = dict(k.impl.params)
            if irq_devices_override is not None:
                new_params["device_keys"] = irq_devices_override
            if irq_cpu_override is not None:
                new_params["cpu_cores"] = irq_cpu_override
            housekeeping_override = _irq_housekeeping_override(state, str(new_params.get("cpu_cores", "")).strip())
            if housekeeping_override:
                new_params["housekeeping_cores"] = housekeeping_override
            k = replace(k, impl=replace(k.impl, params=new_params))
        if k.impl is not None:
            new_params = _apply_root_state_overrides(k.id, k.impl.params, state)
            if new_params != k.impl.params:
                k = replace(k, impl=replace(k.impl, params=new_params))
        status = check_knob_status(k)
        statuses.append({
            "knob_id": k.id,
            "title": k.title,
            "status": status,
            "requires_root": k.requires_root,
        })

    # Derive combined status for PW RT setup (limits + module).
    by_id = {s["knob_id"]: s for s in statuses}
    if PIPEWIRE_RT_SETUP in by_id:
        limits = by_id.get(PIPEWIRE_RT_LIMITS_GROUP, {}).get("status", "unknown")
        module = by_id.get(PIPEWIRE_RT_MODULE_TUNING, {}).get("status", "unknown")
        module_keys = (
            "pipewire_rt_prio",
            "pipewire_rt_time_soft",
            "pipewire_rt_time_hard",
            "pipewire_nice_level",
            "pipewire_rlimits_enabled",
            "pipewire_rtkit_enabled",
            "pipewire_rtportal_enabled",
            "pipewire_uclamp_min",
            "pipewire_uclamp_max",
            "pipewire_cpu_zero_denormals",
        )
        module_configured = any(state.get(key) is not None for key in module_keys)
        limits_enabled = state.get("pipewire_limits_enabled")
        combined = "unknown"
        if limits_enabled is False:
            if module_configured:
                if module in ("running", "pending_reboot"):
                    combined = module
                elif module == "applied":
                    combined = "applied"
                elif module in ("not_applied", "sys_default"):
                    combined = "not_applied"
                elif module == "unknown":
                    combined = "unknown"
                else:
                    combined = "partial"
            else:
                combined = "not_applied"
            by_id[PIPEWIRE_RT_SETUP]["status"] = combined
            statuses = list(by_id.values())
            print(json.dumps({
                "schema": 1,
                "statuses": statuses,
            }, indent=2))
            return 0
        if limits in ("running", "pending_reboot"):
            combined = limits
        elif module_configured and module in ("running", "pending_reboot"):
            combined = module
        elif module_configured:
            if limits == "applied" and module == "applied":
                combined = "applied"
            elif limits in ("not_applied", "sys_default") and module in ("not_applied", "sys_default"):
                combined = "not_applied"
            elif limits == "unknown" or module == "unknown":
                combined = "unknown"
            else:
                combined = "partial"
        elif limits in ("applied", "pending_reboot"):
            combined = limits
        elif limits in ("not_applied", "sys_default"):
            combined = "not_applied"
        else:
            combined = limits
        by_id[PIPEWIRE_RT_SETUP]["status"] = combined
        statuses = list(by_id.values())
    
    print(json.dumps({
        "schema": 1,
        "statuses": statuses,
    }, indent=2))
    return 0


def _find_transaction_for_knob(knob_id: str) -> tuple[str | None, dict | None, str | None]:
    """Find the oldest transaction that applied a specific knob.
    
    Returns (txid, manifest, scope) or (None, None, None) if not found.
    """
    paths = default_paths()
    
    # Check root transactions first (oldest first), so restore-knob can restore
    # the original "before" state even if the knob was applied multiple times.
    root_txs = list_transactions(paths.var_lib_dir)
    for tx_info in reversed(root_txs):
        if knob_id in tx_info.get("applied", []):
            manifest_path = Path(tx_info["root"]) / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                return tx_info["txid"], manifest, "root"
    
    # Check user transactions (oldest first) for non-root knobs.
    user_txs = list_transactions(paths.user_state_dir)
    for tx_info in reversed(user_txs):
        if knob_id in tx_info.get("applied", []):
            manifest_path = Path(tx_info["root"]) / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                return tx_info["txid"], manifest, "user"
    
    return None, None, None


def _knob_restore_targets(knob: Any) -> tuple[set[str], set[str], list[str]]:
    """Return (paths, systemd_units, sysfs_globs) for a knob restore filter.

    We intentionally avoid restoring the full transaction manifest, since root
    apply batches multiple knobs into one transaction. These targets are used
    to select only the files/effects that belong to the requested knob.
    """
    if not getattr(knob, "impl", None):
        return set(), set(), []

    try:
        profile = worker_ops.scan_system_profile(knobs=[knob])
        knob_paths = profile.get("knob_paths") or {}
        entry = knob_paths.get(getattr(knob, "id", "")) or {}
        targets = entry.get("targets") or []
    except Exception:
        targets = []

    paths: set[str] = set()
    units: set[str] = set()
    sysfs_globs: list[str] = []

    for t in targets:
        if not isinstance(t, dict):
            continue
        t_type = str(t.get("type", "")).strip()
        value = t.get("value")
        if not value:
            continue
        if t_type in ("path", "kernel_cmdline_file") and isinstance(value, str):
            paths.add(value)
        elif t_type == "systemd_unit" and isinstance(value, str):
            units.add(value)
        elif t_type == "sysfs_glob" and isinstance(value, str):
            sysfs_globs.append(value)

    return paths, units, sysfs_globs


def _filter_manifest_backups_for_knob(
    backups: object,
    *,
    knob_id: str,
    target_paths: set[str],
) -> list[dict]:
    out: list[dict] = []
    if not isinstance(backups, list):
        return out
    for meta in backups:
        if not isinstance(meta, dict):
            continue
        if meta.get("knob_id") == knob_id:
            out.append(meta)
            continue
        knob_ids = meta.get("knob_ids")
        if isinstance(knob_ids, list) and knob_id in knob_ids:
            out.append(meta)
            continue
        path = str(meta.get("path", "")).strip()
        if path and path in target_paths:
            out.append(meta)
    return out


def _filter_manifest_effects_for_knob(
    effects: object,
    *,
    knob_id: str,
    knob: Any,
    target_units: set[str],
    sysfs_globs: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(effects, list):
        return out

    knob_kind = ""
    try:
        knob_kind = str(knob.impl.kind) if getattr(knob, "impl", None) else ""
    except Exception:
        knob_kind = ""

    sysfs_paths: set[str] = set()
    if knob_kind == "sysfs_glob_kv":
        try:
            # Prefer the knob's own glob spec when available.
            raw = knob.impl.params.get("glob") if getattr(knob, "impl", None) else None
            globs = raw if raw is not None else sysfs_globs
            sysfs_paths = set(worker_ops._expand_sysfs_globs(globs))
        except Exception:
            sysfs_paths = set()

    for e in effects:
        if not isinstance(e, dict):
            continue
        if e.get("knob_id") == knob_id:
            out.append(e)
            continue
        kind = e.get("kind")
        if kind == "systemd_unit_toggle":
            unit = str(e.get("unit", "")).strip()
            if unit and unit in target_units:
                out.append(e)
            continue
        if kind == "sysfs_write" and sysfs_paths:
            path = str(e.get("path", "")).strip()
            if path and path in sysfs_paths:
                out.append(e)
            continue
        if kind == "irq_affinity" and knob_kind == "irq_affinity":
            out.append(e)
            continue
        if kind == "power_profile" and knob_kind == "power_profile":
            out.append(e)
            continue
        if kind == "user_service_mask" and knob_kind == "user_service_mask":
            out.append(e)
            continue
        if kind == "baloo_disable" and knob_kind == "baloo_disable":
            out.append(e)
            continue
        if kind in ("pactl_profile", "wpctl_profile") and knob_kind == "wpctl_profile":
            out.append(e)
            continue

    return out


def _restore_knob_once(knob_id: str) -> dict:
    from audioknob_gui.core.paths import get_registry_path
    knob = None
    try:
        reg = load_registry(get_registry_path())
        knob = next((k for k in reg if k.id == knob_id), None)
    except Exception:
        knob = None

    txid, manifest, scope = _find_transaction_for_knob(knob_id)
    if not txid or not manifest:
        return {
            "schema": 1,
            "success": False,
            "knob_id": knob_id,
            "error": f"No transaction found for knob: {knob_id}",
        }

    # Check if we need root for this operation
    if scope == "root" and os.geteuid() != 0:
        return {
            "schema": 1,
            "success": False,
            "knob_id": knob_id,
            "error": f"Knob {knob_id} was applied as root; run with pkexec to restore",
        }

    target_paths, target_units, sysfs_globs = _knob_restore_targets(knob)
    backups_for_knob = _filter_manifest_backups_for_knob(
        manifest.get("backups", []),
        knob_id=knob_id,
        target_paths=target_paths,
    )
    effects_for_knob = _filter_manifest_effects_for_knob(
        manifest.get("effects", []),
        knob_id=knob_id,
        knob=knob,
        target_units=target_units,
        sysfs_globs=sysfs_globs,
    )

    if knob and knob.impl and knob.impl.kind == "kernel_cmdline":
        from audioknob_gui.worker.ops import detect_distro

        param = str(knob.impl.params.get("param", ""))
        if not param:
            param = _kernel_cmdline_param_from_manifest(manifest, knob_id) or ""
        if not param:
            param = _kernel_cmdline_override(_load_gui_state(), knob_id) or ""
        if not param:
            return {
                "schema": 1,
                "success": False,
                "knob_id": knob_id,
                "error": "No kernel parameter specified",
            }

        distro = detect_distro()
        if distro.boot_system == "unknown" or not distro.kernel_cmdline_file:
            return {
                "schema": 1,
                "success": False,
                "knob_id": knob_id,
                "error": f"Unknown boot system for {distro.distro_id}; cannot reset kernel cmdline",
            }

        cmdline_path = distro.kernel_cmdline_file
        meta = next((m for m in manifest.get("backups", []) if m.get("path") == cmdline_path), None)
        if not meta:
            return {
                "schema": 1,
                "success": False,
                "knob_id": knob_id,
                "error": "Kernel cmdline backup not found for this knob",
            }

        paths = default_paths()
        tx_root = Path(paths.var_lib_dir if scope == "root" else paths.user_state_dir) / "transactions" / txid
        backup_key = meta.get("backup_key")
        backup_path = tx_root / "backups" / backup_key if backup_key else None
        if not backup_path or not backup_path.exists():
            return {
                "schema": 1,
                "success": False,
                "knob_id": knob_id,
                "error": "Kernel cmdline backup file missing",
            }

        try:
            backup_content = backup_path.read_text(encoding="utf-8")
        except Exception as exc:
            return {
                "schema": 1,
                "success": False,
                "knob_id": knob_id,
                "error": f"Failed to read kernel cmdline backup: {exc}",
            }

        try:
            current_content = Path(cmdline_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            current_content = ""
        except Exception as exc:
            return {
                "schema": 1,
                "success": False,
                "knob_id": knob_id,
                "error": f"Failed to read kernel cmdline file: {exc}",
            }

        def _tokens_for_content(content: str, boot_system: str) -> list[str]:
            if boot_system in ("grub2-bls", "bls", "systemd-boot"):
                return content.strip().split()
            if boot_system == "grub2":
                for line in content.splitlines():
                    if not line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                        continue
                    _, _, rhs = line.partition("=")
                    rhs = rhs.strip()
                    if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                        rhs = rhs[1:-1]
                    try:
                        return shlex.split(rhs)
                    except Exception:
                        return rhs.split()
                return []
            return content.strip().split()

        def _param_present(param_str: str, tokens: list[str]) -> bool:
            if not param_str:
                return False
            if "=" in param_str:
                return any(t == param_str for t in tokens)
            return any(t == param_str or t.startswith(param_str + "=") for t in tokens)

        want_present = _param_present(param, _tokens_for_content(backup_content, distro.boot_system))

        def _apply_param(tokens: list[str], present: bool) -> list[str]:
            if present:
                if not _param_present(param, tokens):
                    tokens.append(param)
                return tokens
            if "=" in param:
                return [t for t in tokens if t != param]
            return [t for t in tokens if t != param and not t.startswith(param + "=")]

        updated = False
        current_tokens = _tokens_for_content(current_content, distro.boot_system)
        param_in_current = _param_present(param, current_tokens)
        if distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
            tokens = _tokens_for_content(current_content, distro.boot_system)
            new_tokens = _apply_param(tokens, want_present)
            new_line = " ".join(new_tokens).strip()
            new_content = (new_line + "\n") if new_line else ""
            if new_content != current_content:
                updated = True
                try:
                    Path(cmdline_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(cmdline_path).write_text(new_content, encoding="utf-8")
                except Exception as exc:
                    return {
                        "schema": 1,
                        "success": False,
                        "knob_id": knob_id,
                        "error": f"Failed to write kernel cmdline file: {exc}",
                    }
        elif distro.boot_system == "grub2":
            lines = current_content.splitlines()
            out_lines: list[str] = []
            found = False
            for line in lines:
                if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                    tokens = _tokens_for_content(line, "grub2")
                    new_tokens = _apply_param(tokens, want_present)
                    new_rhs = " ".join(new_tokens)
                    out_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{new_rhs}"')
                    found = True
                else:
                    out_lines.append(line)
            if not found:
                if want_present:
                    out_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{param}"')
                    found = True
                else:
                    out_lines.append('GRUB_CMDLINE_LINUX_DEFAULT=""')
                    found = True
            new_content = "\n".join(out_lines)
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            if new_content != current_content:
                updated = True
                try:
                    Path(cmdline_path).write_text(new_content, encoding="utf-8")
                except Exception as exc:
                    return {
                        "schema": 1,
                        "success": False,
                        "knob_id": knob_id,
                        "error": f"Failed to write kernel cmdline file: {exc}",
                    }
        else:
            return {
                "schema": 1,
                "success": False,
                "knob_id": knob_id,
                "error": f"Unsupported boot system: {distro.boot_system}",
            }

        if not updated and want_present and param_in_current:
            return {
                "schema": 1,
                "success": False,
                "knob_id": knob_id,
                "error": f"Force reset available: reset did not remove {param} from {cmdline_path}",
            }

        restored: list[str] = [cmdline_path]
        errors: list[str] = []
        if updated and distro.kernel_cmdline_update_cmd:
            result = subprocess.run(distro.kernel_cmdline_update_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                cmd_str = " ".join(distro.kernel_cmdline_update_cmd)
                detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                errors.append(
                    "Bootloader update failed after reset.\n"
                    f"Command: {cmd_str}\n"
                    f"Error: {detail}\n"
                    "Run the command manually and reboot."
                )
            else:
                restored.append(f"(bootloader update: {' '.join(distro.kernel_cmdline_update_cmd)})")

        return {
            "schema": 1,
            "success": len(errors) == 0,
            "knob_id": knob_id,
            "txid": txid,
            "scope": scope,
            "restored": restored,
            "errors": errors,
        }

    if knob and knob.impl and knob.impl.kind == "rtirq_config":
        from audioknob_gui.core.rtirq import strip_rtirq_block
        from audioknob_gui.worker.ops import read_os_release, resolve_rtirq_config_path

        distro_id = read_os_release().get("ID", "")
        cfg_path = resolve_rtirq_config_path(distro_id)
        meta = next((m for m in manifest.get("backups", []) if m.get("path") == cfg_path), None)
        we_created = bool(meta.get("we_created")) if isinstance(meta, dict) else False

        restored: list[str] = []
        errors: list[str] = []
        unit = str(knob.impl.params.get("unit", "rtirq.service")) if knob.impl else "rtirq.service"
        pre_not_found = False
        for e in effects_for_knob:
            if e.get("kind") != "systemd_unit_toggle":
                continue
            pre = e.get("pre") or {}
            pre_enabled = str(pre.get("enabled", "")).strip().lower()
            if "not-found" in pre_enabled or "not found" in pre_enabled or "no such file" in pre_enabled:
                pre_not_found = True
                break

        try:
            current = ""
            try:
                current = Path(cfg_path).read_text(encoding="utf-8")
            except FileNotFoundError:
                current = ""
            updated = strip_rtirq_block(current)
            if updated != current:
                if not updated.strip() and we_created and Path(cfg_path).exists():
                    Path(cfg_path).unlink()
                else:
                    Path(cfg_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(cfg_path).write_text(updated, encoding="utf-8")
                restored.append(cfg_path)
        except Exception as exc:
            errors.append(f"Failed to update rtirq config: {exc}")

        try:
            for e in effects_for_knob:
                if e.get("kind") == "systemd_unit_toggle":
                    worker_ops.systemd_restore(e)
            if any(e.get("kind") == "systemd_unit_toggle" for e in effects_for_knob):
                restored.append("(systemd effects)")
        except Exception as exc:
            errors.append(f"Failed to restore systemd effects: {exc}")

        # If the service didn't exist when this knob was applied (unit not found),
        # a later package install can leave the unit enabled. Try to disable it
        # automatically so normal reset remains seamless.
        if not errors and pre_not_found and unit:
            try:
                r = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True)
                enabled = (r.stdout or r.stderr or "").strip()
                if enabled in ("enabled", "static", "indirect"):
                    disable_result = subprocess.run(
                        ["systemctl", "disable", "--now", unit],
                        capture_output=True,
                        text=True,
                    )
                    verify = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True)
                    enabled_after = (verify.stdout or verify.stderr or "").strip()
                    if enabled_after in ("enabled", "static", "indirect"):
                        detail = (
                            disable_result.stderr.strip()
                            or disable_result.stdout.strip()
                            or "unknown error"
                        )
                        return {
                            "schema": 1,
                            "success": False,
                            "knob_id": knob_id,
                            "txid": txid,
                            "scope": scope,
                            "error": f"Force reset available: reset did not disable {unit} ({detail})",
                        }
                    restored.append(f"(auto-disabled {unit} added after initial apply)")
            except Exception:
                pass

        return {
            "schema": 1,
            "success": len(errors) == 0,
            "knob_id": knob_id,
            "txid": txid,
            "scope": scope,
            "restored": restored,
            "errors": errors,
        }

    paths = default_paths()
    tx_root = Path(paths.var_lib_dir if scope == "root" else paths.user_state_dir) / "transactions" / txid

    # Create a Transaction object for backup restore
    from audioknob_gui.core.transaction import Transaction
    tx = Transaction(txid=txid, root=tx_root)

    # Restore only the backups from this knob's transaction
    restored = []
    errors = []
    seen_paths: set[str] = set()
    for meta in backups_for_knob:
        file_path = meta.get("path", "")
        if not file_path or file_path in seen_paths:
            continue
        seen_paths.add(file_path)
        success, message = reset_file_to_default(meta, tx)
        if success:
            restored.append(file_path)
        else:
            errors.append(message)

    # Also restore effects if present
    effects = effects_for_knob

    if scope == "root" and os.geteuid() == 0:
        sysfs = [e for e in effects if e.get("kind") == "sysfs_write"]
        systemd = [e for e in effects if e.get("kind") == "systemd_unit_toggle"]
        irq_affinity = [e for e in effects if e.get("kind") == "irq_affinity"]

        try:
            sysfs_errors = restore_sysfs(sysfs)
            for e in systemd:
                worker_ops.systemd_restore(e)
            irq_errors = restore_irq_affinity(irq_affinity)
            power_errors: list[str] = []
            power_restored = _restore_power_profile_effects(effects, power_errors)
            if sysfs or systemd or irq_affinity or power_restored:
                restored.append(
                    f"(effects: {len(sysfs)} sysfs, {len(systemd)} systemd, {len(irq_affinity)} irq, {power_restored} power)"
                )
            if power_errors:
                errors.extend(power_errors)
            if sysfs_errors:
                errors.extend(sysfs_errors)
            if irq_errors:
                errors.extend(irq_errors)
        except Exception as ex:
            errors.append(f"Failed to restore effects: {ex}")

    # User-scope effects
    from audioknob_gui.worker.ops import user_service_restore, baloo_enable

    user_effects_restored = 0
    for e in effects:
        try:
            if e.get("kind") == "user_service_mask":
                user_service_restore(e)
                user_effects_restored += 1
            elif e.get("kind") == "baloo_disable":
                baloo_enable()
                user_effects_restored += 1
        except Exception as ex:
            errors.append(f"Failed to restore user effect: {ex}")

    if user_effects_restored:
        restored.append(f"(user effects: {user_effects_restored})")

    # If kernel cmdline was restored, update the bootloader so changes stick after reboot.
    if scope == "root" and os.geteuid() == 0:
        try:
            from audioknob_gui.worker.ops import detect_distro
            distro = detect_distro()
            needs_bootloader_update = any(e.get("kind") == "kernel_cmdline" for e in effects)
            if distro.kernel_cmdline_file and distro.kernel_cmdline_file in restored:
                needs_bootloader_update = True
            if needs_bootloader_update:
                if distro.kernel_cmdline_update_cmd:
                    result = subprocess.run(
                        distro.kernel_cmdline_update_cmd,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        cmd_str = " ".join(distro.kernel_cmdline_update_cmd)
                        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                        errors.append(
                            "Bootloader update failed after reset.\n"
                            f"Command: {cmd_str}\n"
                            f"Error: {detail}\n"
                            "Run the command manually and reboot."
                        )
                    else:
                        restored.append(f"(bootloader update: {' '.join(distro.kernel_cmdline_update_cmd)})")
                elif distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
                    errors.append(
                        "Kernel cmdline reset but no bootloader update command is configured.\n"
                        "Run sdbootutil update-all-entries and reboot."
                    )
                elif distro.boot_system == "grub2":
                    errors.append(
                        "Kernel cmdline reset but no bootloader update command is configured.\n"
                        "Run grub2-mkconfig -o /boot/grub2/grub.cfg (or your distro's update-grub) and reboot."
                    )
        except Exception as ex:
            errors.append(f"Bootloader update check failed: {ex}")

    return {
        "schema": 1,
        "success": len(errors) == 0,
        "knob_id": knob_id,
        "txid": txid,
        "scope": scope,
        "restored": restored,
        "errors": errors,
    }


def cmd_restore_knob(args: argparse.Namespace) -> int:
    """Restore a specific knob to its original state."""
    result = _restore_knob_once(args.knob_id)
    _log_audit_event("restore-knob", result)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


def cmd_restore_many(args: argparse.Namespace) -> int:
    """Restore multiple knobs to their original state."""
    results = []
    restored: list[str] = []
    errors: list[str] = []

    for knob_id in args.knob:
        result = _restore_knob_once(knob_id)
        results.append(result)
        if result.get("success"):
            restored.append(knob_id)
            continue
        if result.get("errors"):
            for err in result["errors"]:
                errors.append(f"{knob_id}: {err}")
        elif result.get("error"):
            errors.append(f"{knob_id}: {result['error']}")
        else:
            errors.append(f"{knob_id}: restore failed")

    success = len(errors) == 0
    payload = {
        "schema": 1,
        "success": success,
        "restored": restored,
        "results": results,
        "errors": errors,
    }
    _log_audit_event("restore-many", payload)
    print(json.dumps(payload, indent=2))
    return 0 if success else 1


def _force_reset_systemd(unit: str, action: str) -> tuple[bool, str]:
    from audioknob_gui.worker.ops import systemd_disable_now, systemd_enable_now

    if action in ("disable_now", "disable"):
        systemd_enable_now(unit, start=True)
        return True, f"Enabled {unit}"
    if action in ("enable_now", "enable"):
        systemd_disable_now(unit)
        return True, f"Disabled {unit}"
    return False, f"Unsupported systemd action: {action}"


def _force_reset_remove_lines(
    path_str: str,
    remove_lines: list[str],
    *,
    remove_prefixes: list[str] | None = None,
) -> tuple[bool, str]:
    path = Path(path_str).expanduser()
    if not path.exists():
        return True, f"Missing {path} (already default)"

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return False, f"Failed to read {path}: {e}"

    wanted = [str(x) for x in remove_lines if str(x).strip() != ""]
    prefixes = [str(x).strip() for x in (remove_prefixes or []) if str(x).strip()]
    if not wanted and not prefixes:
        return False, "No reset lines provided"

    new_lines: list[str] = []
    for line in lines:
        if line in wanted:
            continue
        if any(line.strip().startswith(prefix) for prefix in prefixes):
            continue
        new_lines.append(line)
    removed = len(lines) - len(new_lines)
    if removed == 0:
        return True, f"No matching lines in {path}"

    if not any(line.strip() for line in new_lines):
        try:
            path.unlink()
        except Exception as e:
            return False, f"Failed to delete {path}: {e}"
        return True, f"Deleted {path}"

    try:
        path.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
    except Exception as e:
        return False, f"Failed to write {path}: {e}"

    return True, f"Removed {removed} line(s) from {path}"


def _force_reset_udev_rule(path_str: str, content: str) -> tuple[bool, str]:
    path = Path(path_str).expanduser()
    if not path.exists():
        return True, f"Missing {path} (already default)"

    try:
        current = path.read_text(encoding="utf-8").strip()
    except Exception as e:
        return False, f"Failed to read {path}: {e}"

    expected = str(content).strip()
    if current != expected:
        return False, f"{path} does not match expected audioknob rule"

    try:
        path.unlink()
    except Exception as e:
        return False, f"Failed to delete {path}: {e}"

    try:
        subprocess.run(["udevadm", "control", "--reload-rules"], check=False, capture_output=True)
        subprocess.run(["udevadm", "trigger"], check=False, capture_output=True)
    except Exception:
        pass

    return True, f"Deleted {path}"


def _force_reset_pipewire_conf(path_str: str) -> tuple[bool, str]:
    path = Path(path_str).expanduser()
    if not path.exists():
        return True, f"Missing {path} (already default)"

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Failed to read {path}: {e}"

    if "# audioknob-gui PipeWire configuration" not in content.splitlines()[:3]:
        return False, f"{path} does not appear to be an audioknob config"

    try:
        path.unlink()
    except Exception as e:
        return False, f"Failed to delete {path}: {e}"

    try:
        subprocess.run(
            ["systemctl", "--user", "restart", "pipewire.service", "pipewire-pulse.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        pass

    return True, f"Deleted {path}"


def _force_reset_wireplumber_conf(path_str: str) -> tuple[bool, str]:
    path = Path(path_str).expanduser()
    if not path.exists():
        return True, f"Missing {path} (already default)"

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Failed to read {path}: {e}"

    if "# audioknob-gui WirePlumber ALSA configuration" not in content.splitlines()[:3]:
        return False, f"{path} does not appear to be an audioknob config"

    try:
        path.unlink()
    except Exception as e:
        return False, f"Failed to delete {path}: {e}"

    try:
        subprocess.run(
            ["systemctl", "--user", "restart", "wireplumber.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        pass

    return True, f"Deleted {path}"


def _force_reset_rtirq_config(params: dict) -> tuple[bool, str]:
    from audioknob_gui.core.rtirq import strip_rtirq_block
    from audioknob_gui.worker.ops import read_os_release, resolve_rtirq_config_path, systemd_disable_now

    distro_id = read_os_release().get("ID", "")
    cfg_path = resolve_rtirq_config_path(distro_id)
    path = Path(cfg_path)

    try:
        before = path.read_text(encoding="utf-8") if path.exists() else ""
    except Exception as exc:
        return False, f"Failed to read rtirq config: {exc}"

    after = strip_rtirq_block(before)
    try:
        if after != before:
            if not after.strip() and path.exists():
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(after, encoding="utf-8")
    except Exception as exc:
        return False, f"Failed to update rtirq config: {exc}"

    unit = str(params.get("unit", "rtirq.service"))
    try:
        systemd_disable_now(unit)
    except Exception:
        pass

    return True, "Removed rtirq config block and disabled rtirq service"


def _force_reset_user_services(services: list[str]) -> tuple[bool, str]:
    from audioknob_gui.worker.ops import resolve_user_services, user_service_unmask

    resolved = resolve_user_services(services)
    if not resolved:
        return True, "No matching user services found"

    user_service_unmask(resolved)
    return True, f"Unmasked {len(resolved)} user service(s)"


def _force_reset_baloo_disable() -> tuple[bool, str]:
    from audioknob_gui.worker.ops import baloo_enable

    try:
        baloo_enable()
    except Exception as e:
        return False, f"Failed to enable Baloo: {e}"
    return True, "Enabled Baloo"


def _force_reset_sysfs_glob(glob_spec: str | list[str]) -> tuple[bool, str]:
    from audioknob_gui.worker.ops import _expand_sysfs_globs

    targets = _expand_sysfs_globs(glob_spec)
    if not targets:
        return False, f"No sysfs entries found for: {glob_spec}"

    errors: list[str] = []
    updated = 0
    for path_str in targets:
        path = Path(path_str)
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except Exception as e:
            errors.append(f"{path_str}: {e}")
            continue
        if not raw:
            errors.append(f"{path_str}: empty sysfs value")
            continue
        tokens = raw.split()
        bracketed = [t for t in tokens if t.startswith("[") and t.endswith("]")]
        if not bracketed:
            errors.append(f"{path_str}: unable to infer default from '{raw}'")
            continue
        default = bracketed[0].strip("[]")
        try:
            path.write_text(default + "\n", encoding="utf-8")
            updated += 1
        except Exception as e:
            errors.append(f"{path_str}: {e}")

    if errors:
        return False, "; ".join(errors)
    suffix = "entry" if updated == 1 else "entries"
    return True, f"Reset {updated} sysfs {suffix}"


def _list_powerprofilesctl_profiles(cmd: str) -> list[str]:
    try:
        res = subprocess.run([cmd, "list"], capture_output=True, text=True)
    except Exception:
        return []
    if res.returncode != 0:
        return []
    profiles: list[str] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        if line.startswith("*"):
            line = line[1:].strip()
        name = line.split(":", 1)[0].strip()
        if name:
            profiles.append(name)
    seen: set[str] = set()
    out: list[str] = []
    for name in profiles:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _list_tuned_profiles(cmd: str) -> list[str]:
    try:
        res = subprocess.run([cmd, "list"], capture_output=True, text=True)
    except Exception:
        return []
    if res.returncode != 0:
        return []
    profiles: list[str] = []
    for line in res.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        low = text.lower()
        if low.startswith("available profiles") or low.startswith("current active profile"):
            continue
        text = text.lstrip("-* ").strip()
        if not text:
            continue
        name = text.split()[0].strip()
        if name and name not in ("-", "*"):
            profiles.append(name)
    seen: set[str] = set()
    out: list[str] = []
    for name in profiles:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _force_reset_power_profile(params: dict[str, Any]) -> tuple[bool, str]:
    backend = worker_ops.select_power_profile_backend(params)
    if not backend:
        return False, "No power profile backend found (powerprofilesctl or tuned-adm)."

    target = "balanced"
    backend_name = str(backend.get("backend", "")).strip()
    cmd = str(backend.get("cmd", "")).strip()
    if not backend_name or not cmd:
        return False, "Power profile backend metadata is incomplete."

    if backend_name == "powerprofilesctl":
        available = _list_powerprofilesctl_profiles(cmd)
        if available and target not in available:
            return False, (
                "Cannot safely reset power profile: "
                f"'{target}' is not available for powerprofilesctl "
                f"(available: {', '.join(available)})."
            )
        result = subprocess.run([cmd, "set", target], capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            return False, f"Failed to set power profile '{target}': {detail}"
        current = worker_ops.read_power_profile(backend_name, cmd)
        if current and current != target:
            return False, f"Power profile verification failed (current: {current}, target: {target})."
        return True, f"Set power profile to {target} via powerprofilesctl"

    if backend_name == "tuned":
        available = _list_tuned_profiles(cmd)
        if available and target not in available:
            return False, (
                "Cannot safely reset tuned profile: "
                f"'{target}' is not available (available: {', '.join(available)})."
            )
        result = subprocess.run([cmd, "profile", target], capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            return False, f"Failed to set tuned profile '{target}': {detail}"
        current = worker_ops.read_power_profile(backend_name, cmd)
        if current and current != target:
            return False, f"Tuned profile verification failed (current: {current}, target: {target})."
        return True, f"Set tuned profile to {target}"

    return False, f"Unsupported power profile backend: {backend_name}"


def _normalize_irq_mask(raw: str) -> str:
    text = str(raw).strip().lower().replace(",", "")
    text = text.lstrip("0")
    return text or "0"


def _force_reset_irq_affinity(params: dict[str, Any]) -> tuple[bool, str]:
    from audioknob_gui.core.irq import is_irq_affinity_writable, list_irqs

    default_mask_path = Path("/proc/irq/default_smp_affinity")
    if not default_mask_path.exists():
        return False, "Missing /proc/irq/default_smp_affinity"
    try:
        default_mask = default_mask_path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        return False, f"Failed to read /proc/irq/default_smp_affinity: {exc}"
    if not default_mask:
        return False, "Kernel default IRQ affinity mask is empty"

    errors: list[str] = []
    updated = 0
    unchanged = 0
    skipped_read_only = 0

    for irq in list_irqs():
        if not is_irq_affinity_writable(irq):
            skipped_read_only += 1
            continue
        affinity_path = Path(f"/proc/irq/{irq}/smp_affinity")
        if not affinity_path.exists():
            continue
        try:
            current = affinity_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            errors.append(f"IRQ {irq}: failed to read smp_affinity ({exc})")
            continue
        if _normalize_irq_mask(current) == _normalize_irq_mask(default_mask):
            unchanged += 1
            continue
        try:
            affinity_path.write_text(default_mask + "\n", encoding="utf-8")
            updated += 1
        except Exception as exc:
            errors.append(f"IRQ {irq}: failed to write default mask ({exc})")

    unit = str(params.get("persist_unit", "")).strip() or "audioknob-irq-pinning.service"
    unit_disable_note = ""
    if unit:
        try:
            disable_res = subprocess.run(
                ["systemctl", "disable", "--now", unit],
                check=False,
                capture_output=True,
                text=True,
            )
            if disable_res.returncode == 0:
                unit_disable_note = f"disabled {unit}"
            else:
                detail = (disable_res.stderr or disable_res.stdout or "").strip()
                detail_low = detail.lower()
                if any(token in detail_low for token in ("not-found", "not found", "not loaded", "no such file")):
                    unit_disable_note = f"{unit} not found"
                elif detail:
                    errors.append(f"Failed to disable {unit}: {detail}")
                else:
                    errors.append(f"Failed to disable {unit}")
        except Exception as exc:
            errors.append(f"Failed to disable {unit}: {exc}")

    unit_path_raw = str(params.get("persist_unit_path", "")).strip()
    unit_path = Path(unit_path_raw) if unit_path_raw else Path("/etc/systemd/system") / unit
    unit_removed = False
    if unit_path.exists():
        try:
            unit_text = unit_path.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"Failed to read {unit_path}: {exc}")
            unit_text = ""
        if unit_text:
            owned_markers = (
                "Description=Apply audioknob IRQ pinning",
                "ExecStart=/usr/libexec/audioknob-gui-worker apply irq_pinning",
            )
            if all(marker in unit_text for marker in owned_markers):
                try:
                    unit_path.unlink()
                    unit_removed = True
                    subprocess.run(["systemctl", "daemon-reload"], check=False, capture_output=True, text=True)
                except Exception as exc:
                    errors.append(f"Failed to remove {unit_path}: {exc}")

    state_path_raw = str(params.get("persist_state_path", "")).strip()
    state_path = Path(state_path_raw) if state_path_raw else Path(default_paths().var_lib_dir) / "state.json"
    state_cleared = False
    if state_path.exists():
        try:
            raw = state_path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
            if not isinstance(data, dict):
                raise ValueError("state payload is not a JSON object")
            changed = False
            for key, value in (
                ("irq_pinning_devices", []),
                ("irq_pinning_cpu_cores", None),
                ("irq_housekeeping_auto", True),
                ("irq_housekeeping_cores", []),
            ):
                if data.get(key) != value:
                    data[key] = value
                    changed = True
            if changed:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                state_cleared = True
        except Exception as exc:
            errors.append(f"Failed to update IRQ state file {state_path}: {exc}")

    if errors:
        return False, "; ".join(errors)

    parts = [
        f"Reset {updated} IRQ affinities to kernel default mask",
        f"{unchanged} already default",
        f"{skipped_read_only} read-only skipped",
    ]
    if unit_disable_note:
        parts.append(unit_disable_note)
    if unit_removed:
        parts.append(f"removed {unit_path}")
    if state_cleared:
        parts.append(f"cleared IRQ pinning state in {state_path}")
    return True, "; ".join(parts)


def _looks_like_audioknob_post_start_script(content: str) -> bool:
    head = "\n".join(content.splitlines()[:5])
    return "Generated by audioknob-gui. Do not edit." in head and "taskset -apc" in content


def _force_reset_qjackctl_server_prefix(params: dict[str, Any]) -> tuple[bool, str]:
    from audioknob_gui.core.qjackctl import (
        default_post_start_script_path,
        ensure_server_has_flags,
        ensure_server_prefix,
        read_config,
        write_config_with_server_update,
    )

    path = Path(str(params.get("path", "~/.config/rncbc.org/QjackCtl.conf"))).expanduser()
    if not path.exists():
        return True, f"Missing {path} (already default)"

    try:
        cfg = read_config(path)
    except Exception as exc:
        return False, f"Failed to parse QjackCtl config {path}: {exc}"

    before_cmd = cfg.server_cmd or "jackd"
    before_prefix = cfg.server_prefix or ""
    after_cmd = ensure_server_has_flags(
        before_cmd,
        ensure_rt=False,
        ensure_priority=False,
        cpu_cores="",
    )
    after_prefix = ensure_server_prefix(before_prefix, cpu_cores="")
    preset = cfg.def_preset.strip() if cfg.def_preset else ""
    target_preset = preset or None

    try:
        write_config_with_server_update(
            path,
            target_preset,
            after_cmd,
            server_prefix=after_prefix,
            realtime=False,
            priority=0,
            mirror_unscoped=True,
            post_startup_enabled=False,
            post_startup_shell="",
        )
    except Exception as exc:
        return False, f"Failed to write QjackCtl config {path}: {exc}"

    script_path = default_post_start_script_path()
    script_removed = False
    if script_path.exists():
        try:
            script_text = script_path.read_text(encoding="utf-8")
            if _looks_like_audioknob_post_start_script(script_text):
                script_path.unlink()
                script_removed = True
        except Exception as exc:
            return False, f"Failed to update QjackCtl post-start script {script_path}: {exc}"

    changes: list[str] = []
    if before_cmd != after_cmd:
        changes.append("server command")
    if before_prefix != after_prefix:
        changes.append("server prefix")
    if cfg.realtime is True:
        changes.append("realtime flag")
    if cfg.priority not in (None, 0):
        changes.append("priority")
    if cfg.post_startup_enabled or (cfg.post_startup_shell or "").strip():
        changes.append("post-start hook")
    if script_removed:
        changes.append("generated post-start script")

    if not changes:
        return True, f"No QjackCtl RT/taskset changes detected in {path}"
    return True, f"Reset QjackCtl settings ({', '.join(changes)})"


def _force_reset_wpctl_profile(params: dict[str, Any]) -> tuple[bool, str]:
    from audioknob_gui.platform.packages import which_command

    device_id = params.get("device_id")
    if device_id is None or str(device_id).strip() == "":
        return True, "No configured device id for Pro Audio profile (already default)"

    cmd = which_command("wpctl")
    if not cmd:
        return False, "wpctl not found; cannot inspect current profile safely"

    try:
        inspect = subprocess.run(
            [cmd, "inspect", str(device_id)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return False, f"Failed to inspect PipeWire device {device_id}: {exc}"
    if inspect.returncode != 0:
        detail = inspect.stderr.strip() or inspect.stdout.strip() or "wpctl inspect failed"
        return False, f"Failed to inspect PipeWire device {device_id}: {detail}"

    current = ""
    pro_flag = False
    for line in (inspect.stdout or "").splitlines():
        clean = line.strip().lstrip("* ").strip()
        if not clean:
            continue
        low = clean.lower()
        if low.startswith("active profile:"):
            current = clean.split(":", 1)[1].strip()
        if low.startswith("device.profile.pro"):
            _, _, value = clean.partition("=")
            pro_flag = value.strip().strip('"').lower() in ("true", "1", "yes")

    current_low = current.lower()
    if pro_flag or "pro audio" in current_low or "pro-audio" in current_low:
        return False, (
            "Cannot safely force-reset Pro Audio profile without a recorded transaction. "
            "Select a non-Pro profile manually, or restore from transaction history."
        )
    return True, "Device is not using Pro Audio profile; no force reset needed"


def _kernel_cmdline_tokens(text: str, boot_system: str) -> list[str]:
    if boot_system in ("grub2-bls", "bls", "systemd-boot"):
        return text.strip().split()
    if boot_system == "grub2":
        for line in text.splitlines():
            if not line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                continue
            _, _, rhs = line.partition("=")
            rhs = rhs.strip()
            if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                rhs = rhs[1:-1]
            try:
                return shlex.split(rhs)
            except Exception:
                return rhs.split()
        return []
    return text.strip().split()


def _kernel_cmdline_param_present(param: str, tokens: list[str]) -> bool:
    if not param:
        return False
    if "=" in param:
        return any(t == param for t in tokens)
    return any(t == param or t.startswith(param + "=") for t in tokens)


def _force_reset_kernel_cmdline_params(params: set[str], *, run_update: bool = True) -> tuple[bool, str]:
    from audioknob_gui.worker.ops import detect_distro

    params = {p for p in params if p}
    if not params:
        return True, "No kernel params to remove"

    distro = detect_distro()
    if distro.boot_system == "unknown" or not distro.kernel_cmdline_file:
        return False, "No kernel cmdline file detected"

    path = Path(distro.kernel_cmdline_file)
    try:
        before = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Failed to read {path}: {e}"

    def _remove_params(tokens: list[str]) -> list[str]:
        out: list[str] = []
        for token in tokens:
            keep = True
            for param in params:
                if "=" in param:
                    if token == param:
                        keep = False
                        break
                else:
                    if token == param or token.startswith(param + "="):
                        keep = False
                        break
            if keep:
                out.append(token)
        return out

    after = before
    if distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
        tokens = before.strip().split()
        new_tokens = _remove_params(tokens)
        after = " ".join(new_tokens).strip() + ("\n" if before.endswith("\n") or new_tokens else "")
    elif distro.boot_system == "grub2":
        lines = before.splitlines()
        out_lines: list[str] = []
        updated = False
        for line in lines:
            if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                _, _, rhs = line.partition("=")
                rhs = rhs.strip()
                if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                    inner = rhs[1:-1]
                else:
                    inner = rhs
                try:
                    tokens = shlex.split(inner)
                except Exception:
                    tokens = inner.split()
                new_tokens = _remove_params(tokens)
                new_rhs = " ".join(new_tokens)
                out_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{new_rhs}"')
                updated = True
            else:
                out_lines.append(line)
        if not updated:
            return False, "GRUB_CMDLINE_LINUX_DEFAULT not found"
        after = "\n".join(out_lines)
        if after and not after.endswith("\n"):
            after += "\n"
    else:
        return False, f"Unsupported boot system: {distro.boot_system}"

    try:
        path.write_text(after, encoding="utf-8")
    except Exception as e:
        return False, f"Failed to write {path}: {e}"

    if run_update and distro.kernel_cmdline_update_cmd:
        try:
            subprocess.run(distro.kernel_cmdline_update_cmd, check=False, capture_output=True, text=True)
        except Exception:
            pass

    removed = ", ".join(sorted(params))
    return True, f"Removed {removed} from {path}"


def _force_reset_kernel_cmdline(param: str) -> tuple[bool, str]:
    from audioknob_gui.worker.ops import detect_distro

    distro = detect_distro()
    if distro.boot_system == "unknown" or not distro.kernel_cmdline_file:
        return False, "No kernel cmdline file detected"

    path = Path(distro.kernel_cmdline_file)
    try:
        before = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Failed to read {path}: {e}"

    def _remove_param(tokens: list[str]) -> list[str]:
        if not param:
            return tokens
        if "=" in param:
            return [t for t in tokens if t != param]
        return [t for t in tokens if t != param and not t.startswith(param + "=")]

    after = before
    if distro.boot_system in ("grub2-bls", "bls", "systemd-boot"):
        tokens = before.strip().split()
        new_tokens = _remove_param(tokens)
        after = " ".join(new_tokens).strip() + ("\n" if before.endswith("\n") or new_tokens else "")
    elif distro.boot_system == "grub2":
        lines = before.splitlines()
        out_lines: list[str] = []
        updated = False
        for line in lines:
            if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                _, _, rhs = line.partition("=")
                rhs = rhs.strip()
                if rhs.startswith('"') and rhs.endswith('"') and len(rhs) >= 2:
                    inner = rhs[1:-1]
                else:
                    inner = rhs
                try:
                    tokens = shlex.split(inner)
                except Exception:
                    tokens = inner.split()
                new_tokens = _remove_param(tokens)
                new_rhs = " ".join(new_tokens)
                out_lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{new_rhs}"')
                updated = True
            else:
                out_lines.append(line)
        if not updated:
            return False, "GRUB_CMDLINE_LINUX_DEFAULT not found"
        after = "\n".join(out_lines)
        if after and not after.endswith("\n"):
            after += "\n"
    else:
        return False, f"Unsupported boot system: {distro.boot_system}"

    try:
        path.write_text(after, encoding="utf-8")
    except Exception as e:
        return False, f"Failed to write {path}: {e}"

    if distro.kernel_cmdline_update_cmd:
        try:
            subprocess.run(distro.kernel_cmdline_update_cmd, check=False, capture_output=True, text=True)
        except Exception:
            pass

    return True, f"Removed {param} from {path}"


def cmd_force_reset_knob(args: argparse.Namespace) -> int:
    knob_id = args.knob_id
    reg = load_registry(args.registry)
    by_id = {k.id: k for k in reg}
    k = by_id.get(knob_id)
    if k is None:
        payload = {"schema": 1, "success": False, "error": f"Unknown knob id: {knob_id}", "knob_id": knob_id}
        _log_audit_event("force-reset-knob", payload)
        print(json.dumps(payload, indent=2))
        return 1

    if k.requires_root and os.geteuid() != 0:
        payload = {
            "schema": 1,
            "success": False,
            "error": f"Knob {knob_id} requires root; run with pkexec",
            "knob_id": knob_id,
        }
        _log_audit_event("force-reset-knob", payload)
        print(json.dumps(payload, indent=2))
        return 1

    if not k.impl:
        payload = {"schema": 1, "success": False, "error": "Knob not implemented", "knob_id": knob_id}
        _log_audit_event("force-reset-knob", payload)
        print(json.dumps(payload, indent=2))
        return 1

    kind = k.impl.kind
    params = k.impl.params
    state = _load_gui_state()
    power_profile_backend = _power_profile_backend_override(state)
    if knob_id == PIPEWIRE_RT_LIMITS_GROUP and kind == "pam_limits_audio_group":
        params = _apply_pipewire_state_overrides(knob_id, params, state)
    if kind == "wpctl_profile" and knob_id.startswith("pipewire_"):
        params = _apply_pipewire_state_overrides(knob_id, params, state)
    if (
        power_profile_backend is not None
        and knob_id == POWER_PROFILE_PERFORMANCE
        and kind == "power_profile"
    ):
        new_params = dict(params)
        new_params["backend"] = power_profile_backend
        params = new_params
    params = _apply_root_state_overrides(knob_id, params, state)
    success = False
    message = ""

    if kind == "systemd_unit_toggle":
        unit = str(params.get("unit", ""))
        action = str(params.get("action", ""))
        success, message = _force_reset_systemd(unit, action)
    elif kind == "pam_limits_audio_group":
        path = str(params.get("path", ""))
        lines = params.get("lines", [])
        success, message = _force_reset_remove_lines(path, lines)
    elif kind == "sysctl_conf":
        path = str(params.get("path", ""))
        lines = params.get("lines", [])
        replace_prefixes = params.get("replace_prefixes", [])
        success, message = _force_reset_remove_lines(
            path,
            lines,
            remove_prefixes=list(replace_prefixes) if isinstance(replace_prefixes, list) else None,
        )
    elif kind == "udev_rule":
        path = str(params.get("path", ""))
        content = str(params.get("content", ""))
        success, message = _force_reset_udev_rule(path, content)
    elif kind == "sysfs_glob_kv":
        glob_spec = params.get("glob", "")
        success, message = _force_reset_sysfs_glob(glob_spec)
    elif kind == "kernel_cmdline":
        param = str(params.get("param", ""))
        success, message = _force_reset_kernel_cmdline(param)
    elif kind == "pipewire_conf":
        path = str(params.get("path", ""))
        success, message = _force_reset_pipewire_conf(path)
    elif kind == "wireplumber_conf":
        path = str(params.get("path", ""))
        success, message = _force_reset_wireplumber_conf(path)
    elif kind == "rtirq_config":
        success, message = _force_reset_rtirq_config(params)
    elif kind == "irq_affinity":
        success, message = _force_reset_irq_affinity(params)
    elif kind == "power_profile":
        success, message = _force_reset_power_profile(params)
    elif kind == "qjackctl_server_prefix":
        success, message = _force_reset_qjackctl_server_prefix(params)
    elif kind == "wpctl_profile":
        success, message = _force_reset_wpctl_profile(params)
    elif kind == "user_service_mask":
        services = params.get("services", [])
        if isinstance(services, str):
            services = [services]
        success, message = _force_reset_user_services([str(s) for s in services])
    elif kind == "baloo_disable":
        success, message = _force_reset_baloo_disable()
    else:
        message = f"Force reset not supported for kind: {kind}"

    payload = {
        "schema": 1,
        "success": success,
        "knob_id": knob_id,
        "message": message,
    }
    _log_audit_event("force-reset-knob", payload)
    print(json.dumps(payload, indent=2))
    return 0 if success else 1


def main(argv: list[str] | None = None) -> int:
    logger = _setup_worker_logging()
    p = argparse.ArgumentParser(prog="audioknob-worker")
    p.add_argument("--registry", default=_registry_default_path())

    sub = p.add_subparsers(dest="cmd", required=True)

    sd = sub.add_parser("detect", help="Detect audio stack and devices (read-only)")
    sd.set_defaults(func=cmd_detect)

    sp = sub.add_parser("preview", help="Preview planned changes")
    sp.add_argument("--action", choices=["apply", "restore"], default="apply")
    sp.add_argument("knob", nargs="+")
    sp.set_defaults(func=cmd_preview)

    sa = sub.add_parser("apply", help="Apply root knobs (creates a transaction, requires root)")
    sa.add_argument("knob", nargs="+")
    sa.set_defaults(func=cmd_apply)

    sau = sub.add_parser("apply-user", help="Apply non-root knobs (creates user-scope transaction)")
    sau.add_argument("knob", nargs="+")
    sau.set_defaults(func=cmd_apply_user)

    sr = sub.add_parser("restore", help="Restore a transaction")
    sr.add_argument("txid")
    sr.set_defaults(func=cmd_restore)

    sh = sub.add_parser("history", help="List transactions")
    sh.add_argument(
        "--scope",
        choices=["user", "root", "all"],
        default="all",
        help="Which transactions to list (default: all; root requires pkexec)",
    )
    sh.set_defaults(func=cmd_history)

    srd = sub.add_parser("reset-defaults", help="Reset ALL changes to system defaults")
    srd.add_argument(
        "--scope",
        choices=["user", "root", "all"],
        default="all",
        help="Which scope to reset: 'user' (no root needed), 'root' (needs pkexec), or 'all' (default)",
    )
    srd.set_defaults(func=cmd_reset_defaults)

    slc = sub.add_parser("list-changes", help="List all files modified by audioknob-gui (historical audit)")
    slc.set_defaults(func=cmd_list_changes)

    slp = sub.add_parser("list-pending", help="List files/effects still pending reset (for GUI preview)")
    slp.set_defaults(func=cmd_list_pending)

    sst = sub.add_parser("status", help="Check current status of all knobs")
    sst.set_defaults(func=cmd_status)

    srk = sub.add_parser("restore-knob", help="Restore a specific knob to its original state")
    srk.add_argument("knob_id", help="ID of the knob to restore")
    srk.set_defaults(func=cmd_restore_knob)

    srm = sub.add_parser("restore-many", help="Restore multiple knobs to their original state")
    srm.add_argument("knob", nargs="+", help="IDs of knobs to restore")
    srm.set_defaults(func=cmd_restore_many)

    sfr = sub.add_parser("force-reset-knob", help="Force reset a knob without a transaction")
    sfr.add_argument("knob_id", help="ID of the knob to force reset")
    sfr.set_defaults(func=cmd_force_reset_knob)

    args = p.parse_args(argv)
    try:
        result = args.func(args)
        rc = int(result) if result is not None else 0
        logger.info("exit rc=%s", rc)
        return rc
    except SystemExit as e:
        logger.error("exit error=%s", e)
        raise
    except Exception:
        logger.exception("unhandled error")
        raise


if __name__ == "__main__":
    raise SystemExit(main())

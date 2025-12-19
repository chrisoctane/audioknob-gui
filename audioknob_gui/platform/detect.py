from __future__ import annotations

import json
import os
from dataclasses import dataclass

from audioknob_gui.core.runner import run


@dataclass(frozen=True)
class StackStatus:
    pipewire_active: bool
    wireplumber_active: bool
    jack_active: bool


def _is_active(unit: str, user: bool = False) -> bool:
    """Check if a systemd unit is active.
    
    Args:
        unit: The unit name (e.g., "pipewire.service")
        user: If True, check user services (--user), else system services
    """
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd.extend(["is-active", unit])
    r = run(cmd)
    return r.returncode == 0 and r.stdout.strip() == "active"


def detect_stack() -> StackStatus:
    """Detect audio stack status.
    
    Checks both user services (PipeWire, WirePlumber) and system services (JACK).
    """
    return StackStatus(
        # PipeWire and WirePlumber run as user services
        pipewire_active=_is_active("pipewire.service", user=True),
        wireplumber_active=_is_active("wireplumber.service", user=True),
        # JACK can run as either user or system service
        jack_active=(
            _is_active("jack.service", user=True) or
            _is_active("jackd.service", user=True) or
            _is_active("jack.service", user=False) or
            _is_active("jackd.service", user=False)
        ),
    )


def list_alsa_playback_devices() -> list[dict]:
    # Uses `aplay -l` if available.
    from shutil import which

    if which("aplay") is None:
        return []

    r = run(["aplay", "-l"])
    if r.returncode != 0:
        return []

    # Minimal parse: return raw lines as a starting point.
    lines = [ln.rstrip() for ln in r.stdout.splitlines() if ln.strip()]
    return [{"raw": ln} for ln in lines]


def get_cpu_count() -> int:
    return os.cpu_count() or 1


def dump_detect() -> dict:
    s = detect_stack()
    return {
        "schema": 1,
        "stack": {
            "pipewire_active": s.pipewire_active,
            "wireplumber_active": s.wireplumber_active,
            "jack_active": s.jack_active,
        },
        "alsa_playback_devices": list_alsa_playback_devices(),
    }


def main() -> int:
    print(json.dumps(dump_detect(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

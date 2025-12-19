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


@dataclass(frozen=True)
class GroupStatus:
    """User's audio-related group memberships."""
    audio: bool
    realtime: bool  # Arch Linux uses 'realtime' instead of 'audio'
    pipewire: bool
    
    @property
    def has_rt_groups(self) -> bool:
        """True if user has groups needed for RT limits."""
        return self.audio or self.realtime


def check_group_membership() -> GroupStatus:
    """Check if current user is in audio-related groups."""
    import grp
    
    user_groups = set(os.getgroups())
    
    def in_group(name: str) -> bool:
        try:
            return grp.getgrnam(name).gr_gid in user_groups
        except KeyError:
            return False  # Group doesn't exist on this system
    
    return GroupStatus(
        audio=in_group("audio"),
        realtime=in_group("realtime"),
        pipewire=in_group("pipewire"),
    )


def get_missing_groups() -> list[str]:
    """Return list of recommended groups user is NOT in."""
    import grp
    
    user_groups = set(os.getgroups())
    missing = []
    
    # Check which audio groups exist and if user is in them
    for group_name in ["audio", "realtime", "pipewire"]:
        try:
            gid = grp.getgrnam(group_name).gr_gid
            if gid not in user_groups:
                missing.append(group_name)
        except KeyError:
            pass  # Group doesn't exist, skip
    
    return missing


def get_available_audio_groups() -> list[str]:
    """Return list of audio-related groups that exist on this system."""
    import grp
    
    available = []
    for group_name in ["audio", "realtime", "pipewire"]:
        try:
            grp.getgrnam(group_name)
            available.append(group_name)
        except KeyError:
            pass
    return available


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

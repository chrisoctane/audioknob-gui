from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Paths:
    # Unprivileged GUI state
    user_state_dir: str

    # Privileged worker transaction root
    var_lib_dir: str


def default_paths() -> Paths:
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        user_state_dir = os.path.join(xdg_state, "audioknob-gui")
    else:
        user_state_dir = os.path.join(os.path.expanduser("~"), ".local", "state", "audioknob-gui")

    return Paths(
        user_state_dir=user_state_dir,
        var_lib_dir="/var/lib/audioknob-gui",
    )

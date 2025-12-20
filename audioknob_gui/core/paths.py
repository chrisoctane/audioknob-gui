from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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


def get_registry_path() -> str:
    """Get path to registry.json, supporting both dev and installed modes.
    
    Priority:
    1. AUDIOKNOB_REGISTRY env var (explicit override)
    2. AUDIOKNOB_DEV_REPO env var (dev mode)
    3. Package data via importlib.resources
    4. Fallback: relative to this file (legacy dev mode)
    """
    # Explicit override via environment
    env_registry = os.environ.get("AUDIOKNOB_REGISTRY")
    if env_registry and Path(env_registry).exists():
        return env_registry
    
    # Dev repo override via environment
    dev_repo = os.environ.get("AUDIOKNOB_DEV_REPO")
    if dev_repo:
        dev_path = Path(dev_repo) / "config" / "registry.json"
        if dev_path.exists():
            return str(dev_path)
    
    # Try importlib.resources (works when installed as package)
    try:
        import importlib.resources as resources
        # Python 3.9+
        try:
            files = resources.files("audioknob_gui.data")
            registry_file = files.joinpath("registry.json")
            # Check if it's traversable (exists)
            if hasattr(registry_file, "is_file") and registry_file.is_file():
                # For Python 3.9+, we can get the path directly for a real file
                # or read it. For compatibility, try to get a path.
                with resources.as_file(registry_file) as p:
                    return str(p)
        except (TypeError, AttributeError):
            # Fallback for older API
            pass
        
        # Python 3.7-3.8 style
        with resources.path("audioknob_gui.data", "registry.json") as p:
            if p.exists():
                return str(p)
    except (ImportError, ModuleNotFoundError, FileNotFoundError, TypeError):
        pass
    
    # Fallback: compute from this file's location (legacy dev mode)
    # paths.py is in audioknob_gui/core/
    # repo root is parents[2], config/registry.json is at repo_root/config/
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    dev_path = repo_root / "config" / "registry.json"
    if dev_path.exists():
        return str(dev_path)
    
    # Also check package data location in dev mode
    pkg_data = repo_root / "audioknob_gui" / "data" / "registry.json"
    if pkg_data.exists():
        return str(pkg_data)
    
    raise FileNotFoundError(
        "Cannot find registry.json. Set AUDIOKNOB_REGISTRY or AUDIOKNOB_DEV_REPO env var, "
        "or install the package properly."
    )

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _read_git_rev(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short=8", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            rev = result.stdout.strip()
            if rev:
                return rev[:8]
    except Exception:
        pass

    git_dir = repo_root / ".git"
    if git_dir.is_file():
        try:
            line = git_dir.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
        if line.startswith("gitdir:"):
            git_dir = (repo_root / line.split(":", 1)[1].strip()).resolve()
        else:
            return ""
    if not git_dir.is_dir():
        return ""
    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        ref_path = git_dir / ref
        try:
            return ref_path.read_text(encoding="utf-8").strip()[:8]
        except Exception:
            packed_refs = git_dir / "packed-refs"
            try:
                for raw in packed_refs.read_text(encoding="utf-8").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#") or line.startswith("^"):
                        continue
                    parts = line.split(" ", 1)
                    if len(parts) != 2:
                        continue
                    if parts[1].strip() == ref:
                        return parts[0].strip()[:8]
            except Exception:
                pass
            return ""
    return head[:8]


def _git_rev() -> str:
    env_rev = os.environ.get("AUDIOKNOB_GIT_REV", "").strip()
    if env_rev:
        return env_rev[:8]
    repo_env = os.environ.get("AUDIOKNOB_DEV_REPO", "").strip()
    if repo_env:
        rev = _read_git_rev(Path(repo_env))
        if rev:
            return rev
    return _read_git_rev(Path(__file__).resolve().parents[2])


def _app_title() -> str:
    try:
        from audioknob_gui import __version__ as app_version
    except Exception:
        app_version = "unknown"
    rev = _git_rev()
    if rev:
        return f"audioknob-gui v{app_version} (git {rev})"
    return f"audioknob-gui v{app_version}"

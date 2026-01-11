"""Package ownership detection for cross-distro reset support.

Detects which package (if any) owns a file, and provides methods to
restore files to their package defaults.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PackageManager(Enum):
    RPM = "rpm"      # openSUSE, Fedora, RHEL
    DPKG = "dpkg"    # Debian, Ubuntu
    PACMAN = "pacman"  # Arch
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PackageInfo:
    """Information about package ownership of a file."""
    path: str
    owned: bool
    package: str | None
    manager: PackageManager
    can_restore: bool  # Whether we can restore this file from the package


def detect_package_manager() -> PackageManager:
    """Detect which package manager is available on this system."""
    if shutil.which("rpm") and Path("/var/lib/rpm").exists():
        return PackageManager.RPM
    elif shutil.which("dpkg") and Path("/var/lib/dpkg").exists():
        return PackageManager.DPKG
    elif shutil.which("pacman") and Path("/var/lib/pacman").exists():
        return PackageManager.PACMAN
    return PackageManager.UNKNOWN


def get_package_owner(path: str | Path) -> PackageInfo:
    """Determine which package (if any) owns a file.
    
    Returns PackageInfo with ownership details.
    """
    path = Path(path).resolve()
    path_str = str(path)
    manager = detect_package_manager()
    
    if not path.exists():
        return PackageInfo(
            path=path_str,
            owned=False,
            package=None,
            manager=manager,
            can_restore=False,
        )
    
    # User home files are never package-owned
    if path_str.startswith(str(Path.home())):
        return PackageInfo(
            path=path_str,
            owned=False,
            package=None,
            manager=manager,
            can_restore=False,
        )
    
    if manager == PackageManager.RPM:
        return _query_rpm(path_str, manager)
    elif manager == PackageManager.DPKG:
        return _query_dpkg(path_str, manager)
    elif manager == PackageManager.PACMAN:
        return _query_pacman(path_str, manager)
    
    return PackageInfo(
        path=path_str,
        owned=False,
        package=None,
        manager=manager,
        can_restore=False,
    )


def _query_rpm(path: str, manager: PackageManager) -> PackageInfo:
    """Query RPM database for file ownership."""
    try:
        cmd = which_command("rpm") or "rpm"
        result = subprocess.run(
            [cmd, "-qf", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            package = result.stdout.strip()
            return PackageInfo(
                path=path,
                owned=True,
                package=package,
                manager=manager,
                can_restore=True,  # rpm --restore works
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return PackageInfo(
        path=path,
        owned=False,
        package=None,
        manager=manager,
        can_restore=False,
    )


def _query_dpkg(path: str, manager: PackageManager) -> PackageInfo:
    """Query dpkg database for file ownership."""
    try:
        cmd = which_command("dpkg") or "dpkg"
        result = subprocess.run(
            [cmd, "-S", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Output format: "package-name: /path/to/file"
            line = result.stdout.strip()
            if ":" in line:
                package = line.split(":")[0].strip()
                return PackageInfo(
                    path=path,
                    owned=True,
                    package=package,
                    manager=manager,
                    can_restore=True,  # apt-get install --reinstall works
                )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return PackageInfo(
        path=path,
        owned=False,
        package=None,
        manager=manager,
        can_restore=False,
    )


def _query_pacman(path: str, manager: PackageManager) -> PackageInfo:
    """Query pacman database for file ownership."""
    try:
        cmd = which_command("pacman") or "pacman"
        result = subprocess.run(
            [cmd, "-Qo", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Output format: "/path/to/file is owned by package-name version"
            parts = result.stdout.strip().split(" is owned by ")
            if len(parts) == 2:
                pkg_ver = parts[1].split()
                package = pkg_ver[0] if pkg_ver else None
                return PackageInfo(
                    path=path,
                    owned=True,
                    package=package,
                    manager=manager,
                    can_restore=True,
                )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return PackageInfo(
        path=path,
        owned=False,
        package=None,
        manager=manager,
        can_restore=False,
    )


def restore_package_file(info: PackageInfo) -> tuple[bool, str]:
    """Restore a file to its package default.
    
    Returns (success, message).
    """
    if not info.owned or not info.package:
        return False, f"File {info.path} is not owned by any package"
    
    if info.manager == PackageManager.RPM:
        return _restore_rpm(info)
    elif info.manager == PackageManager.DPKG:
        return _restore_dpkg(info)
    elif info.manager == PackageManager.PACMAN:
        return _restore_pacman(info)
    
    return False, f"Unknown package manager: {info.manager}"


def _restore_rpm(info: PackageInfo) -> tuple[bool, str]:
    """Restore file using rpm --restore."""
    try:
        # rpm --restore restores files to their package defaults
        cmd = which_command("rpm") or "rpm"
        result = subprocess.run(
            [cmd, "--restore", info.package],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return True, f"Restored {info.path} from package {info.package}"
        else:
            return False, f"rpm --restore failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "rpm --restore timed out"
    except FileNotFoundError:
        return False, "rpm command not found"


def _restore_dpkg(info: PackageInfo) -> tuple[bool, str]:
    """Restore file by reinstalling package (dpkg)."""
    try:
        cmds = resolve_package_commands()
        reinstall_cmd = cmds.get("reinstall") or []
        if not reinstall_cmd:
            return False, "apt-get/apt command not found"
        result = subprocess.run(
            [*reinstall_cmd, info.package],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, f"Reinstalled package {info.package} to restore {info.path}"
        else:
            return False, f"Package reinstall failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "Package reinstall timed out"
    except FileNotFoundError:
        return False, "Package reinstall command not found"


def _restore_pacman(info: PackageInfo) -> tuple[bool, str]:
    """Restore file by reinstalling package (pacman)."""
    try:
        cmds = resolve_package_commands()
        reinstall_cmd = cmds.get("reinstall") or []
        if not reinstall_cmd:
            return False, "pacman command not found"
        result = subprocess.run(
            [*reinstall_cmd, info.package],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, f"Reinstalled package {info.package} to restore {info.path}"
        else:
            return False, f"Package reinstall failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "Package reinstall timed out"
    except FileNotFoundError:
        return False, "Package reinstall command not found"


@dataclass(frozen=True)
class ResetStrategy:
    """Strategy for resetting a file to system defaults."""
    DELETE = "delete"           # File we created - just delete it
    RESTORE_BACKUP = "backup"   # Restore from our backup
    RESTORE_PACKAGE = "package" # Restore from package manager
    MANUAL = "manual"           # Requires manual intervention


# Package name mappings: command -> package name per distro
PACKAGE_MAPPINGS: dict[str, dict[PackageManager, str]] = {
    "cyclictest": {
        PackageManager.RPM: "rt-tests",
        PackageManager.DPKG: "rt-tests",
        PackageManager.PACMAN: "rt-tests",
    },
    "rtirq": {
        PackageManager.RPM: "rtirq",
        PackageManager.DPKG: "rtirq-init",
        PackageManager.PACMAN: "rtirq",
    },
    "cpupower": {
        PackageManager.RPM: "cpupower",
        PackageManager.DPKG: "linux-cpupower",
        PackageManager.PACMAN: "cpupower",
    },
    "qjackctl": {
        PackageManager.RPM: "qjackctl",
        PackageManager.DPKG: "qjackctl",
        PackageManager.PACMAN: "qjackctl",
    },
    # Best-effort mapping: package names vary by distro/flavor.
    # If this mapping is wrong on a given distro, install will fail and user must install manually.
    "balooctl": {
        # openSUSE Tumbleweed / KDE Frameworks 6: provides balooctl6
        PackageManager.RPM: "kf6-baloo-tools",
        PackageManager.DPKG: "baloo-kf5",
        PackageManager.PACMAN: "baloo",
    },
}


# Some distros rename commands across major desktop/framework versions.
# Treat these aliases as satisfying the canonical command name in registry.json.
COMMAND_ALIASES: dict[str, tuple[str, ...]] = {
    # openSUSE Tumbleweed / KDE Frameworks 6
    "balooctl": ("balooctl6",),
}


def which_command(command: str) -> str | None:
    """Return an executable path for a command, considering aliases and common sbin paths."""
    cands = (command,) + tuple(COMMAND_ALIASES.get(command, ()))

    for cand in cands:
        p = shutil.which(cand)
        if p:
            return p

    # GUI sessions often have a reduced PATH that omits sbin.
    for cand in cands:
        for d in (
            "/usr/bin",
            "/usr/sbin",
            "/bin",
            "/sbin",
            "/usr/local/bin",
            "/usr/local/sbin",
            "/etc/init.d",
        ):
            p = Path(d) / cand
            if p.exists() and p.is_file() and os.access(p, os.X_OK):
                return str(p)

    return None


def resolve_package_commands() -> dict[str, list[str]]:
    """Resolve package manager commands for install/remove/reinstall/query."""
    manager = detect_package_manager()
    cmds: dict[str, list[str]] = {
        "install": [],
        "remove": [],
        "reinstall": [],
        "query_owner": [],
    }

    if manager == PackageManager.RPM:
        zypper = which_command("zypper")
        dnf = which_command("dnf")
        rpm = which_command("rpm")
        if zypper:
            cmds["install"] = [zypper, "--non-interactive", "install"]
            cmds["remove"] = [zypper, "--non-interactive", "remove"]
            cmds["reinstall"] = [zypper, "--non-interactive", "install", "-f"]
        elif dnf:
            cmds["install"] = [dnf, "install", "-y"]
            cmds["remove"] = [dnf, "remove", "-y"]
            cmds["reinstall"] = [dnf, "reinstall", "-y"]
        if rpm:
            cmds["query_owner"] = [rpm, "-qf"]
            if not cmds["reinstall"]:
                cmds["reinstall"] = [rpm, "--restore"]

    elif manager == PackageManager.DPKG:
        apt = which_command("apt-get") or which_command("apt")
        dpkg = which_command("dpkg")
        if apt:
            cmds["install"] = [apt, "install", "-y"]
            cmds["remove"] = [apt, "remove", "-y"]
            cmds["reinstall"] = [apt, "install", "--reinstall", "-y"]
        if dpkg:
            cmds["query_owner"] = [dpkg, "-S"]

    elif manager == PackageManager.PACMAN:
        pacman = which_command("pacman")
        if pacman:
            cmds["install"] = [pacman, "-S", "--noconfirm"]
            cmds["remove"] = [pacman, "-R", "--noconfirm"]
            cmds["reinstall"] = [pacman, "-S", "--noconfirm"]
            cmds["query_owner"] = [pacman, "-Qo"]

    return cmds


def check_command_available(command: str) -> bool:
    """Check if a command is available in PATH."""
    return which_command(command) is not None


def check_packages_installed(commands: list[str]) -> dict[str, bool]:
    """Check which commands are available.
    
    Returns dict of {command: is_available}.
    """
    return {cmd: check_command_available(cmd) for cmd in commands}


def get_missing_packages(commands: list[str]) -> list[str]:
    """Return list of commands that are NOT available."""
    return [cmd for cmd in commands if not check_command_available(cmd)]


def get_package_name(command: str) -> str | None:
    """Get the package name to install for a command on this distro."""
    manager = detect_package_manager()
    mapping = PACKAGE_MAPPINGS.get(command, {})
    return mapping.get(manager)


def install_packages(commands: list[str]) -> tuple[bool, str]:
    """Install packages that provide the given commands.
    
    Returns (success, message).
    """
    # Map commands to package names
    packages = []
    for cmd in commands:
        pkg = get_package_name(cmd)
        if pkg:
            packages.append(pkg)
        else:
            return False, f"Unknown package for command: {cmd}"
    
    if not packages:
        return True, "No packages to install"
    
    packages = list(set(packages))  # Dedupe
    
    try:
        cmd = resolve_package_commands().get("install") or []
        if not cmd:
            return False, "Unknown package manager"
        result = subprocess.run(
            [*cmd, *packages],
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        if result.returncode == 0:
            return True, f"Installed: {', '.join(packages)}"
        else:
            return False, f"Install failed: {result.stderr.strip()}"
    
    except subprocess.TimeoutExpired:
        return False, "Package installation timed out"
    except Exception as e:
        return False, f"Install error: {e}"


def determine_reset_strategy(path: str | Path, we_created: bool = False) -> tuple[str, PackageInfo | None]:
    """Determine the best reset strategy for a file.
    
    Args:
        path: Path to the file
        we_created: True if we created this file (vs modifying existing)
    
    Returns:
        (strategy, package_info) tuple
    """
    path = Path(path)
    path_str = str(path.resolve()) if path.exists() else str(path)
    
    # If we created the file, just delete it
    if we_created:
        return ResetStrategy.DELETE, None
    
    # Check if it's a user file
    try:
        if path_str.startswith(str(Path.home())):
            return ResetStrategy.RESTORE_BACKUP, None
    except RuntimeError:
        # Path.home() can fail in some contexts
        pass
    
    # Check package ownership
    pkg_info = get_package_owner(path)
    if pkg_info.owned and pkg_info.can_restore:
        return ResetStrategy.RESTORE_PACKAGE, pkg_info
    
    # Fall back to backup restore
    return ResetStrategy.RESTORE_BACKUP, None

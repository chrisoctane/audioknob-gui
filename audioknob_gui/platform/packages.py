"""Package ownership detection for cross-distro reset support.

Detects which package (if any) owns a file, and provides methods to
restore files to their package defaults.
"""

from __future__ import annotations

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
        result = subprocess.run(
            ["rpm", "-qf", path],
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
        result = subprocess.run(
            ["dpkg", "-S", path],
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
        result = subprocess.run(
            ["pacman", "-Qo", path],
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
        result = subprocess.run(
            ["rpm", "--restore", info.package],
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
        # For dpkg, we need to reinstall the package
        result = subprocess.run(
            ["apt-get", "install", "--reinstall", "-y", info.package],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, f"Reinstalled package {info.package} to restore {info.path}"
        else:
            return False, f"apt-get reinstall failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "apt-get reinstall timed out"
    except FileNotFoundError:
        return False, "apt-get command not found"


def _restore_pacman(info: PackageInfo) -> tuple[bool, str]:
    """Restore file by reinstalling package (pacman)."""
    try:
        result = subprocess.run(
            ["pacman", "-S", "--noconfirm", info.package],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, f"Reinstalled package {info.package} to restore {info.path}"
        else:
            return False, f"pacman -S failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "pacman -S timed out"
    except FileNotFoundError:
        return False, "pacman command not found"


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
}


def check_command_available(command: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(command) is not None


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
    manager = detect_package_manager()
    
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
        if manager == PackageManager.RPM:
            # Try zypper first (openSUSE), fall back to dnf (Fedora)
            if shutil.which("zypper"):
                result = subprocess.run(
                    ["zypper", "--non-interactive", "install", *packages],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            else:
                result = subprocess.run(
                    ["dnf", "install", "-y", *packages],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
        elif manager == PackageManager.DPKG:
            result = subprocess.run(
                ["apt-get", "install", "-y", *packages],
                capture_output=True,
                text=True,
                timeout=300,
            )
        elif manager == PackageManager.PACMAN:
            result = subprocess.run(
                ["pacman", "-S", "--noconfirm", *packages],
                capture_output=True,
                text=True,
                timeout=300,
            )
        else:
            return False, "Unknown package manager"
        
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

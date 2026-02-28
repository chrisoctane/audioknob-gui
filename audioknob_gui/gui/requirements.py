from __future__ import annotations

import os
import subprocess
import shutil

from PySide6.QtWidgets import QMessageBox

from audioknob_gui.gui.actions import QueueTaskWorker
from audioknob_gui.gui.logging_utils import _get_gui_logger, _log_gui_audit
from audioknob_gui.gui.worker_api import _PKEXEC_CANCELLED, _run_pkexec_command_capture
from audioknob_gui.knob_ids import AUDIO_GROUP_MEMBERSHIP, POWER_PROFILE_PERFORMANCE


def refresh_user_groups(ui) -> None:
    """Get current user's group memberships."""
    import grp
    try:
        user_gids = set(os.getgroups())
        ui._user_groups = set()
        for group_name in ["audio", "realtime", "pipewire"]:
            try:
                if grp.getgrnam(group_name).gr_gid in user_gids:
                    ui._user_groups.add(group_name)
            except KeyError:
                pass  # Group doesn't exist
    except Exception:
        ui._user_groups = set()


def knob_group_ok(ui, k) -> bool:
    """Check if user has required groups for this knob."""
    if not k.requires_groups:
        return True  # No groups required
    # User needs to be in at least ONE of the required groups
    return bool(set(k.requires_groups) & ui._user_groups)


def knob_commands_ok(ui, k) -> bool:
    """Check if required commands are available for this knob."""
    if not k.requires_commands:
        return True  # No commands required
    from audioknob_gui.platform.packages import check_command_available
    if k.id == POWER_PROFILE_PERFORMANCE:
        backend = ui._power_profile_backend_from_state()
        if backend == "powerprofilesctl":
            return check_command_available("powerprofilesctl")
        if backend == "tuned":
            return check_command_available("tuned-adm")
        return (
            check_command_available("powerprofilesctl")
            or check_command_available("tuned-adm")
        )
    return all(check_command_available(cmd) for cmd in k.requires_commands)


def knob_missing_commands(ui, k) -> list[str]:
    """Return list of missing commands for this knob."""
    if not k.requires_commands:
        return []
    from audioknob_gui.platform.packages import check_command_available
    if k.id == POWER_PROFILE_PERFORMANCE:
        backend = ui._power_profile_backend_from_state()
        if backend == "powerprofilesctl":
            return [] if check_command_available("powerprofilesctl") else ["powerprofilesctl"]
        if backend == "tuned":
            return [] if check_command_available("tuned-adm") else ["tuned-adm"]
        if (
            check_command_available("powerprofilesctl")
            or check_command_available("tuned-adm")
        ):
            return []
        return ["powerprofilesctl", "tuned-adm"]
    return [cmd for cmd in k.requires_commands if not check_command_available(cmd)]


def _group_op_finish(
    ui,
    logger,
    payload: object,
    message: str,
    *,
    action_key: str,
    action_label: str,
    log_action: str,
    audit_action: str,
    user: str,
) -> None:
    """Shared completion handler for join/leave group operations."""
    ui._busy_knobs.discard(AUDIO_GROUP_MEMBERSHIP)
    errors: list[str] = []
    changed: list[str] = []
    if isinstance(payload, dict):
        errors = payload.get("errors") or []
        changed = payload.get(action_key) or []
    if not changed and not errors and message:
        errors = [message]

    msg: list[str] = []
    if changed:
        msg.append(f"<b style='color: #2e7d32;'>{action_label}</b> {', '.join(changed)}")
    if errors:
        msg.append(f"<br/><b style='color: #d32f2f;'>Errors:</b><br/>{'<br/>'.join(errors)}")
    if changed:
        msg.append("<br/><br/><b>Reboot required for changes to take effect.</b>")

    QMessageBox.information(ui, "Group Membership", "".join(msg))
    logger.info(
        "%s user=%s %s=%s errors=%s",
        log_action, user, action_key, ",".join(changed), "; ".join(errors),
    )
    if isinstance(payload, dict):
        _log_gui_audit(audit_action, payload)

    if changed:
        ui._knob_statuses[AUDIO_GROUP_MEMBERSHIP] = "pending_reboot"
        ui._update_reboot_banner()

    ui._refresh_user_groups()
    ui._populate()


def on_join_groups(ui) -> None:
    """Add current user to audio groups."""
    from audioknob_gui.platform.detect import get_available_audio_groups, get_missing_groups
    from audioknob_gui.platform.packages import which_command

    logger = _get_gui_logger()
    if AUDIO_GROUP_MEMBERSHIP in ui._busy_knobs:
        return
    missing = get_missing_groups()
    available = get_available_audio_groups()

    if not missing:
        QMessageBox.information(
            ui,
            "Groups OK",
            "You are already in all available audio groups!"
        )
        return

    # Show what groups we'll add
    groups_to_add = [g for g in missing if g in available]
    if not groups_to_add:
        QMessageBox.warning(
            ui,
            "No Groups Available",
            "No audio groups exist on this system."
        )
        return

    reply = QMessageBox.question(
        ui,
        "Join Audio Groups",
        f"Add user to these groups?\n\n• {chr(10).join(groups_to_add)}\n\n"
        f"Note: You must log out and back in for changes to take effect.",
        QMessageBox.Ok | QMessageBox.Cancel
    )

    if reply != QMessageBox.Ok:
        return

    # Run usermod via pkexec for each group
    import getpass
    usermod = which_command("usermod")
    if not usermod:
        QMessageBox.critical(ui, "Error", "usermod not found on this system.")
        logger.error("join groups failed: usermod not found")
        _log_gui_audit(
            "join-groups",
            {
                "user": os.environ.get("USER") or "",
                "groups": groups_to_add,
                "error": "usermod not found",
            },
        )
        return

    user = os.environ.get("USER") or getpass.getuser()
    ui._busy_knobs.add(AUDIO_GROUP_MEMBERSHIP)
    ui._knob_statuses[AUDIO_GROUP_MEMBERSHIP] = "running"
    ui._populate()

    def _task() -> tuple[bool, object, str]:
        errors: list[str] = []
        successes: list[str] = []
        results: list[dict[str, object]] = []

        for group in groups_to_add:
            try:
                cmd = [usermod, "-aG", group, user]
                p = _run_pkexec_command_capture(cmd, timeout=30)
                results.append(
                    {
                        "group": group,
                        "cmd": ["pkexec", *cmd],
                        "returncode": p.returncode,
                        "stdout": p.stdout,
                        "stderr": p.stderr,
                    }
                )
                if p.returncode == 0:
                    successes.append(group)
                else:
                    errors.append(f"{group}: {p.stderr.strip() or 'Failed'}")
            except Exception as e:
                results.append({"group": group, "error": str(e)})
                if str(e) == _PKEXEC_CANCELLED:
                    errors.append(f"{group}: Authentication cancelled")
                    break
                errors.append(f"{group}: {e}")

        payload = {
            "user": user,
            "groups": groups_to_add,
            "added": successes,
            "errors": errors,
            "results": results,
        }
        return len(errors) == 0, payload, ""

    worker = QueueTaskWorker(_task, parent=ui)

    def _on_done(success: bool, payload: object, message: str) -> None:
        _group_op_finish(
            ui, logger, payload, message,
            action_key="added",
            action_label="Added to:",
            log_action="join groups",
            audit_action="join-groups",
            user=user,
        )

    worker.finished.connect(_on_done)
    worker.finished.connect(worker.deleteLater)
    ui._task_threads.append(worker)
    worker.start()


def on_leave_groups(ui) -> None:
    """Remove current user from audio groups."""
    from audioknob_gui.platform.detect import get_available_audio_groups
    from audioknob_gui.platform.packages import which_command

    logger = _get_gui_logger()
    if AUDIO_GROUP_MEMBERSHIP in ui._busy_knobs:
        return
    ui._refresh_user_groups()
    available = get_available_audio_groups()
    groups_to_remove = [g for g in available if g in ui._user_groups]

    if not groups_to_remove:
        QMessageBox.information(
            ui,
            "No Groups",
            "You are not currently in any audio groups."
        )
        return

    reply = QMessageBox.question(
        ui,
        "Leave Audio Groups",
        f"Remove user from these groups?\n\n• {chr(10).join(groups_to_remove)}\n\n"
        f"Note: A reboot is required for changes to take effect.",
        QMessageBox.Ok | QMessageBox.Cancel
    )
    if reply != QMessageBox.Ok:
        return

    import getpass
    user = os.environ.get("USER") or getpass.getuser()
    gpasswd = which_command("gpasswd")
    usermod = which_command("usermod")
    if not gpasswd and not usermod:
        QMessageBox.critical(ui, "Error", "Neither gpasswd nor usermod found on this system.")
        logger.error("leave groups failed: no gpasswd/usermod")
        _log_gui_audit(
            "leave-groups",
            {
                "user": user,
                "groups": groups_to_remove,
                "error": "no gpasswd/usermod",
            },
        )
        return
    ui._busy_knobs.add(AUDIO_GROUP_MEMBERSHIP)
    ui._knob_statuses[AUDIO_GROUP_MEMBERSHIP] = "running"
    ui._populate()

    def _task() -> tuple[bool, object, str]:
        errors: list[str] = []
        successes: list[str] = []
        results: list[dict[str, object]] = []

        if gpasswd:
            for group in groups_to_remove:
                try:
                    cmd = [gpasswd, "-d", user, group]
                    p = _run_pkexec_command_capture(cmd, timeout=30)
                    results.append(
                        {
                            "group": group,
                            "cmd": ["pkexec", *cmd],
                            "returncode": p.returncode,
                            "stdout": p.stdout,
                            "stderr": p.stderr,
                        }
                    )
                    if p.returncode == 0:
                        successes.append(group)
                    else:
                        errors.append(f"{group}: {p.stderr.strip() or 'Failed'}")
                except Exception as e:
                    results.append({"group": group, "error": str(e)})
                    if str(e) == _PKEXEC_CANCELLED:
                        errors.append(f"{group}: Authentication cancelled")
                        break
                    errors.append(f"{group}: {e}")
        else:
            try:
                import grp
                keep_groups = []
                for gid in os.getgroups():
                    try:
                        keep_groups.append(grp.getgrgid(gid).gr_name)
                    except KeyError:
                        pass
                keep_groups = [g for g in keep_groups if g not in groups_to_remove]
                group_list = ",".join(sorted(set(keep_groups)))
                cmd = [usermod, "-G", group_list, user]
                p = _run_pkexec_command_capture(cmd, timeout=30)
                results.append(
                    {
                        "groups": groups_to_remove,
                        "cmd": ["pkexec", *cmd],
                        "returncode": p.returncode,
                        "stdout": p.stdout,
                        "stderr": p.stderr,
                    }
                )
                if p.returncode == 0:
                    successes.extend(groups_to_remove)
                else:
                    errors.append(p.stderr.strip() or "Failed to update groups")
            except Exception as e:
                results.append({"groups": groups_to_remove, "error": str(e)})
                if str(e) == _PKEXEC_CANCELLED:
                    errors.append("Authentication cancelled")
                else:
                    errors.append(str(e))

        payload = {
            "user": user,
            "groups": groups_to_remove,
            "removed": successes,
            "errors": errors,
            "results": results,
        }
        return len(errors) == 0, payload, ""

    worker = QueueTaskWorker(_task, parent=ui)

    def _on_done(success: bool, payload: object, message: str) -> None:
        _group_op_finish(
            ui, logger, payload, message,
            action_key="removed",
            action_label="Removed from:",
            log_action="leave groups",
            audit_action="leave-groups",
            user=user,
        )

    worker.finished.connect(_on_done)
    worker.finished.connect(worker.deleteLater)
    ui._task_threads.append(worker)
    worker.start()


def on_install_packages(ui, commands: list[str]) -> None:
    """Install packages that provide the given commands."""
    from audioknob_gui.platform.packages import get_package_name, detect_package_manager

    if ui._install_busy:
        QMessageBox.information(ui, "Install in progress", "Package installation is already running.")
        return

    logger = _get_gui_logger()
    logger.info("install clicked commands=%s", ",".join(commands))
    if not commands:
        QMessageBox.warning(ui, "Install", "No installable commands were detected.")
        logger.warning("install clicked with no commands")
        return
    # Map commands to package names
    packages = []
    unknown = []
    for cmd in commands:
        pkg = get_package_name(cmd)
        if pkg:
            packages.append(pkg)
        else:
            unknown.append(cmd)

    if unknown:
        QMessageBox.warning(
            ui,
            "Unknown Package",
            f"Cannot determine package for: {', '.join(unknown)}\n\n"
            f"Please install manually."
        )
        _log_gui_audit(
            "install-packages",
            {
                "commands": commands,
                "packages": packages,
                "unknown": unknown,
                "error": "unknown package mapping",
            },
        )
        return

    packages = list(set(packages))  # Dedupe

    # Confirm installation
    reply = QMessageBox.question(
        ui,
        "Install Packages",
        f"Install the following packages?\n\n• {chr(10).join(packages)}",
        QMessageBox.Ok | QMessageBox.Cancel
    )

    if reply != QMessageBox.Ok:
        _log_gui_audit(
            "install-packages",
            {
                "commands": commands,
                "packages": packages,
                "status": "cancelled",
            },
        )
        return

    # Run package manager via pkexec
    manager = detect_package_manager()

    try:
        from audioknob_gui.platform.packages import PackageManager

        if manager == PackageManager.RPM:
            if shutil.which("zypper"):
                cmd = ["zypper", "--non-interactive", "install", *packages]
            else:
                cmd = ["dnf", "install", "-y", *packages]
        elif manager == PackageManager.DPKG:
            cmd = ["apt-get", "install", "-y", *packages]
        elif manager == PackageManager.PACMAN:
            cmd = ["pacman", "-S", "--noconfirm", *packages]
        else:
            QMessageBox.warning(ui, "Error", "Unknown package manager")
            _log_gui_audit(
                "install-packages",
                {
                    "commands": commands,
                    "packages": packages,
                    "error": "unknown package manager",
                },
            )
            return

        def _run_install(*, retry: bool) -> None:
            def _task() -> tuple[bool, object, str]:
                try:
                    p = _run_pkexec_command_capture(cmd, timeout=300)
                except subprocess.TimeoutExpired:
                    return False, {
                        "cmd": ["pkexec", *cmd],
                        "returncode": -1,
                        "stdout": "",
                        "stderr": "timeout",
                        "retry": retry,
                        "timeout": True,
                    }, "timeout"
                except Exception as exc:
                    return False, {
                        "cmd": ["pkexec", *cmd],
                        "returncode": -1,
                        "stdout": "",
                        "stderr": str(exc),
                        "retry": retry,
                    }, str(exc)
                return p.returncode == 0, {
                    "cmd": ["pkexec", *cmd],
                    "returncode": p.returncode,
                    "stdout": p.stdout,
                    "stderr": p.stderr,
                    "retry": retry,
                }, ""

            worker = QueueTaskWorker(_task, parent=ui)

            def _on_done(success: bool, payload: object, message: str) -> None:
                if not isinstance(payload, dict):
                    ui._install_busy = False
                    QMessageBox.critical(ui, "Error", message or "Install error")
                    return

                stderr = (payload.get("stderr") or "").strip()
                stdout = (payload.get("stdout") or "").strip()
                rc = payload.get("returncode")
                retry_flag = bool(payload.get("retry"))

                if stderr == _PKEXEC_CANCELLED:
                    _log_gui_audit(
                        "install-packages",
                        {
                            "commands": commands,
                            "packages": packages,
                            "cmd": cmd,
                            "status": "cancelled",
                            "retry": retry_flag,
                        },
                    )
                    ui._install_busy = False
                    return

                if success:
                    if any(cmd_name in ("qjackctl", "qjackctl6") for cmd_name in commands):
                        ui._prime_qjackctl_preset()
                    QMessageBox.information(
                        ui,
                        "Success",
                        f"Installed: {', '.join(packages)}"
                    )
                    _log_gui_audit(
                        "install-packages",
                        {
                            "commands": commands,
                            "packages": packages,
                            "cmd": cmd,
                            "returncode": rc,
                            "stdout": stdout,
                            "stderr": stderr,
                            "retry": retry_flag,
                        },
                    )
                    ui._populate()
                    ui._install_busy = False
                    return

                if payload.get("timeout"):
                    QMessageBox.critical(ui, "Timeout", "Package installation timed out")
                    _log_gui_audit(
                        "install-packages",
                        {
                            "commands": commands,
                            "packages": packages,
                            "cmd": cmd,
                            "error": "timeout",
                        },
                    )
                    ui._install_busy = False
                    return

                combined = (stderr + "\n" + stdout).lower()
                logger.error("install packages failed cmd=%s rc=%s stderr=%s stdout=%s", cmd, rc, stderr, stdout)
                _log_gui_audit(
                    "install-packages",
                    {
                        "commands": commands,
                        "packages": packages,
                        "cmd": cmd,
                        "returncode": rc,
                        "stdout": stdout,
                        "stderr": stderr,
                        "retry": retry_flag,
                    },
                )

                no_provider = any(
                    needle in combined
                    for needle in (
                        "no provider of",
                        "no provider found",
                        "nothing provides",
                        "not found in enabled repositories",
                        "not found in enabled repos",
                    )
                )
                if no_provider and manager == PackageManager.RPM and shutil.which("zypper"):
                    reply = QMessageBox.question(
                        ui,
                        "Add Repositories",
                        "Packages not found in enabled repos.\n\n"
                        "Add repositories and retry?\n\n"
                        "• multimedia:proaudio\n"
                        "• packman",
                        QMessageBox.Ok | QMessageBox.Cancel
                    )
                    if reply == QMessageBox.Ok:
                        repo_defs = [
                            ("multimedia:proaudio", "https://download.opensuse.org/repositories/multimedia:/proaudio/openSUSE_Tumbleweed/"),
                            ("packman", "https://ftp.gwdg.de/pub/linux/misc/packman/suse/openSUSE_Tumbleweed/"),
                        ]

                        def _repo_task() -> tuple[bool, object, str]:
                            repo_errors = []
                            for name, url in repo_defs:
                                add_cmd = ["zypper", "ar", "-f", "-n", name, url, name]
                                r = _run_pkexec_command_capture(add_cmd, timeout=120)
                                if r.returncode != 0:
                                    msg = (r.stderr.strip() or r.stdout.strip())
                                    if "already exists" not in msg.lower():
                                        repo_errors.append(f"{name}: {msg or 'failed'}")

                            if not repo_errors:
                                refresh_cmd = ["zypper", "--gpg-auto-import-keys", "refresh"]
                                r = _run_pkexec_command_capture(refresh_cmd, timeout=300)
                                if r.returncode != 0:
                                    repo_errors.append(r.stderr.strip() or r.stdout.strip() or "refresh failed")

                            if repo_errors:
                                return False, {"errors": repo_errors}, "repo add failed"
                            return True, {"errors": []}, ""

                        repo_worker = QueueTaskWorker(_repo_task, parent=ui)

                        def _on_repo_done(success: bool, payload: object, message: str) -> None:
                            if not success or not isinstance(payload, dict):
                                if message == _PKEXEC_CANCELLED:
                                    ui._install_busy = False
                                    return
                                ui._install_busy = False
                                QMessageBox.critical(ui, "Repo Add Failed", message or "Repo add failed")
                                return
                            repo_errors = payload.get("errors") or []
                            if repo_errors:
                                ui._install_busy = False
                                logger.error("repo add failed errors=%s", "; ".join(repo_errors))
                                QMessageBox.critical(
                                    ui,
                                    "Repo Add Failed",
                                    "Failed to add repositories:\n\n" + "\n".join(repo_errors)
                                )
                                return

                            _run_install(retry=True)

                        repo_worker.finished.connect(_on_repo_done)
                        repo_worker.finished.connect(repo_worker.deleteLater)
                        ui._task_threads.append(repo_worker)
                        repo_worker.start()
                        return

                if any(needle in combined for needle in ("no provider of", "nothing provides")):
                    QMessageBox.critical(
                        ui,
                        "Install Failed",
                        "Package not found in enabled repositories.\n\n"
                        "rtirq may not be available for this distro snapshot."
                    )
                else:
                    QMessageBox.critical(
                        ui,
                        "Install Failed",
                        f"Failed to install packages:\n\n{stderr or stdout}"
                    )
                ui._install_busy = False

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            ui._task_threads.append(worker)
            worker.start()

        ui._install_busy = True
        _run_install(retry=False)

    except Exception as e:
        QMessageBox.critical(ui, "Error", f"Install error: {e}")
        _log_gui_audit(
            "install-packages",
            {
                "commands": commands,
                "packages": packages,
                "cmd": cmd if "cmd" in locals() else None,
                "error": str(e),
            },
        )

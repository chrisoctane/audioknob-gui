"""Tests for GUI worker_api privileged helper behavior."""

from __future__ import annotations

import subprocess

import pytest

from audioknob_gui.gui import worker_api as api


def _cp(argv: list[str], *, rc: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, rc, stdout=stdout, stderr=stderr)


def test_validate_pkexec_command_allowlist_accepts_expected_commands() -> None:
    api._validate_pkexec_command(["/usr/sbin/usermod", "-aG", "audio", "chris"])
    api._validate_pkexec_command(["apt-get", "install", "-y", "rtirq-init"])
    api._validate_pkexec_command(["systemctl", "reboot"])
    api._validate_pkexec_command(["truncate", "--size", "0", "/var/lib/audioknob-gui/logs/worker.log"])
    api._validate_pkexec_command(["sdbootutil", "update-all-entries"])


def test_validate_pkexec_command_rejects_unlisted_commands() -> None:
    with pytest.raises(RuntimeError, match="Refused privileged command outside allowlist"):
        api._validate_pkexec_command(["/bin/sh", "-c", "echo risky"])


def test_validate_pkexec_command_rejects_systemctl_non_exact_reboot() -> None:
    with pytest.raises(RuntimeError, match="outside reboot"):
        api._validate_pkexec_command(["systemctl", "reboot", "--force"])


def test_validate_pkexec_command_rejects_truncate_non_worker_log_path() -> None:
    with pytest.raises(RuntimeError, match="outside zero-size log clear"):
        api._validate_pkexec_command(["truncate", "--size", "0", "/etc/shadow"])


def test_pick_root_worker_path_refuses_dev_repo_mismatch(monkeypatch, tmp_path) -> None:
    worker = tmp_path / "audioknob-gui-worker"
    worker.write_text("#!/bin/sh\n", encoding="utf-8")
    worker.chmod(0o755)

    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setenv("AUDIOKNOB_DEV_REPO", str(repo))
    monkeypatch.setattr(api, "_root_worker_path_candidates", lambda: [str(worker)])
    monkeypatch.setattr(api, "_configured_root_worker_repo", lambda: "")

    with pytest.raises(RuntimeError, match="Repo GUI is running in dev mode"):
        api._pick_root_worker_path()


def test_pick_root_worker_path_allows_matching_dev_repo(monkeypatch, tmp_path) -> None:
    worker = tmp_path / "audioknob-gui-worker"
    worker.write_text("#!/bin/sh\n", encoding="utf-8")
    worker.chmod(0o755)

    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setenv("AUDIOKNOB_DEV_REPO", str(repo))
    monkeypatch.setattr(api, "_root_worker_path_candidates", lambda: [str(worker)])
    monkeypatch.setattr(api, "_configured_root_worker_repo", lambda: str(repo))

    assert api._pick_root_worker_path() == str(worker)


def test_run_worker_reset_defaults_user_parses_json_even_on_nonzero_exit(monkeypatch) -> None:
    payload = '{"schema":1,"reset_count":0,"results":[],"errors":["x"],"scope":"user","needs_root_reset":false}'

    monkeypatch.setattr(
        api.subprocess,
        "run",
        lambda *args, **kwargs: _cp(args[0], rc=1, stdout=payload, stderr=""),
    )

    result = api._run_worker_reset_defaults_user()
    assert result["scope"] == "user"
    assert result["errors"] == ["x"]


def test_run_worker_reset_defaults_pkexec_cancel_maps_to_cancel_token(monkeypatch) -> None:
    monkeypatch.setattr(api, "_pkexec_available", lambda: True)
    monkeypatch.setattr(api, "_pick_root_worker_path", lambda: "/usr/libexec/audioknob-gui-worker")
    monkeypatch.setattr(
        api.subprocess,
        "run",
        lambda *args, **kwargs: _cp(args[0], rc=1, stdout="", stderr="Authentication canceled"),
    )

    with pytest.raises(RuntimeError) as exc:
        api._run_worker_reset_defaults_pkexec()
    assert str(exc.value) == api._PKEXEC_CANCELLED

"""Real check probes and SSH failure behavior."""

from __future__ import annotations

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_check_reports_real_success(live_project) -> None:
    project = live_project()
    before = project.sandbox.exec(
        "server", "find", project.remote_root, "-mindepth", "1", "-print"
    ).stdout

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "ssh login good" in text
    assert "root dir exists" in text
    assert "DB(demo) as sink" in text
    after = project.sandbox.exec(
        "server", "find", project.remote_root, "-mindepth", "1", "-print"
    ).stdout
    assert after == before
    assert project.sandbox.credentials_files() == []


def test_check_reports_a_bad_mysql_password(live_project) -> None:
    project = live_project(mysql_password="wrong-password")  # noqa: S106

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "[✗]" in text
    assert "Access denied" in text or "ERROR 1045" in text


def test_check_rejects_an_unknown_host_key(live_project, monkeypatch) -> None:
    project = live_project()
    empty_known_hosts = project.path / "empty-known-hosts"
    empty_known_hosts.write_text("")
    empty_known_hosts.chmod(0o600)
    monkeypatch.setenv("SINK_TEST_KNOWN_HOSTS", str(empty_known_hosts))

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "ssh login failed" in text
    assert (
        "Host key verification failed" in text
        or "REMOTE HOST IDENTIFICATION HAS CHANGED" in text
    )


def test_check_reports_a_bad_ssh_user(live_project) -> None:
    project = live_project(ssh_overrides={"username": "nobody"})

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "ssh login failed" in text
    assert "nobody" in text

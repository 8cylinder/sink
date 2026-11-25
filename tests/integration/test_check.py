"""Real check probes and SSH failure behavior."""

from __future__ import annotations

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_check_reports_real_success(live_project) -> None:
    project = live_project()

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "ssh login good" in text
    assert "root dir exists" in text
    assert "DB(demo) as sink" in text


def test_check_reports_a_bad_mysql_password(live_project) -> None:
    project = live_project(mysql_password="wrong-password")  # noqa: S106

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "[✗]" in text
    assert "Access denied" in text or "ERROR 1045" in text


def test_check_rejects_an_unknown_host_key(live_project, monkeypatch) -> None:
    project = live_project()
    empty_home = project.path / "empty-home"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "ssh login failed" in text
    assert (
        "Host key verification failed" in text
        or "REMOTE HOST IDENTIFICATION HAS CHANGED" in text
    )

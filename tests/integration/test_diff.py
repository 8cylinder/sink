"""Real rsync and git diff behavior against the Docker server."""

from __future__ import annotations

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_diff_reports_identical_files(live_project) -> None:
    project = live_project()
    project.remote_write("index.html", "local index\n")

    result = project.invoke("diff", "dev", "project/index.html", "--real")

    assert result.exit_code == 0, combined(result)
    assert "Files are the same." in combined(result)


def test_diff_reports_a_changed_file(live_project, capfd) -> None:
    project = live_project()
    project.remote_write("index.html", "remote index\n")

    result = project.invoke("diff", "dev", "project/index.html", "--real")

    captured = capfd.readouterr()
    assert result.exit_code == 1, combined(result)
    assert "remote index" in captured.out + captured.err


def test_diff_reports_a_missing_remote_file(live_project) -> None:
    project = live_project()

    result = project.invoke("diff", "dev", "project/missing.txt", "--real")

    assert result.exit_code != 0, combined(result)

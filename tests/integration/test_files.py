"""Real rsync transfers against the Docker server."""

from __future__ import annotations

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_file_put_and_pull(live_project) -> None:
    project = live_project()

    result = project.invoke(
        "file", "put", "dev", "project/index.html", "--real"
    )
    assert result.exit_code == 0, combined(result)
    assert project.remote_read("index.html") == "local index\n"

    project.remote_write("index.html", "remote index\n")
    result = project.invoke(
        "file", "pull", "dev", "project/index.html", "--real"
    )
    assert result.exit_code == 0, combined(result)
    assert (project.path / "project" / "index.html").read_text() == (
        "remote index\n"
    )


def test_directory_put_honors_exclusions(live_project) -> None:
    project = live_project()
    (project.path / "project" / ".env").write_text("do not upload\n")

    result = project.invoke("file", "put", "dev", "project", "--real")

    assert result.exit_code == 0, combined(result)
    assert project.remote_exists("index.html")
    assert project.remote_exists("sub/file.txt")
    assert not project.remote_exists(".env")


def test_dry_run_does_not_mutate_the_remote(live_project) -> None:
    project = live_project()

    result = project.invoke("file", "put", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert not project.remote_exists("index.html")


def test_warn_declined_does_not_overwrite(live_project) -> None:
    project = live_project(warn=True)

    result = project.invoke(
        "file",
        "put",
        "dev",
        "project/index.html",
        "--real",
        input="n\n",
    )

    assert result.exit_code == 0, combined(result)
    assert not project.remote_exists("index.html")

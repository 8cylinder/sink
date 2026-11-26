"""Hostile filenames, paths, and tags against the real Docker server."""

from __future__ import annotations

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_filenames_with_spaces_and_unicode_round_trip(live_project) -> None:
    project = live_project()
    name = "sp ace-\u00fc.txt"
    local = project.path / "project" / name
    local.write_text("payload\n")

    result = project.invoke("file", "put", "dev", f"project/{name}", "--real")

    assert result.exit_code == 0, combined(result)
    assert project.remote_read(name) == "payload\n"

    project.remote_write(name, "changed\n")
    result = project.invoke("file", "pull", "dev", f"project/{name}", "--real")

    assert result.exit_code == 0, combined(result)
    assert local.read_text() == "changed\n"


def test_paths_outside_the_project_root_are_rejected(live_project) -> None:
    project = live_project()
    outside = project.path / "outside.txt"
    outside.write_text("outside\n")

    result = project.invoke("file", "put", "dev", str(outside), "--real")

    assert result.exit_code != 0, combined(result)
    assert "outside the project root" in combined(result)
    assert not project.remote_exists("outside.txt")

    link = project.path / "project" / "link.txt"
    link.symlink_to(outside)
    result = project.invoke("file", "put", "dev", "project/link.txt", "--real")

    assert result.exit_code != 0, combined(result)
    assert "outside the project root" in combined(result)
    assert not project.remote_exists("link.txt")


def test_shell_syntax_in_a_filename_never_runs(live_project) -> None:
    project = live_project()
    name = "pwn-$(touch sink-pwned).txt"
    (project.path / "project" / name).write_text("payload\n")

    # Whether rsync accepts the name or rejects it, no remote or local shell
    # may evaluate the ``$(...)`` fragment.
    project.invoke("file", "put", "dev", f"project/{name}", "--real")

    remote_home = project.sandbox.exec(
        "server",
        "test",
        "-e",
        "/home/deploy/sink-pwned",
        check=False,
    )
    assert remote_home.returncode != 0
    assert not project.remote_exists("sink-pwned")
    assert not (project.path / "sink-pwned").exists()
    assert not (project.path / "project" / "sink-pwned").exists()


def test_db_pull_tag_cannot_escape_the_pulls_directory(live_project) -> None:
    project = live_project()

    result = project.invoke(
        "db",
        "pull",
        "dev",
        "--tag",
        "../../../escape",
        "--real",
    )

    assert result.exit_code != 0, combined(result)
    assert "tag" in combined(result).lower()
    assert not (project.path / "escape.sql.gz").exists()
    assert not (project.path.parent / "escape.sql.gz").exists()
    assert not list((project.path / "pulls").glob("*escape*"))


def test_database_password_is_never_rendered(live_project) -> None:
    project = live_project()

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert project.db_password not in text
    assert "defaults-extra-file=" in text

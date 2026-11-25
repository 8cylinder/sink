"""Remote database dump and load paths outside the local pipelines."""

from __future__ import annotations

import pytest
from helpers import commands_named

from sink.config.loader import load
from sink.db import DB


def _db(project) -> DB:
    """Build a real-mode DB helper from the fixture project."""
    config = load(project.path / "sink.yaml")
    return DB(config.project, config.server("dev"), real=True)


def test_dump_remote_writes_through_sudo_tee(project_factory) -> None:
    project = project_factory()
    destination = project.path / "remote.sql.gz"

    _db(project).dump_remote(destination)

    fragments = [
        command.args[-1] for command in commands_named(project.stub_log, "ssh")
    ]
    dump = next(fragment for fragment in fragments if "mysqldump" in fragment)
    assert "gzip -c | sudo tee" in dump
    assert str(destination) in dump
    assert not destination.exists()


def test_load_remote_tests_and_streams_the_remote_file(
    project_factory,
) -> None:
    project = project_factory()

    _db(project).load_remote("remote.sql.gz")

    fragments = [
        command.args[-1] for command in commands_named(project.stub_log, "ssh")
    ]
    assert any("test -f remote.sql.gz" in fragment for fragment in fragments)
    assert any("zcat remote.sql.gz" in fragment for fragment in fragments)


def test_load_remote_stops_when_the_remote_file_is_missing(
    project_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUB_EXIT_SSH", "1")
    project = project_factory()

    with pytest.raises(SystemExit):
        _db(project).load_remote("remote.sql.gz")

    fragments = [
        command.args[-1] for command in commands_named(project.stub_log, "ssh")
    ]
    assert any("test -f remote.sql.gz" in fragment for fragment in fragments)
    assert all("zcat" not in fragment for fragment in fragments)

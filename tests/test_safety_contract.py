"""Safety contract tests for database paths and destructive writes.

These tests cover invariants S3 (paths stay inside the project), S4 (warn
requires confirmation), S10 (a failed pull never looks successful), and S14
(a pull never overwrites an existing dump).  The Docker-backed counterparts
live in ``tests/integration``.
"""

from __future__ import annotations

import datetime
import gzip
from pathlib import Path

import pytest
from helpers import combined, commands_named

from sink.config.models import DatabaseConfig, Project, Server
from sink.db import DB
from sink.shell import Result


def _server(warn: bool = False) -> Server:
    """Return a server with one database for direct DB tests."""
    return Server(
        name="dev",
        databases=(
            DatabaseConfig(
                db="demo",
                username="sink",
                password="secret",  # noqa: S106 - test fixture
            ),
        ),
        warn=warn,
    )


def _project(root: Path) -> Project:
    """Return a project rooted at *root* with a pulls directory."""
    return Project(name="demo", root=root, pulls_dir=root / "pulls")


def _gzip_dump(project, name: str = "dump.sql.gz") -> str:
    """Write a valid gzipped dump and return its project-relative path."""
    path = project.path / name
    path.write_bytes(gzip.compress(b"SELECT 1;\n"))
    return name


@pytest.mark.xfail(
    strict=True,
    reason="B25: a db pull tag may escape pulls_dir",
)
def test_db_pull_rejects_a_path_traversal_tag(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "pull", "dev", "--tag", "../../../escape")

    assert result.exit_code != 0, combined(result)
    assert "tag" in combined(result).lower()


@pytest.mark.xfail(
    strict=True,
    reason="B26: db put does not honor warn before overwriting",
)
def test_db_put_requires_confirmation_when_warn(project_factory) -> None:
    project = project_factory(warn=True)
    filename = _gzip_dump(project)

    result = project.invoke(
        "db",
        "put",
        "dev",
        filename,
        "--real",
        input="n\n",
    )

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() == ""


def test_db_put_proceeds_when_warn_is_confirmed(project_factory) -> None:
    project = project_factory(warn=True)
    filename = _gzip_dump(project)

    result = project.invoke(
        "db",
        "put",
        "dev",
        filename,
        "--real",
        input="y\n",
    )

    assert result.exit_code == 0, combined(result)
    assert commands_named(project.stub_log, "ssh")


@pytest.mark.xfail(
    strict=True,
    reason="B27: dumps created within one second overwrite each other",
)
def test_db_pull_does_not_overwrite_a_same_second_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    db = DB(_project(tmp_path), _server(), real=True)
    frozen = datetime.datetime(2026, 11, 26, 12, 0, 0, tzinfo=datetime.UTC)

    class FrozenDateTime:
        """A clock that does not advance between pulls."""

        @staticmethod
        def now(tz=None):
            _ = tz
            return frozen

    monkeypatch.setattr("sink.db.datetime.datetime", FrozenDateTime)

    def fake_pull(sqlfile, local: bool = True) -> None:
        """Stand in for the remote pipeline and write the destination."""
        _ = local
        Path(sqlfile).write_text("dump")

    monkeypatch.setattr(db, "_pull", fake_pull)

    db.pull()
    db.pull()

    assert len(list(pulls.glob("*.sql.gz"))) == 2


@pytest.mark.xfail(
    strict=True,
    reason="B28: a failed pull leaves a partial dump on disk",
)
def test_db_failed_pull_removes_the_partial_dump(tmp_path: Path) -> None:
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    db = DB(_project(tmp_path), _server(), real=True)
    partial = pulls / "partial.sql.gz"
    partial.write_bytes(b"partial")

    with pytest.raises(SystemExit):
        db._report_pull(Result(1, "", "boom"), partial, True)

    assert not partial.exists()

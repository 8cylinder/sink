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
from sink.rsync import Transfer
from sink.shell import Result


def _server(warn: bool = False, name: str = "dev") -> Server:
    """Return a server with one database for direct DB tests."""
    return Server(
        name=name,
        databases=(
            DatabaseConfig(
                db="demo",
                username="sink",
                password="secret",  # noqa: S106 - test fixture
            ),
        ),
        warn=warn,
    )


def _project(root: Path, name: str = "demo") -> Project:
    """Return a project rooted at *root* with a pulls directory."""
    return Project(name=name, root=root, pulls_dir=root / "pulls")


def _gzip_dump(project, name: str = "dump.sql.gz") -> str:
    """Write a valid gzipped dump and return its project-relative path."""
    path = project.path / name
    path.write_bytes(gzip.compress(b"SELECT 1;\n"))
    return name


def test_db_pull_rejects_a_path_traversal_tag(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "pull", "dev", "--tag", "../../../escape")

    assert result.exit_code != 0, combined(result)
    assert "tag" in combined(result).lower()


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


def test_db_pull_does_not_overwrite_a_same_second_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    pulls.chmod(0o700)
    db = DB(_project(tmp_path), _server(), real=True)
    frozen = datetime.datetime(2026, 11, 26, 12, 0, 0, tzinfo=datetime.UTC)

    class FrozenDateTime:
        """A clock that does not advance between pulls."""

        @staticmethod
        def now(tz=None):
            _ = tz
            return frozen

    monkeypatch.setattr("sink.db.datetime.datetime", FrozenDateTime)

    def fake_pull(
        sqlfile, local: bool = True, final: Path | None = None
    ) -> None:
        """Stand in for the remote pipeline and commit the destination."""
        _ = sqlfile, local
        assert final is not None
        final.write_text("dump")

    monkeypatch.setattr(db, "_pull", fake_pull)

    db.pull()
    db.pull()

    assert len(list(pulls.glob("*.sql.gz"))) == 2


def test_db_failed_pull_removes_the_partial_dump(tmp_path: Path) -> None:
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    pulls.chmod(0o700)
    db = DB(_project(tmp_path), _server(), real=True)
    partial = pulls / "partial.sql.gz"
    partial.write_bytes(b"partial")

    with pytest.raises(SystemExit):
        db._report_pull(Result(1, "", "boom"), partial, True)

    assert not partial.exists()


def test_db_dump_path_stays_inside_pulls_for_hostile_names(
    tmp_path: Path,
) -> None:
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    pulls.chmod(0o700)
    project = _project(tmp_path, name="../../project-escape")
    server = _server(name="../../server-escape")
    db = DB(project, server)

    path = db._dest(project.name, pulls, server.name, None)

    assert path.resolve(strict=False).parent == pulls.resolve()


def test_latest_symlink_stays_inside_pulls_for_hostile_server(
    tmp_path: Path,
) -> None:
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    pulls.chmod(0o700)
    db = DB(_project(tmp_path), _server(name="../../escape"), real=True)
    dump = pulls / "dump.sql.gz"
    dump.write_text("x")

    db.make_symlink(dump)

    links = list(pulls.glob("LATEST-*"))
    assert len(links) == 1
    assert links[0].parent == pulls
    assert links[0].is_symlink()


def test_environment_expansion_is_not_shell_syntax(
    project_factory, monkeypatch, tmp_path: Path
) -> None:
    marker = tmp_path / "sink-pwned"
    monkeypatch.setenv("SINK_TEST_HOSTILE", f"$(touch {marker})")
    project = project_factory(
        project_overrides={"exclude": ["${SINK_TEST_HOSTILE}"]}
    )

    result = project.invoke("file", "put", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert rsync
    assert any(f"$(touch {marker})" in arg for arg in rsync[0].args)
    assert not marker.exists()


def test_interrupted_pull_removes_only_new_rsync_temp_files(
    tmp_path: Path,
) -> None:
    local = tmp_path / "remote.bin"
    local.write_text("complete")
    backup = tmp_path / ".remote.bin.backup"
    backup.write_text("keep")
    swap = tmp_path / ".remote.bin.swp"
    swap.write_text("keep")
    unrelated = tmp_path / ".other.bin.14r3Y9"
    unrelated.write_text("keep")
    temporary = tmp_path / ".remote.bin.14r3Y9"
    temporary.write_text("partial")
    before = {local, backup, swap, unrelated}

    Transfer._remove_pull_temp(local, before)

    assert local.exists()
    assert backup.exists()
    assert swap.exists()
    assert unrelated.exists()
    assert not temporary.exists()


def test_interrupted_pull_removes_the_temp_before_reraising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transfer = Transfer(_project(tmp_path), Server(name="dev", root=tmp_path))
    local = tmp_path / "remote.bin"
    backup = tmp_path / ".remote.bin.backup"
    backup.write_text("keep")
    temporary = tmp_path / ".remote.bin.abc123"

    def interrupted(*args, **kwargs) -> None:
        _ = args, kwargs
        temporary.write_text("partial")
        raise KeyboardInterrupt

    monkeypatch.setattr(transfer, "_rsync", interrupted)

    with pytest.raises(KeyboardInterrupt):
        transfer.pull(local, None)

    assert backup.exists()
    assert not temporary.exists()

"""SEC-04: private local dumps and out-of-band local credentials."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import combined, write_gzip

from sink.config.models import DatabaseConfig, Project, Server
from sink.credentials import local_mysql_credentials
from sink.db import DB
from sink.errors import CommandError


def _server() -> Server:
    """Return a server with one database for direct DB tests."""
    return Server(
        name="dev",
        databases=(
            DatabaseConfig(
                db="demo",
                username="deploy",
                password="secret",  # noqa: S106 - test fixture
            ),
        ),
    )


def _project(root: Path) -> Project:
    """Return a project rooted at *root* with a pulls directory."""
    return Project(name="demo", root=root, pulls_dir=root / "pulls")


def test_local_credentials_file_is_private() -> None:
    with local_mysql_credentials(
        user="deploy",
        password="secret",  # noqa: S106 - test fixture
        host="db",
        port=3306,
        real=True,
    ) as credentials:
        assert credentials.path.stat().st_mode & 0o777 == 0o600
        assert credentials.path.parent.stat().st_mode & 0o777 == 0o700
        body = credentials.path.read_text()
        assert 'user="deploy"' in body
        assert 'password="secret"' in body
        assert 'host="db"' in body
        assert "port=3306" in body

    assert not credentials.path.exists()
    assert not credentials.path.parent.exists()


def test_local_credentials_keep_legacy_auth_setting() -> None:
    with local_mysql_credentials(
        password="secret",  # noqa: S106 - test fixture
        skip_secure_auth="yes",
        real=True,
    ) as credentials:
        assert "skip-secure-auth" in credentials.path.read_text()


def test_local_credentials_dry_run_does_not_write() -> None:
    with local_mysql_credentials(
        password="secret",  # noqa: S106 - test fixture
        real=False,
    ) as credentials:
        assert not credentials.path.exists()

    assert not credentials.path.parent.exists()


def test_ensure_pulls_dir_creates_0700(tmp_path: Path) -> None:
    db = DB(_project(tmp_path), _server(), real=True)

    pulls = db._ensure_pulls_dir()

    assert pulls == tmp_path / "pulls"
    assert pulls.stat().st_mode & 0o777 == 0o700


def test_ensure_pulls_dir_refuses_world_readable(tmp_path: Path) -> None:
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    pulls.chmod(0o755)
    db = DB(_project(tmp_path), _server(), real=True)

    with pytest.raises(CommandError, match="chmod 700"):
        db._ensure_pulls_dir()


def test_db_pull_writes_a_private_dump(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    pulls = project.path / "pulls"
    dumps = list(pulls.glob("*.sql.gz"))
    assert dumps
    assert not list(pulls.glob("*.part*"))
    assert pulls.stat().st_mode & 0o777 == 0o700
    assert dumps[0].stat().st_mode & 0o777 == 0o600


def test_mamp_pull_uses_local_defaults_file(project_factory) -> None:
    project = project_factory(server_overrides={"mamp": "mamp"})

    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "MYSQL_PWD" not in text
    assert "--defaults-file=" in text
    assert "sink-mysql-local-" in text


def test_mamp_put_uses_local_defaults_file(project_factory) -> None:
    project = project_factory(server_overrides={"mamp": "mamp"})
    write_gzip(project.path / "project" / "dump.sql.gz")

    result = project.invoke("db", "put", "dev", "project/dump.sql.gz")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "MYSQL_PWD" not in text
    assert "--defaults-file=" in text
    assert "sink-mysql-local-" in text

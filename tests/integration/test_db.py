"""Real MySQL pull and push behavior against the Docker stack."""

from __future__ import annotations

import datetime
import gzip
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_db_pull_uses_special_password_and_cleans_up(live_project) -> None:
    project = live_project()
    project.sandbox.db_query("UPDATE widgets SET name='alpha' WHERE id=1")

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    dumps = sorted((project.path / "pulls").glob("demo-dev-*.sql.gz"))
    assert len(dumps) == 1
    sql = gzip.decompress(dumps[0].read_bytes()).decode()
    assert "widgets" in sql
    assert "alpha" in sql
    assert (project.path / "pulls" / "LATEST-dev.sql.gz").is_symlink()
    assert project.sandbox.credentials_files() == []


def test_db_pull_writes_a_private_dump(live_project) -> None:
    project = live_project()

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    pulls = project.path / "pulls"
    dumps = list(pulls.glob("demo-dev-*.sql.gz"))
    assert dumps
    assert not list(pulls.glob("*.part*"))
    assert pulls.stat().st_mode & 0o777 == 0o700
    assert dumps[0].stat().st_mode & 0o777 == 0o600


def test_db_put_loads_a_gzipped_dump(live_project) -> None:
    project = live_project()
    dump = project.path / "put.sql.gz"
    dump.write_bytes(
        gzip.compress(
            b"DROP TABLE IF EXISTS put_data;"
            b"CREATE TABLE put_data (id INT PRIMARY KEY, name VARCHAR(50));"
            b"INSERT INTO put_data VALUES (1, 'put-value');"
        )
    )

    result = project.invoke("db", "put", "dev", "put.sql.gz", "--real")

    assert result.exit_code == 0, combined(result)
    output = project.sandbox.db_query("SELECT name FROM put_data WHERE id = 1")
    assert "put-value" in output
    assert project.sandbox.credentials_files() == []


def test_db_pull_with_a_bad_password_reports_the_error(
    live_project,
) -> None:
    project = live_project(mysql_password="wrong-password")  # noqa: S106

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code != 0, combined(result)
    text = combined(result)
    assert "Access denied" in text or "ERROR 1045" in text
    assert not (project.path / "pulls" / "LATEST-dev.sql.gz").exists()
    assert not list((project.path / "pulls").glob("demo-dev-*.sql.gz"))
    assert not list((project.path / "pulls").glob("*.part*"))
    assert project.sandbox.credentials_files() == []


def test_db_pull_does_not_overwrite_a_same_second_dump(
    live_project, monkeypatch
) -> None:
    project = live_project()
    frozen = datetime.datetime(2026, 11, 26, 12, 0, 0, tzinfo=datetime.UTC)

    class FrozenDateTime:
        """A clock that does not advance between pulls."""

        @staticmethod
        def now(tz=None):
            _ = tz
            return frozen

    monkeypatch.setattr("sink.db.datetime.datetime", FrozenDateTime)

    first = project.invoke("db", "pull", "dev", "--real")
    second = project.invoke("db", "pull", "dev", "--real")

    assert first.exit_code == 0, combined(first)
    assert second.exit_code == 0, combined(second)
    dumps = sorted((project.path / "pulls").glob("demo-dev-*.sql.gz"))
    assert len(dumps) == 2
    latest = (project.path / "pulls" / "LATEST-dev.sql.gz").resolve()
    assert latest.name in {dump.name for dump in dumps}
    assert latest.name.endswith("-2.sql.gz")
    assert project.sandbox.credentials_files() == []


def test_db_pull_uses_the_first_database_entry(live_project) -> None:
    project = live_project(
        extra_databases=[
            {
                "username": "nopriv",
                "password": "wrong",
                "db": "demo",
                "hostname": "db",
                "ssl_mode": "DISABLED",
            }
        ]
    )

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    dumps = list((project.path / "pulls").glob("demo-dev-*.sql.gz"))
    assert len(dumps) == 1
    assert project.sandbox.credentials_files() == []


def test_concurrent_tagged_pulls_keep_both_dumps_and_latest(
    live_project,
) -> None:
    project = live_project()

    def pull(tag: str) -> subprocess.CompletedProcess[str]:
        result = project.run("db", "pull", "dev", "--tag", tag, "--real")
        return cast("subprocess.CompletedProcess[str]", result)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pull, ("a", "b")))

    for result in results:
        assert result.returncode == 0, result.stdout + result.stderr
    dumps = sorted(
        [
            *(project.path / "pulls").glob("demo-dev-*-a.sql.gz"),
            *(project.path / "pulls").glob("demo-dev-*-b.sql.gz"),
        ]
    )
    assert len(dumps) == 2
    for dump in dumps:
        assert "widgets" in gzip.decompress(dump.read_bytes()).decode()
    latest = (project.path / "pulls" / "LATEST-dev.sql.gz").resolve()
    assert latest.name in {dump.name for dump in dumps}
    assert project.sandbox.credentials_files() == []

"""Real MySQL pull and push behavior against the Docker stack."""

from __future__ import annotations

import gzip

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_db_pull_uses_special_password_and_cleans_up(live_project) -> None:
    project = live_project()

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    dumps = sorted((project.path / "pulls").glob("demo-dev-*.sql.gz"))
    assert len(dumps) == 1
    sql = gzip.decompress(dumps[0].read_bytes()).decode()
    assert "widgets" in sql
    assert "alpha" in sql
    assert (project.path / "pulls" / "LATEST-dev.sql.gz").is_symlink()
    assert project.sandbox.credentials_files() == []


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
    assert project.sandbox.credentials_files() == []

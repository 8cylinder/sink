"""Stage 8 database safety, progress, and backend contract tests."""

from __future__ import annotations

import gzip
from pathlib import Path

from helpers import combined, commands_named, unwrap


def gzip_dump(project, name: str = "dump.sql.gz") -> str:
    """Write a valid gzipped dump inside the project and return its path."""
    path = project.path / "project" / name
    path.write_bytes(gzip.compress(b"SELECT 1;\n"))
    return f"project/{name}"


def test_db_put_rejects_a_non_gzip_file(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "put", "dev", "project/index.html")

    assert result.exit_code != 0
    assert "gzip" in combined(result).lower()
    assert project.stub_log.read_text() == ""


def test_db_put_rejects_a_fake_gz_suffix(project_factory) -> None:
    project = project_factory()
    fake = project.path / "project" / "fake.sql.gz"
    fake.write_text("not gzip\n")

    result = project.invoke("db", "put", "dev", "project/fake.sql.gz")

    assert result.exit_code != 0
    assert "gzip" in combined(result).lower()


def test_db_put_requires_a_configured_database(project_factory) -> None:
    project = project_factory(server_overrides={"mysql": []})
    filename = gzip_dump(project)

    result = project.invoke("db", "put", "dev", filename)

    assert result.exit_code != 0
    assert "database" in combined(result).lower()


def test_db_put_uses_cat_by_default(project_factory) -> None:
    project = project_factory()
    filename = gzip_dump(project)

    result = project.invoke("db", "put", "dev", filename)

    assert result.exit_code == 0, combined(result)
    text = unwrap(combined(result))
    assert "cat project/dump.sql.gz" in text
    assert "pv --numeric" not in text


def test_db_put_uses_pv_when_enabled(project_factory) -> None:
    project = project_factory(project_overrides={"pv": True})
    filename = gzip_dump(project)

    result = project.invoke("db", "put", "dev", filename)

    assert result.exit_code == 0, combined(result)
    assert "pv --numeric project/dump.sql.gz" in unwrap(combined(result))


def test_db_put_falls_back_when_pv_is_missing(project_factory) -> None:
    project = project_factory(project_overrides={"pv": True})
    (project.bin_dir / "pv").unlink()
    filename = gzip_dump(project)

    result = project.invoke("db", "put", "dev", filename)

    assert result.exit_code == 0, combined(result)
    text = unwrap(combined(result))
    assert "cat project/dump.sql.gz" in text
    assert "pv --numeric" not in text


def test_db_pull_uses_mysqlpump_when_enabled(project_factory) -> None:
    project = project_factory(project_overrides={"mysqlpump": True})

    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    text = unwrap(combined(result))
    assert "mysqlpump" in text
    assert "--watch-progress" in text
    assert "mysqldump" not in text


def test_db_put_does_not_execute_without_real(project_factory) -> None:
    project = project_factory()
    filename = gzip_dump(project)

    result = project.invoke("db", "put", "dev", filename)

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() == ""


def test_db_put_real_sends_the_dump(project_factory) -> None:
    project = project_factory()
    filename = gzip_dump(project)

    result = project.invoke("db", "put", "dev", filename, "--real")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert commands_named(project.stub_log, "ssh")
    assert project.stub_log.read_text() != ""


def test_db_put_real_uses_pv_when_enabled(project_factory) -> None:
    project = project_factory(project_overrides={"pv": True})
    filename = gzip_dump(project)

    result = project.invoke("db", "put", "dev", filename, "--real")

    assert result.exit_code == 0, combined(result)
    assert commands_named(project.stub_log, "pv")
    assert commands_named(project.stub_log, "ssh")


def test_db_timestamps_use_aware_datetime() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src/sink/db.py"
    ).read_text()
    assert "datetime.datetime.now()" not in source
    assert "astimezone()" in source

"""Stage 9 check reporting and path-cleanup contract tests."""

from __future__ import annotations

from pathlib import Path

from helpers import combined


def test_check_reports_project_and_server_fields(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "rsync_binary" in text
    assert "pulls_dir" in text
    assert "warn" in text
    assert "automatic" in text
    assert project.stub_log.read_text() == ""


def test_check_reports_a_missing_rsync_binary(project_factory) -> None:
    project = project_factory(
        project_overrides={"rsync_binary": "missing-rsync-binary"}
    )

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert "missing-rsync-binary" in combined(result)
    assert "missing" in combined(result)


def test_check_dry_run_prints_url_probes(project_factory) -> None:
    project = project_factory(urls=[{"url": "https://example.test"}])

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert "+ URL(https://example.test)" in combined(result)
    assert project.stub_log.read_text() == ""


def test_db_pull_creates_the_latest_symlink(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    latest = project.path / "pulls" / "LATEST-dev.sql.gz"
    assert latest.is_symlink()
    assert latest.resolve().name.startswith("demo-dev-")


def test_no_os_chdir_remains_in_database_or_check_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("db.py", "check.py"):
        source = (root / "src/sink" / name).read_text()
        assert "os.chdir" not in source

"""Characterization tests for the commands sink renders today.

These pin the current dry-run text before the execution-layer refactor.  The
normalizer removes only values that change on every run: the fixture path,
timestamps, temporary diff directories, and generated deploy codenames.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from helpers import combined, commands_named, unwrap

GOLDEN = Path(__file__).parent / "fixtures" / "golden"


def normalize(text: str, project) -> str:
    text = unwrap(text)
    text = text.replace(str(project.path / "project"), "<PROJECT_ROOT>")
    text = text.replace(str(project.path), "<CONFIG_DIR>")
    text = re.sub(
        r"/tmp/tmp\w+\s+\[dev\]",  # noqa: S108 - path made by tempfile
        "<DIFFDIR> [dev]",
        text,
    )
    text = re.sub(
        r"\b\d{2}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\b", "<DB_STAMP>", text
    )
    text = re.sub(
        r"dev--\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}--[a-z]+-[a-z]+",
        "dev--<DEPLOY_STAMP>",
        text,
    )
    text = re.sub(r"sink-mysql-[0-9a-f]+\.cnf", "<CREDS_FILE>", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(lines).strip("\n") + "\n"


def assert_golden(name: str, text: str, project) -> None:
    actual = normalize(text, project)
    path = GOLDEN / f"{name}.txt"
    if os.environ.get("SINK_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual)
    expected = path.read_text()
    assert actual == expected


def test_file_put_root_golden(project_factory) -> None:
    project = project_factory()
    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert_golden("file-put-root", combined(result), project)


def test_file_put_file_golden(project_factory) -> None:
    project = project_factory()
    result = project.invoke("file", "put", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert_golden("file-put-file", combined(result), project)


def test_file_pull_golden(project_factory) -> None:
    project = project_factory()
    result = project.invoke("file", "pull", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert_golden("file-pull", combined(result), project)


def test_db_pull_golden(project_factory) -> None:
    project = project_factory()
    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    assert_golden("db-pull", combined(result), project)


def test_db_put_golden(project_factory) -> None:
    project = project_factory()
    result = project.invoke("db", "put", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert_golden("db-put", combined(result), project)


def test_deploy_local_init_golden(project_factory) -> None:
    project = project_factory()
    result = project.invoke("deploy", "-m", "local", "init", "dev")

    assert result.exit_code == 0, combined(result)
    assert_golden("deploy-local-init", combined(result), project)


def test_deploy_local_new_golden(project_factory) -> None:
    project = project_factory()
    result = project.invoke("deploy", "-m", "local", "new", "dev")

    assert result.exit_code == 0, combined(result)
    assert_golden("deploy-local-new", combined(result), project)


def test_diff_golden(project_factory) -> None:
    project = project_factory()
    result = project.invoke("diff", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert_golden("diff", combined(result), project)


def test_check_golden(project_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    # The spinner is a thread writing cursor frames; freeze it so the
    # characterization only covers the rendered probes and status lines.
    monkeypatch.setattr("sink.check.Spinner.start", lambda self: None)
    monkeypatch.setattr("sink.check.Spinner.stop", lambda self: None)

    project = project_factory()
    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert_golden("check", combined(result), project)


def test_file_put_uses_dry_run_by_default(project_factory) -> None:
    project = project_factory()
    project.invoke("file", "put", "dev")

    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    assert rsync[0].dry_run


def test_file_put_real_omits_dry_run(project_factory) -> None:
    project = project_factory()
    project.invoke("file", "put", "dev", "--real")

    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    assert not rsync[0].dry_run


def test_single_uses_the_automatic_server(project_factory) -> None:
    """Characterization: one automatic server is sent the file in dry-run."""
    project = project_factory()
    result = project.invoke("single", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert "Success (DRY RUN)" in combined(result)
    assert [c.name for c in commands_named(project.stub_log, "rsync")]

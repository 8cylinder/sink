"""Additional CLI branch coverage for commands and error paths."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import combined

from sink.cli import cli as sink
from sink.logging import configure as configure_logging


def test_action_remote_listing_and_run(project_factory) -> None:
    project = project_factory()

    listed = project.invoke("action", "dev")
    assert listed.exit_code == 0, combined(listed)
    assert "files" in listed.output

    dry = project.invoke("action", "dev", "files")
    assert dry.exit_code == 0, combined(dry)
    assert project.stub_log.read_text() == ""

    real = project.invoke("action", "dev", "files", "--real")
    assert real.exit_code == 0, combined(real)
    assert "ssh" in project.stub_log.read_text()


def test_action_missing_name(project_factory) -> None:
    project = project_factory()

    result = project.invoke("action", "dev", "missing")

    assert result.exit_code != 0
    assert "command not found" in combined(result)


def test_info_view(project_factory) -> None:
    project = project_factory()

    result = project.invoke("info")

    assert result.exit_code == 0, combined(result)
    assert "project:" in result.output


def test_info_edit_error_then_cancel(
    project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_factory()

    def bad_edit(filename):
        Path(filename).write_text("project: [unterminated\n")

    monkeypatch.setattr("sink.cli.info.click.edit", bad_edit)
    monkeypatch.setattr("sink.cli.info.click.confirm", lambda *_a, **_k: False)

    result = project.invoke("info", "--edit")

    assert result.exit_code == 0, combined(result)
    assert "error while parsing" in combined(result)


def test_misc_api_invalid_key_and_index(project_factory) -> None:
    project = project_factory()

    missing = project.invoke("misc", "api", "missing")
    assert missing.exit_code != 0
    assert "does not exist" in combined(missing)

    index = project.invoke("misc", "api", "project", "exclude", "99")
    assert index.exit_code != 0


def test_misc_settings_unknown_and_known(project_factory) -> None:
    project = project_factory()

    unknown = project.invoke("misc", "settings", "missing")
    assert unknown.exit_code == 0
    assert "Unknown application" in combined(unknown)
    assert "Known are" in combined(unknown)

    filezilla = project.invoke("misc", "settings", "filezilla")
    assert filezilla.exit_code == 0
    assert "SFTP" in combined(filezilla)


def test_misc_pack_and_init(project_factory) -> None:
    project = project_factory()

    packed = project.invoke("misc", "pack")
    assert packed.exit_code == 0, combined(packed)
    assert "tar -czvf" in packed.output

    initial = project.invoke("misc", "init", "dev", "prod")
    assert initial.exit_code == 0
    assert "dev:" in initial.output
    assert "prod:" in initial.output


def test_file_missing_path(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev", "missing.txt")

    assert result.exit_code != 0
    assert "Path does not exist" in combined(result)


def test_file_and_single_silent_aliases(project_factory) -> None:
    project = project_factory()

    file_result = project.invoke("file", "put", "dev", "--silent")
    single_result = project.invoke("single", "project/index.html", "--silent")

    assert file_result.exit_code == 0, combined(file_result)
    assert single_result.exit_code == 0, combined(single_result)
    assert file_result.output == ""
    assert single_result.output == ""


def test_db_put_without_sql_file(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "put", "dev")

    assert result.exit_code != 0
    assert "SQL-GZ is required" in combined(result)


def test_diff_difftool_and_word_diff(project_factory) -> None:
    project = project_factory()

    tool = project.invoke("diff", "dev", "project/index.html", "--difftool")
    assert tool.exit_code == 0, combined(tool)
    assert "meld" in combined(tool)

    word = project.invoke(
        "diff", "dev", "project/index.html", "--word-diff", "word"
    )
    assert "--word-diff=color" in combined(word)
    letter = project.invoke(
        "diff", "dev", "project/index.html", "--word-diff", "letter"
    )
    assert "--word-diff-regex=." in combined(letter)


def test_diff_without_a_configured_difftool(project_factory) -> None:
    project = project_factory(project_overrides={"difftool": None})

    result = project.invoke("diff", "dev", "project/index.html", "--difftool")

    assert result.exit_code != 0
    assert "No difftool" in combined(result)


def test_check_required_and_missing_fields(project_factory) -> None:
    project = project_factory(
        project_overrides={"pulls_dir": None},
        server_overrides={"ssh": [{"server": "example.com"}], "root": None},
    )

    required = project.invoke("check", "--required")
    assert required.exit_code == 0
    assert "ssh -V" in required.output

    checked = project.invoke("check", "dev")
    assert checked.exit_code == 0, combined(checked)
    assert "not configured" in combined(checked)
    assert "missing values for ssh" in combined(checked)


def test_check_real_failure(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "check", "dev", "--real", env={"STUB_EXIT_SSH": "1"}
    )

    assert result.exit_code == 0
    assert "ssh login failed" in combined(result)


def test_verbose_logging() -> None:
    configure_logging(2)
    configure_logging(1)


def test_completion_helpers_cover_paths() -> None:
    from sink.completions import _commands, generate_bash

    commands = list(_commands(sink))
    assert commands
    assert "_sink_complete" in generate_bash(sink, "sink", "0.3.0")

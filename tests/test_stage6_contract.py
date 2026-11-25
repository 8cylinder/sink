"""Stage 6 CLI/output contract tests."""

from __future__ import annotations

from click.testing import CliRunner
from helpers import combined

from sink.cli import cli as sink


def test_verbose_flag_is_accepted() -> None:
    result = CliRunner().invoke(sink, ["-v", "--version"])

    assert result.exit_code == 0, combined(result)


def test_success_label_format(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert "[Success (DRY RUN)]" in combined(result)


def test_db_quiet_flag_is_renamed() -> None:
    result = CliRunner().invoke(sink, ["db", "--help"])

    assert "--filename-only" in result.output
    assert "--quiet" not in result.output


def test_deploy_new_quiet_flag_is_renamed() -> None:
    result = CliRunner().invoke(sink, ["deploy", "new", "--help"])

    assert "--no-itemize" in result.output
    assert "--quiet" not in result.output


def test_root_help_has_no_literal_markup() -> None:
    result = CliRunner().invoke(sink, ["--help"])

    assert "[red]" not in result.output
    assert "[/]" not in result.output

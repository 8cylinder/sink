"""Stage 6 CLI/output contract tests."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from helpers import combined

from sink.sink import sink


@pytest.mark.xfail(
    strict=True, reason="Stage 6: add the root -v/--verbose count option"
)
def test_verbose_flag_is_accepted() -> None:
    result = CliRunner().invoke(sink, ["-v", "--version"])

    assert result.exit_code == 0, combined(result)


@pytest.mark.xfail(
    strict=True, reason="Stage 6: success labels use [Success] formatting"
)
def test_success_label_format(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert "[Success (DRY RUN)]" in combined(result)


@pytest.mark.xfail(
    strict=True, reason="Stage 6: db --quiet becomes --filename-only"
)
def test_db_quiet_flag_is_renamed() -> None:
    result = CliRunner().invoke(sink, ["db", "--help"])

    assert "--filename-only" in result.output
    assert "--quiet" not in result.output


@pytest.mark.xfail(
    strict=True, reason="Stage 6: deploy new --quiet becomes --no-itemize"
)
def test_deploy_new_quiet_flag_is_renamed() -> None:
    result = CliRunner().invoke(sink, ["deploy", "new", "--help"])

    assert "--no-itemize" in result.output
    assert "--quiet" not in result.output


@pytest.mark.xfail(
    strict=True, reason="N14: remove the literal rich markup from root help"
)
def test_root_help_has_no_literal_markup() -> None:
    result = CliRunner().invoke(sink, ["--help"])

    assert "[red]" not in result.output
    assert "[/]" not in result.output

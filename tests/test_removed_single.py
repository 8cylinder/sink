"""The obsolete single command has been removed from Sink."""

from __future__ import annotations

from click.testing import CliRunner
from helpers import combined

from sink.cli import cli
from sink.rsync import Transfer


def test_single_command_is_gone() -> None:
    result = CliRunner().invoke(cli, ["single", "project/index.html"])

    assert result.exit_code != 0
    assert "No such command 'single'" in combined(result)


def test_transfer_has_no_single_helper() -> None:
    assert not hasattr(Transfer, "single")

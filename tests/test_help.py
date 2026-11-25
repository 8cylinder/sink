"""Every command must answer -h/--help without a project."""

from __future__ import annotations

from collections.abc import Iterator

import click
import pytest
from click.testing import CliRunner
from helpers import combined

from sink.cli import cli as sink


def walk_commands(
    group: click.Group, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[str, ...]]:
    """Yield the path of every command, including nested groups."""
    for name, command in group.commands.items():
        path = (*prefix, name)
        yield path
        if isinstance(command, click.Group):
            yield from walk_commands(command, path)


COMMAND_PATHS = list(walk_commands(sink))


@pytest.mark.parametrize(
    ("path", "option"),
    [
        pytest.param(path, option, id=f"{'.'.join(path)}-{option}")
        for path in COMMAND_PATHS
        for option in ("-h", "--help")
    ],
)
def test_help_for_every_command(path: tuple[str, ...], option: str) -> None:
    result = CliRunner().invoke(sink, [*path, option])

    assert result.exit_code == 0, combined(result)
    assert "Usage:" in result.output
    assert "\x1b[" not in result.output


def test_root_help_needs_no_project() -> None:
    result = CliRunner().invoke(sink, ["--help"])

    assert result.exit_code == 0
    assert "Usage: sink" in result.output
    assert "\x1b[" not in result.output


def test_help_option_is_registered_on_every_command() -> None:
    """Catch a command that accidentally opts out of the -h convention."""
    for path in COMMAND_PATHS:
        result = CliRunner().invoke(sink, [*path, "--help"])
        assert "-h, --help" in result.output, ".".join(path)


def test_command_paths_are_not_empty() -> None:
    assert COMMAND_PATHS
    assert ("misc", "init") in COMMAND_PATHS

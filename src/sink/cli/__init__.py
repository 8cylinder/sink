"""Click command tree, base classes, and process entry point."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import click

from sink.completions import install_bash_completion
from sink.errors import SinkError
from sink.logging import configure as configure_logging
from sink.runtime import Runtime
from sink.ui import ui

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class AppCommand(click.Command):
    """Command base class with the shared help options."""


class AppGroup(click.Group):
    """Display commands in file order and render expected errors."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Keep commands in their registration order."""
        _ = ctx
        return list(self.commands.keys())

    def invoke(self, ctx: click.Context) -> int:
        """Render expected application errors without a traceback."""
        try:
            result = super().invoke(ctx)
            return int(result or 0)
        except SinkError as error:
            ui.error(f"{type(error).__name__}: {error}")
            return 1


def _version() -> str:
    """Return the installed Sink version."""
    try:
        return importlib.metadata.version("sink")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _config_callback(
    ctx: click.Context, _param: click.Parameter, value: bool
) -> None:
    """Print the discovered config path and exit."""
    if not value or ctx.resilient_parsing:
        return
    path = Runtime.discover_config(Path.cwd())
    if path is None:
        raise click.ClickException(
            "You are not in a project. A sink.yaml file was not found "
            "in this or any directory above."
        )
    click.echo(str(path))
    ctx.exit()


def _completions_callback(
    ctx: click.Context, _param: click.Parameter, value: bool
) -> None:
    """Install static bash completions and exit."""
    if not value or ctx.resilient_parsing:
        return
    path = install_bash_completion(cli, "sink", _version())
    click.echo(str(path))
    click.echo(
        f"To use it in this shell:\n  source {path}\n"
        "Server names are not completed; type them manually.",
        err=True,
    )
    ctx.exit()


@click.group(
    name="sink",
    cls=AppGroup,
    context_settings=CONTEXT_SETTINGS,
    no_args_is_help=True,
)
@click.option(
    "-q",
    "--quiet",
    count=True,
    help="Hide rendered commands; -qq hides all output.",
)
@click.option(
    "-s",
    "--suppress-commands",
    is_flag=True,
    help="Alias for -q: do not display shell commands.",
)
@click.option(
    "--silent",
    is_flag=True,
    help="Alias for -qq: emit only the exit code.",
)
@click.option("-v", "--verbose", count=True, help="Increase diagnostics.")
@click.option(
    "--color",
    type=click.Choice(["auto", "always", "never"]),
    default="auto",
    help="Color output: auto, always, or never.",
)
@click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_config_callback,
    help="Print the discovered sink.yaml path and exit.",
)
@click.option(
    "--completions",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_completions_callback,
    help="Write static bash completions and print their path.",
)
@click.version_option(package_name="sink", prog_name="sink")
@click.pass_context
def cli(
    ctx: click.Context,
    quiet: int,
    suppress_commands: bool,
    silent: bool,
    verbose: int,
    color: str,
) -> None:
    """🐙 Tools to manage projects.

    Use `sink COMMAND -h` for help on specific commands.
    """
    effective_quiet = max(
        quiet, 1 if suppress_commands else 0, 2 if silent else 0
    )
    ui.configure(
        color=color,
        quiet=effective_quiet,
        verbose=verbose,
        suppress=suppress_commands or quiet >= 1,
    )
    if verbose:
        configure_logging(verbose)
    if ctx.obj is None:
        ctx.obj = Runtime.create(quiet=effective_quiet)
    else:
        ctx.obj.quiet = max(ctx.obj.quiet, effective_quiet)


def main() -> int:
    """Console-script entry point."""
    cli.main(prog_name="sink")
    return 0


# Importing registers commands on the group above.
from sink.cli import (  # noqa: E402, F401
    action,
    check,
    db,
    diff,
    file,
    info,
    misc,
    ssh,
)

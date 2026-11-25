"""The ``sink file`` and ``sink single`` commands."""

import os
from pathlib import Path

import click

from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.config.models import Action
from sink.rsync import Transfer
from sink.ui import ui

FILE_ACTIONS = (Action.PUT.value, Action.PULL.value)


def _resolve_target(rt, server, filename):
    """Resolve the optional SERVER/FILENAME tokens.

    ``sink file put dev`` means the whole project.  A single token that is
    not a configured server is a filename on the default server, so
    ``sink file put index.html`` keeps working.
    """
    cfg = rt.config
    if server is None:
        return cfg.server(None), filename
    if filename is not None:
        return cfg.server(server), filename
    if server in cfg.servers:
        return cfg.servers[server], None
    return cfg.server(None), server


@cli.command("file", context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("action", type=click.Choice(FILE_ACTIONS))
@click.argument("server", required=False)
@click.argument("filename", type=click.Path(), required=False)
@click.option("--real", "-r", is_flag=True)
@click.option("--silent", is_flag=True, help="Deprecated alias for -qq.")
@click.option("--extra-flags", help="extra flags to pass to rsync.")
@click.pass_obj
def files(rt, action, filename, server, real, silent, extra_flags):
    """Send files to and fro.

    Push or pull a single file or directory from a remote server.

    \b
    ACTION: pull or put
    SERVER: server name; if omitted the default server is used.
    FILENAME: file/dir to transfer; if omitted the whole project is used.
    With one token, a configured server name selects that server,
    otherwise the token is treated as a filename."""
    if silent:
        rt.quiet = max(rt.quiet, 2)
        ui.quiet = max(ui.quiet, 2)

    cfg = rt.config
    target, filename = _resolve_target(rt, server, filename)
    if filename and action == Action.PUT.value and not os.path.exists(filename):
        ui.error(f"Path does not exist: {filename}")

    f = Path(os.path.abspath(filename)) if filename else Path(cfg.project.root)

    xfer = Transfer(
        cfg.project,
        target,
        real=real,
        silent=silent,
    )
    extra_flags = extra_flags if extra_flags else ""

    if action == Action.PULL.value:
        xfer.pull(f, extra_flags)
    elif action == Action.PUT.value:
        xfer.put(f, extra_flags)


@cli.command("single", context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("filename", type=click.Path(), required=True)
@click.option("--real", "-r", is_flag=True)
@click.option("--silent", is_flag=True, help="Deprecated alias for -qq.")
@click.pass_obj
def automatic(rt, filename, real, silent):
    """Send a single file to any server marked as automatic.

    Send a single file to any server that has been designated as
    automatic.  This is primarily designed for scripting from a text
    editor."""
    if silent:
        rt.quiet = max(rt.quiet, 2)
        ui.quiet = max(ui.quiet, 2)
    cfg = rt.config
    f = Path(os.path.abspath(filename))
    for target in cfg.servers.values():
        if target.automatic:
            Transfer(cfg.project, target, real=real).single(f)

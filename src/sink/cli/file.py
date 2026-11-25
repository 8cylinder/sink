import os
from pathlib import Path

import click

from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.config.models import Action
from sink.rsync import Transfer
from sink.ui import ui


@cli.command("file", context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("action", type=click.Choice([str(i.value) for i in Action]))
@click.argument("server")
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
    SERVER: server name, if not specified sink will use the default server.
    FILENAME: file/dir to be transfered."""
    if silent:
        rt.quiet = max(rt.quiet, 2)
        ui.quiet = max(ui.quiet, 2)

    if filename and action == Action.PUT.value and not os.path.exists(filename):
        ui.error(f"Path does not exist: {filename}")

    cfg = rt.config
    f = Path(os.path.abspath(filename)) if filename else Path(cfg.project.root)

    xfer = Transfer(
        cfg.project,
        cfg.server(server),
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

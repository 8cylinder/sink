"""The ``sink ssh`` command."""

import click

from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.runtime import Runtime
from sink.ssh import SSH


@cli.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("server")
@click.argument("user", required=False)
@click.option(
    "--real", "-r", is_flag=True, help="Open an interactive ssh session."
)
@click.pass_obj
def ssh(rt: Runtime, server: str, user: str | None, real: bool) -> None:
    """SSH into a server."""
    target = rt.config.server(server)
    SSH(target, user=user, dry_run=not real).visit_ssh()

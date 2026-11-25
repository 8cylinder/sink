"""The ``sink action`` command."""

import click

from sink.actions import Actions
from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.runtime import Runtime


@cli.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("server")
@click.argument("action_name", required=False)
@click.option("--real", "-r", is_flag=True)
@click.pass_obj
def action(
    rt: Runtime, server: str, action_name: str | None, real: bool
) -> None:
    """Run a pre defined command on the server.

    If a section named 'actions' is in sink.yaml, run the requested
    action or list the available actions for that server.

    For example, add the following to one of the servers.  It will
    list all files ending in .cache on the requested server.

    \b
    actions:
      find-cache: find -iname '*.cache'

    Instead of using one of the servers, you can use the special name
    'local' for a server.  This will use the commands in the project
    section.

    If no action is specified, all actions available to that server
    will be listed.
    """
    cfg = rt.config
    if server == "local":
        actions = Actions(cfg.project, None, real)
    else:
        actions = Actions(cfg.project, cfg.server(server), real)
    if action_name:
        actions.run(action_name)
    else:
        actions.list_actions()

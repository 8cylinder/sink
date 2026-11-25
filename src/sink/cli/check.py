"""The ``sink check`` command."""

import click

from sink.check import TestConfig
from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.runtime import Runtime


@cli.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("server-names", nargs=-1)
@click.option("--required", "-R", is_flag=True)
@click.option(
    "--insecure", is_flag=True, help="Do not verify TLS certificates."
)
@click.pass_obj
def check(
    rt: Runtime,
    required: bool,
    server_names: tuple[str, ...],
    insecure: bool,
) -> None:
    """Test server settings in config."""
    if server_names:
        server_names = tuple(name.lower() for name in server_names)
    tc = TestConfig(rt.config, insecure=insecure)
    if required:
        tc.test_requirements()
    else:
        tc.test_unknown_keys()
        tc.test_project()
        tc.test_servers(server_names)

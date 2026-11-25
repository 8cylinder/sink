"""The ``sink check`` command."""

import click

from sink.check import TestConfig
from sink.cli import CONTEXT_SETTINGS, AppCommand, cli


@cli.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("server-names", nargs=-1)
@click.option("--required", "-R", is_flag=True)
@click.option("--real", "-r", is_flag=True, help="Run the checks.")
@click.option(
    "--insecure", is_flag=True, help="Do not verify TLS certificates."
)
@click.pass_obj
def check(rt, required, server_names, real, insecure):
    """Test server settings in config."""
    if server_names:
        server_names = [name.lower() for name in server_names]
    tc = TestConfig(rt.config, real=real, insecure=insecure)
    if required:
        tc.test_requirements()
    else:
        tc.test_servers(server_names)

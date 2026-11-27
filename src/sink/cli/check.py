"""The ``sink check`` command."""

import click

from sink.check import TestConfig
from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.runtime import Runtime, config_trust
from sink.ui import ui


@cli.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("server-names", nargs=-1)
@click.option("--required", "-R", is_flag=True)
@click.option(
    "--insecure", is_flag=True, help="Do not verify TLS certificates."
)
@click.option(
    "--trust-config",
    is_flag=True,
    help="Run probes even if the config is untrusted.",
)
@click.pass_obj
def check(
    rt: Runtime,
    required: bool,
    server_names: tuple[str, ...],
    insecure: bool,
    trust_config: bool,
) -> None:
    """Test server settings in config."""
    if server_names:
        server_names = tuple(name.lower() for name in server_names)
    cfg = rt.config
    trusted, reason = config_trust(cfg, rt.cwd)
    ui.echo(f"Config: {cfg.path}")
    if not trusted and not trust_config:
        ui.error(
            f"Refusing to probe an untrusted config ({reason}): {cfg.path}. "
            "Review it, then pass --trust-config."
        )
    tc = TestConfig(cfg, insecure=insecure)
    if required:
        tc.test_requirements()
    else:
        tc.test_unknown_keys()
        tc.test_project()
        tc.test_servers(server_names)

"""The ``sink check`` command."""

import json
from dataclasses import asdict

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
@click.option(
    "--strict/--allow-failures",
    default=True,
    help="Exit non-zero on probe failure (default), or allow failures.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit probe results as JSON.",
)
@click.pass_obj
def check(
    rt: Runtime,
    required: bool,
    server_names: tuple[str, ...],
    insecure: bool,
    trust_config: bool,
    strict: bool,
    json_output: bool,
) -> None:
    """Test server settings in config."""
    if server_names:
        server_names = tuple(name.lower() for name in server_names)
    if required and json_output:
        raise click.UsageError("--json cannot be combined with --required.")
    cfg = rt.config
    trusted, reason = config_trust(cfg, rt.cwd)
    if not trusted and not trust_config:
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "config": str(cfg.path),
                        "ok": False,
                        "error": f"untrusted config ({reason})",
                    }
                )
            )
            raise SystemExit(1)
        ui.error(
            f"Refusing to probe an untrusted config ({reason}): {cfg.path}. "
            "Review it, then pass --trust-config."
        )
    if not json_output:
        ui.echo(f"Config: {cfg.path}")
    tc = TestConfig(cfg, insecure=insecure, json_output=json_output)
    previous_quiet = ui.quiet
    if json_output:
        ui.quiet = max(ui.quiet, 2)
    try:
        if required:
            tc.test_requirements()
        else:
            tc.test_unknown_keys()
            tc.test_project()
            tc.test_servers(server_names)
    finally:
        ui.quiet = previous_quiet
    if json_output:
        click.echo(
            json.dumps(
                {
                    "config": str(cfg.path),
                    "ok": not tc.failed,
                    "probes": [asdict(result) for result in tc.results],
                },
                indent=2,
            )
        )
    if tc.failed and strict:
        raise SystemExit(1)

import datetime
import json
import shlex
from collections.abc import Mapping

import click

from sink.applications import Applications
from sink.cli import CONTEXT_SETTINGS, AppCommand, AppGroup, cli
from sink.config.models import Config
from sink.init import Init
from sink.ui import ui

SENSITIVE = ("password", "passwd", "secret", "token")


def _config_secrets(config: Config) -> tuple[str, ...]:
    secrets: set[str] = set()
    for server in config.servers.values():
        for ssh in server.ssh:
            if ssh.password:
                secrets.add(ssh.password)
        for database in server.databases:
            if database.password:
                secrets.add(database.password)
        for url in server.urls:
            if url.password:
                secrets.add(url.password)
            if url.htpassword:
                secrets.add(url.htpassword)
    return tuple(secrets)


def _redact_value(value, show_secrets: bool):
    if show_secrets:
        return value
    if isinstance(value, Mapping):
        return {
            key: (
                "********"
                if isinstance(key, str)
                and any(part in key.lower() for part in SENSITIVE)
                and item
                else _redact_value(item, show_secrets)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item, show_secrets) for item in value]
    return value


@cli.group(context_settings=CONTEXT_SETTINGS, cls=AppGroup)
def misc():
    """[Group] Misc stuff."""


@misc.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("keys", nargs=-1, required=True)
@click.option(
    "--show-secrets",
    is_flag=True,
    help="Print secret values instead of redacting them.",
)
@click.pass_obj
def api(rt, keys, show_secrets):
    """Retrieve information from the config file.

    The data is always output as JSON.

    Some examples:

    \b
    To get the project name:
      sink misc api project name

    \b
    To get the 2nd excluded filename:
      sink misc api project exclude 1

    \b
    To get the dev servers user name:
      sink misc api servers dev user
    """
    data = rt.config.raw
    sensitive_path = any(
        part in str(key).lower() for key in keys for part in SENSITIVE
    )
    for key in keys:
        try:
            index = int(key)
        except ValueError:
            index = key
        try:
            data = data[index]
        except KeyError:
            ui.error(f'key "{key}" does not exist in config.')
        except IndexError as error:
            ui.error(str(error))
    redacted = _redact_value(data, show_secrets)
    if sensitive_path and not show_secrets and redacted:
        redacted = "********"
    click.echo(json.dumps(redacted))


@misc.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.pass_obj
def pack(rt):
    """Display a command to gzip uncommitted files."""
    now = datetime.datetime.now().strftime("%y-%m-%d-%H-%M-%S")
    tarname = f"changed-{rt.config.project.name}-{now}.tar.gz"
    command = f"git ls-files -mz | xargs -0 tar -czvf {shlex.quote(tarname)}"
    ui.echo(f"Run: {command}")


@misc.command("init", context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("servers", nargs=-1)
def init_config(servers):
    """Create a blank config.

    The servers arg will create an entry for each server name given.

    \b
    To write the config to a file use:
    `sink misc init > sink.yaml`
    `sink misc init dev stag prod > sink.yaml`
    """
    init_file = Init()
    init_file.servers(servers)
    click.echo(init_file.create())


@misc.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("application", required=False)
@click.option(
    "--show-secrets",
    is_flag=True,
    help="Print secret values instead of redacting them.",
)
@click.pass_obj
def settings(rt, application, show_secrets):
    """Output settings values for the requested application.

    For the requested application, output settings in a format thats
    easy to copy & paste.
    """
    cfg = rt.config
    app = Applications(cfg)
    if not app.name(application):
        ui.echo(f"Unknown application: {application}")
        ui.echo(f"Known are: {app.known()}")
    else:
        output = app.app_settings()
        if not show_secrets:
            output = ui.redact(output, _config_secrets(cfg))
        ui.output(output + ("" if output.endswith("\n") else "\n"))

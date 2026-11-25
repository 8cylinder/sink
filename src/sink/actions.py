import shlex

import click

from sink.config import config
from sink.errors import CommandError
from sink.shell import Argv, run
from sink.ssh import SSH
from sink.ui import ui


class Actions:
    def __init__(self, servername, real):
        self.servername = servername
        if servername == "local":
            self.s = config.project()
        else:
            self.s = config.server(servername)
        self.dry_run = not real

    def actions(self):
        actions = getattr(self.s, "actions", None)
        if isinstance(actions, dict):
            return actions
        raw = getattr(actions, "raw", None)
        return raw if isinstance(raw, dict) else {}

    def list_actions(self):
        for name, cmd in self.actions().items():
            name = click.style(name, bold=True)
            cmd = click.style(f'"{cmd}"', dim=True)
            click.echo(f"{name} - {cmd}")

    def run(self, command_name):
        commands = self.actions()
        try:
            cmd = commands[command_name]
        except KeyError:
            ui.warn(f'"{command_name}" command not found')
            self.list_actions()
            raise CommandError(f'"{command_name}" command not found') from None

        if self.servername == "local":
            argv = tuple(shlex.split(cmd))
            if not argv:
                raise CommandError(f'"{command_name}" is empty')
            result = run(Argv(argv), real=not self.dry_run, capture=True)
            if result.stdout:
                print(result.stdout)
            if result.returncode:
                raise CommandError(
                    result.stderr.strip() or f'"{command_name}" failed'
                )
        else:
            ssh = SSH(server=self.s.servername, dry_run=self.dry_run)
            result = ssh.run(cmd)
            print(result)

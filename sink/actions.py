
from pprint import pprint as pp
import click

from sink.config import config
from sink.config import Action
from sink.ui import Color
from sink.ui import ui
from sink.ssh import SSH


class Actions:
    def __init__(self, servername, real):
        self.s = config.server(servername)
        self.p = config.project()
        self.dry_run = not real

    def list_actions(self):
        for name, cmd in self.s.actions:
            name = click.style(name, bold=True)
            cmd = click.style(f'"{cmd}"', dim=True)
            click.echo(f'{name} - {cmd}')

    def run(self, command_name):
        commands = dict(self.s.actions)
        try:
            cmd = commands[command_name]
        except KeyError:
            ui.warn(f'"{command_name}" command not found')
            self.list_actions()
            exit(1)

        ssh = SSH()
        result = ssh.run(cmd, server=self.s.servername, dry_run=self.dry_run)
        print(result)

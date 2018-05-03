import subprocess
import click
from pprint import pprint as pp

from sink.config import Config
from sink.ui import ui


class SSH:
    def __init__(self):
        self.config = Config()

    def ssh(self, server=False, dry_run=False):
        s = self.config.server(server)

        identity = self.get_key(s)

        cmd = f'''ssh {identity} {s.ssh.username}@{s.ssh.server}'''
        cmd = ' '.join(cmd.split())

        self.run_cmd(cmd, dry_run)

    def scp(self, localfile, server=False, dry_run=False):
        s = self.config.server(server)

        identity = self.get_key(s)

        cmd = f'''scp  -o 'ConnectTimeout 10' {identity}
            {localfile} {s.ssh_user}@{s.ssh_server}'''
        cmd = ' '.join(cmd.split())

        self.run_cmd(cmd, dry_run)

    def get_key(self, server):
        try:
            identity = f'-i "{server.ssh.key}"'
            if server.ssh.key:
                click.echo(f'Using identity: "{server.ssh.key}"')
            else:
                identity = ''
        except AttributeError:
            identity = ''

        return identity

    def run_cmd(self, cmd, dry_run):
        ui.display_cmd(cmd)
        if not dry_run:
            subprocess.run(cmd, shell=True)


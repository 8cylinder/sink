import errno
import os
import subprocess
import click
from pprint import pprint as pp

from sink.config import config
from sink.ui import ui


class SSH:
    def __init__(self, server=False, user=None, dry_run=False):
        self.dry_run = dry_run
        self.config = config
        self.server = self.config.server(server)
        if user:
            for ssh in self.server.ssh:
                if ssh.name == user:
                    self.ssh = ssh
                    break
            else:
                ui.error(f'Invalid ssh user: {user}')
        else:
            self.ssh = self.server.ssh[0]

    def visit_ssh(self):
        identity = self.get_key()
        port = ''
        if self.ssh.port:
            port = f'-p {self.ssh.port}'

        cd_cmd = ''
        if self.server.root:
            cd_cmd = f'"cd {self.server.root}; bash"'

        cmd = f'''ssh -t {port} {identity} {self.ssh.username}@{self.ssh.server} {cd_cmd}'''
        cmd = ' '.join(cmd.split())

        self.run_cmd(cmd, self.dry_run)

    def scp_put(self, localfile):
        # s = self.config.server(server)

        identity = self.get_key()

        port = ''
        if self.ssh.port:
            port = f'-P {self.ssh.port}'

        cmd = f'''scp {port} -o 'ConnectTimeout 10' {identity}
            {localfile} {self.ssh.username}@{self.ssh.server}'''
        cmd = ' '.join(cmd.split())

        self.run_cmd(cmd, self.dry_run)

    def scp_pull(self, remotefile, dest):
        identity = self.get_key()
        port = ''
        if self.ssh.port:
            port = f'-P {self.ssh.port}'

        cmd = f'''scp {port} -o 'ConnectTimeout 10' {identity}
            {self.ssh.username}@{self.ssh.server}:{remotefile} {dest}'''
        cmd = ' '.join(cmd.split())
        self.run_cmd(cmd, self.dry_run)

    def run(self, remote_cmd):
        identity = self.get_key()

        port = ''
        if self.ssh.port:
            port = f'-p {self.ssh.port}'

        cmd = f'''ssh {port} {identity} {self.ssh.username}@{self.ssh.server} {remote_cmd}'''
        cmd = ' '.join(cmd.split())

        result = self.run_cmd_result(cmd, self.dry_run)
        return result

    def get_key(self):
        if not self.ssh.key:
            identity = ''
        elif os.path.exists(self.ssh.key):
            identity = f'-i "{self.ssh.key}"'
            # click.echo(f'Using identity: "{server.ssh.key}"')
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.ssh.key)
            # ui.error(f'ssh key does no exist: {server.ssh.key}')
        return identity

    def run_cmd(self, cmd, dry_run):
        ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
        if not dry_run:
            subprocess.run(cmd, shell=True)

    def run_cmd_result(self, cmd, dry_run):
        ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
        if dry_run:
            return ''
        else:
            try:
                result = subprocess.check_output(
                    cmd, shell=True,
                    # stderr=subprocess.PIPE)
                    stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                # subprocess.STDOUT returns error msg but
                # subprocess.PIPE does not.
                ui.error('On remote server: {}'.format(
                    e.output.decode('utf-8')))
            decoded = result.decode('utf-8')
            return decoded

import errno
import os
import subprocess
import click
from pprint import pprint as pp

from sink.config import config
from sink.ui import ui


class SSH:
    def __init__(self):
        self.config = config
        pass

    def ssh(self, server=False, dry_run=False):
        s = self.config.server(server)

        identity = self.get_key(s)
        port = ''
        if s.ssh.port:
            port = f'-p {s.ssh.port}'

        cd_cmd = ''
        if s.root:
            cd_cmd = f'"cd {s.root}; bash"'

        cmd = f'''ssh -t {port} {identity} {s.ssh.username}@{s.ssh.server} {cd_cmd}'''
        cmd = ' '.join(cmd.split())

        self.run_cmd(cmd, dry_run)

    def scp_put(self, localfile, server=False, dry_run=False):
        s = self.config.server(server)

        identity = self.get_key(s)

        port = ''
        if s.ssh.port:
            port = f'-P {s.ssh.port}'

        cmd = f'''scp {port} -o 'ConnectTimeout 10' {identity}
            {localfile} {s.ssh_user}@{s.ssh_server}'''
        cmd = ' '.join(cmd.split())

        self.run_cmd(cmd, dry_run)

    def scp_pull(self, remotefile, dest, server, dry_run=False):
        s = self.config.server(server)
        identity = self.get_key(s)
        port = ''
        if s.ssh.port:
            port = f'-P {s.ssh.port}'

        cmd = f'''scp {port} -o 'ConnectTimeout 10' {identity}
            {s.ssh.username}@{s.ssh.server}:{remotefile} {dest}'''
        cmd = ' '.join(cmd.split())
        self.run_cmd(cmd, dry_run)

    def run(self, remote_cmd, server=False, dry_run=False):
        s = self.config.server(server)

        identity = self.get_key(s)

        port = ''
        if s.ssh.port:
            port = f'-p {s.ssh.port}'

        cmd = f'''ssh {port} {identity} {s.ssh.username}@{s.ssh.server} {remote_cmd}'''
        cmd = ' '.join(cmd.split())

        result = self.run_cmd_result(cmd, dry_run)
        return result

    def get_key(self, server):
        if not server.ssh.key:
            identity = ''
        elif os.path.exists(server.ssh.key):
            identity = f'-i "{server.ssh.key}"'
            # click.echo(f'Using identity: "{server.ssh.key}"')
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), server.ssh.key)
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

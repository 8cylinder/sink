import errno
import os
import shlex

from sink.config import config
from sink.errors import CommandError
from sink.shell import Argv, remote_command, run, scp_argv
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
                ui.error(f"Invalid ssh user: {user}")
        else:
            self.ssh = self.server.ssh[0]

    @property
    def real(self):
        return not self.dry_run

    def visit_ssh(self):
        fragment = ""
        if self.server.root:
            fragment = f"cd {shlex.quote(str(self.server.root))}; bash"
        command = remote_command(self.ssh, fragment, tty=True)
        run(command, real=self.real, capture=False)

    def scp_put(self, localfile):
        remote = f"{self.ssh.username}@{self.ssh.server}"
        argv = scp_argv(self.ssh, str(localfile), remote)
        run(Argv(argv), real=self.real, capture=False)

    def scp_pull(self, remotefile, dest):
        remote = f"{self.ssh.username}@{self.ssh.server}:{remotefile}"
        argv = scp_argv(self.ssh, remote, str(dest))
        run(Argv(argv), real=self.real, capture=False)

    def run(self, remote_cmd):
        command = remote_command(
            self.ssh,
            remote_cmd,
            batch=True,
            timeout=25,
        )
        result = run(command, real=self.real, capture=True)
        if self.real and result.returncode:
            raise CommandError(result.stderr.strip() or "remote command failed")
        return result.stdout

    def get_key(self):
        if not self.ssh.key:
            identity = ""
        elif os.path.exists(self.ssh.key):
            identity = f'-i "{self.ssh.key}"'
        else:
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), self.ssh.key
            )
        return identity

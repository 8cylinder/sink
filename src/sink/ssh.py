"""Run ssh, scp, and remote commands."""

import errno
import os
import shlex
from collections.abc import Iterable
from pathlib import Path

from sink.config.models import Server
from sink.errors import CommandError
from sink.shell import Argv, remote_command, run, scp_argv
from sink.ui import ui


class SSH:
    """Run ssh, scp, and remote commands for one server."""

    def __init__(
        self, server: Server, user: str | None = None, dry_run: bool = False
    ) -> None:
        self.dry_run = dry_run
        self.server = server
        if user:
            for ssh in server.ssh:
                if ssh.name == user:
                    self.ssh = ssh
                    break
            else:
                ui.error(f"Invalid ssh user: {user}")
        else:
            if not server.ssh:
                ui.error(f"Server has no ssh settings ({server.name}).")
            self.ssh = server.ssh[0]

    @property
    def real(self) -> bool:
        """Whether this session executes commands."""
        return not self.dry_run

    def visit_ssh(self) -> None:
        """Open or print an interactive ssh session."""
        fragment = ""
        if self.server.root:
            fragment = f"cd {shlex.quote(str(self.server.root))}; bash"
        command = remote_command(self.ssh, fragment, tty=True)
        run(command, real=self.real, capture=False)

    def scp_put(self, localfile: str | Path) -> None:
        """Upload one file with scp."""
        remote = f"{self.ssh.username}@{self.ssh.server}"
        argv = scp_argv(self.ssh, str(localfile), remote)
        run(
            Argv(argv, identity_error=self.ssh.key_error),
            real=self.real,
            capture=False,
        )

    def scp_pull(self, remotefile: str | Path, dest: str | Path) -> None:
        """Download one file with scp."""
        remote = f"{self.ssh.username}@{self.ssh.server}:{remotefile}"
        argv = scp_argv(self.ssh, remote, str(dest))
        run(
            Argv(argv, identity_error=self.ssh.key_error),
            real=self.real,
            capture=False,
        )

    def run(self, remote_cmd: str, secrets: Iterable[str] = ()) -> str:
        """Run a remote shell fragment and return its output."""
        command = remote_command(
            self.ssh,
            remote_cmd,
            batch=True,
            timeout=25,
        )
        result = run(command, real=self.real, capture=True, secrets=secrets)
        if self.real and result.returncode:
            raise CommandError(
                ui.redact(
                    result.stderr.strip() or "remote command failed",
                    secrets,
                )
            )
        return result.stdout

    def get_key(self) -> str:
        """Return the identity argument for the configured key."""
        if not self.ssh.key:
            identity = ""
        elif Path(self.ssh.key).exists():
            identity = f'-i "{self.ssh.key}"'
        else:
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), self.ssh.key
            )
        return identity

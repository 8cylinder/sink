"""Run configured project and server actions."""

import shlex

from sink.config.models import Project, Server
from sink.errors import CommandError
from sink.shell import Argv, run
from sink.ssh import SSH
from sink.ui import ui


class Actions:
    """Project- or server-scoped configured actions."""

    def __init__(self, project: Project, server: Server | None, real: bool):
        self.project = project
        self.server = server
        self.dry_run = not real

    @property
    def servername(self) -> str:
        """Return ``local`` or the target server name."""
        return self.server.name if self.server is not None else "local"

    def actions(self):
        """Return the action mapping for this scope."""
        source = self.project if self.server is None else self.server
        return source.actions

    def list_actions(self):
        """Print the available actions."""
        for name, cmd in self.actions().items():
            ui.output(f'{name} - "{cmd}"\n')

    def run(self, command_name):
        """Run one configured action or report it missing."""
        commands = self.actions()
        try:
            cmd = commands[command_name]
        except KeyError:
            ui.warn(f'"{command_name}" command not found')
            self.list_actions()
            raise CommandError(f'"{command_name}" command not found') from None

        if self.server is None:
            argv = tuple(shlex.split(cmd))
            if not argv:
                raise CommandError(f'"{command_name}" is empty')
            result = run(Argv(argv), real=not self.dry_run, capture=True)
            if result.stdout:
                ui.output(result.stdout)
            if result.returncode:
                raise CommandError(
                    result.stderr.strip() or f'"{command_name}" failed'
                )
        else:
            ssh = SSH(server=self.server, dry_run=self.dry_run)
            result = ssh.run(cmd)
            ui.output(result)

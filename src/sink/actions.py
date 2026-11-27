"""Run configured project and server actions."""

import shlex
from collections.abc import Iterable, Mapping

from sink.config.models import Project, Server
from sink.errors import CommandError
from sink.shell import Argv, run
from sink.ssh import SSH
from sink.ui import ui


class Actions:
    """Project- or server-scoped configured actions."""

    def __init__(
        self,
        project: Project,
        server: Server | None,
        real: bool,
        secrets: Iterable[str] = (),
    ) -> None:
        self.project = project
        self.server = server
        self.dry_run = not real
        self.secrets = tuple(secrets)

    @property
    def servername(self) -> str:
        """Return ``local`` or the target server name."""
        return self.server.name if self.server is not None else "local"

    def actions(self) -> Mapping[str, str]:
        """Return the action mapping for this scope."""
        source = self.project if self.server is None else self.server
        return source.actions

    def list_actions(self, show_commands: bool = False) -> None:
        """Print the available actions, hiding their commands by default."""
        actions = self.actions()
        if show_commands and actions:
            ui.warn("Action commands may contain secrets.")
        for name, cmd in actions.items():
            if show_commands:
                ui.output(f'{name} - "{cmd}"\n')
            else:
                ui.output(f"{name}\n")
        if not show_commands and actions:
            ui.notice(
                "Action commands are hidden; use --show-commands to display "
                "them (they may contain secrets)."
            )

    def run(self, command_name: str) -> None:
        """Run one configured action or report it missing."""
        commands = self.actions()
        try:
            cmd = commands[command_name]
        except KeyError:
            ui.warn(f'"{command_name}" command not found')
            self.list_actions()
            raise CommandError(f'"{command_name}" command not found') from None

        ui.warn(
            f'configured action "{command_name}" will run: '
            f"{ui.redact(cmd, self.secrets)}"
        )

        if self.server is None:
            argv = tuple(shlex.split(cmd))
            if not argv:
                raise CommandError(f'"{command_name}" is empty')
            result = run(
                Argv(argv),
                real=not self.dry_run,
                capture=True,
                secrets=self.secrets,
            )
            if result.stdout:
                ui.output(ui.redact(result.stdout, self.secrets))
            if result.returncode:
                raise CommandError(
                    ui.redact(
                        result.stderr.strip() or f'"{command_name}" failed',
                        self.secrets,
                    )
                )
        else:
            ssh = SSH(server=self.server, dry_run=self.dry_run)
            result = ssh.run(cmd, secrets=self.secrets)
            ui.output(ui.redact(result, self.secrets))

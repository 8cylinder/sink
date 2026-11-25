"""Out-of-band database credentials for remote commands.

The password never appears in a rendered command, argv, or log.  A remote
credentials file is created with mode 0600 by piping it over ssh stdin, then
the command points at the file with ``--defaults-extra-file``.  An EXIT trap
in the command's remote shell removes it even when the command fails or the
connection drops, and a separate cleanup command remains as a fallback.
"""

from __future__ import annotations

import shlex
import tempfile
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from sink.errors import CommandError
from sink.shell import RemoteCommand, remote_command, run

DEFAULT_TIMEOUT = 25


def _option_value(value: object) -> str:
    """Quote one value for a MySQL option file.

    MySQL treats ``#`` as a comment start even in the middle of a line, so
    every value is double-quoted.  Backslashes and double quotes are escaped
    so the option-file parser receives the original value.
    """
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True, slots=True)
class RemoteCredentials:
    """Out-of-band remote MySQL credentials."""

    ssh: object
    password: str
    user: str | None = None
    host: str | None = None
    port: int | None = None
    path: str = field(
        default_factory=lambda: str(
            Path(tempfile.gettempdir()) / f"sink-mysql-{uuid.uuid4().hex}.cnf"
        )
    )

    @property
    def content(self) -> str:
        """Return the credentials file body."""
        lines = ["[client]"]
        if self.user:
            lines.append(f"user={_option_value(self.user)}")
        if self.password:
            lines.append(f"password={_option_value(self.password)}")
        if self.host:
            lines.append(f"host={_option_value(self.host)}")
        if self.port:
            lines.append(f"port={self.port}")
        return "\n".join(lines) + "\n"

    @property
    def option(self) -> str:
        """Return the mysql defaults-file option."""
        return f"--defaults-extra-file={self.path}"

    def stage_command(self) -> RemoteCommand:
        """Return the command that writes the file over ssh."""
        return remote_command(
            self.ssh,
            f"umask 077; cat > {shlex.quote(self.path)}",
            batch=True,
            timeout=DEFAULT_TIMEOUT,
        )

    def cleanup_command(self) -> RemoteCommand:
        """Return the command that removes the remote file."""
        return remote_command(
            self.ssh,
            f"rm -f {shlex.quote(self.path)}",
            batch=True,
            timeout=DEFAULT_TIMEOUT,
        )

    def trap_command(self, fragment: str) -> str:
        """Wrap a remote fragment with an EXIT trap for the credentials file."""
        cleanup = f"rm -f {shlex.quote(self.path)}"
        return f"trap {shlex.quote(cleanup)} EXIT; {fragment}"


@contextmanager
def remote_mysql_credentials(
    ssh: object,
    *,
    password: str,
    user: str | None = None,
    host: str | None = None,
    port: int | None = None,
    real: bool,
) -> Generator[RemoteCredentials]:
    """Stage credentials remotely and always clean them up."""
    credentials = RemoteCredentials(
        ssh=ssh,
        password=password,
        user=user,
        host=host,
        port=port,
    )
    # The secrets travel on stdin, never in argv.  In dry-run mode this only
    # prints the staging command; real mode writes the 0600 file remotely.
    staged = run(
        credentials.stage_command(),
        real=real,
        capture=True,
        input=credentials.content,
    )
    if real and not staged.ok:
        raise CommandError(
            "Could not write remote database credentials"
            + (f": {staged.stderr.strip()}" if staged.stderr.strip() else "")
        )
    try:
        yield credentials
    finally:
        run(credentials.cleanup_command(), real=real, capture=True)

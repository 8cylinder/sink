"""Out-of-band database credentials for local and remote commands.

The password never appears in a rendered command, argv, or log.  A remote
credentials file is created with mode 0600 by piping it over ssh stdin, then
the command points at the file with ``--defaults-file``.  An EXIT trap
in the command's remote shell removes it even when the command fails or the
connection drops, and a separate cleanup command remains as a fallback.

Local clients use a 0600 option file inside a private temporary directory.
The directory and file are removed when the command finishes.
"""

from __future__ import annotations

import os
import shlex
import shutil
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
    if any(character in text for character in ("\x00", "\n", "\r")):
        raise CommandError(
            "MySQL option values must not contain NUL, CR, or LF"
        )
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _credentials_content(
    *,
    user: str | None,
    password: str,
    host: str | None,
    port: int | None,
    ssl_mode: str | None = None,
    ssl_ca: str | None = None,
    ssl_cert: str | None = None,
    ssl_key: str | None = None,
    skip_secure_auth: str | bool | None = None,
) -> str:
    """Build a MySQL option-file body."""
    lines = ["[client]"]
    if user:
        lines.append(f"user={_option_value(user)}")
    if password:
        lines.append(f"password={_option_value(password)}")
    if host:
        lines.append(f"host={_option_value(host)}")
    if port:
        lines.append(f"port={port}")
    if ssl_mode:
        lines.append(f"ssl-mode={ssl_mode}")
    if ssl_ca:
        lines.append(f"ssl-ca={_option_value(ssl_ca)}")
    if ssl_cert:
        lines.append(f"ssl-cert={_option_value(ssl_cert)}")
    if ssl_key:
        lines.append(f"ssl-key={_option_value(ssl_key)}")
    if skip_secure_auth:
        lines.append("skip-secure-auth")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class RemoteCredentials:
    """Out-of-band remote MySQL credentials."""

    ssh: object
    password: str
    user: str | None = None
    host: str | None = None
    port: int | None = None
    ssl_mode: str | None = None
    ssl_ca: str | None = None
    ssl_cert: str | None = None
    ssl_key: str | None = None
    skip_secure_auth: str | bool | None = None
    path: str = field(
        default_factory=lambda: str(
            Path(tempfile.gettempdir())
            / f"sink-mysql-{uuid.uuid4().hex}"
            / "client.cnf"
        )
    )

    @property
    def content(self) -> str:
        """Return the credentials file body."""
        return _credentials_content(
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            ssl_mode=self.ssl_mode,
            ssl_ca=self.ssl_ca,
            ssl_cert=self.ssl_cert,
            ssl_key=self.ssl_key,
            skip_secure_auth=self.skip_secure_auth,
        )

    @property
    def directory(self) -> Path:
        """Return the private remote credential directory."""
        return Path(self.path).parent

    @property
    def option(self) -> str:
        """Return the mysql defaults-file option."""
        return f"--defaults-file={self.path}"

    def stage_command(self) -> RemoteCommand:
        """Return the command that creates the private credential file."""
        directory = shlex.quote(str(self.directory))
        path = shlex.quote(self.path)
        return remote_command(
            self.ssh,
            f"umask 077; mkdir -m 700 {directory} && set -C && cat > {path}",
            batch=True,
            timeout=DEFAULT_TIMEOUT,
        )

    def cleanup_command(self) -> RemoteCommand:
        """Return the command that removes the remote directory."""
        return remote_command(
            self.ssh,
            f"rm -rf {shlex.quote(str(self.directory))}",
            batch=True,
            timeout=DEFAULT_TIMEOUT,
        )

    def trap_command(self, fragment: str) -> str:
        """Wrap a remote fragment with an EXIT trap for the directory."""
        cleanup = f"rm -rf {shlex.quote(str(self.directory))}"
        return f"trap {shlex.quote(cleanup)} EXIT; {fragment}"


@dataclass(frozen=True, slots=True)
class LocalCredentials:
    """A local 0600 MySQL option file in a private directory."""

    path: Path

    @property
    def option(self) -> str:
        """Return the mysql defaults-file option."""
        return f"--defaults-file={self.path}"


@contextmanager
def local_mysql_credentials(
    *,
    user: str | None = None,
    password: str = "",
    host: str | None = None,
    port: int | None = None,
    ssl_mode: str | None = None,
    ssl_ca: str | None = None,
    ssl_cert: str | None = None,
    ssl_key: str | None = None,
    skip_secure_auth: str | bool | None = None,
    real: bool,
) -> Generator[LocalCredentials]:
    """Create a local 0600 option file and remove it afterwards."""
    directory = Path(tempfile.mkdtemp(prefix="sink-mysql-local-"))
    path = directory / "client.cnf"
    try:
        directory.chmod(0o700)
        if real:
            fd = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(fd, "w") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(
                    _credentials_content(
                        user=user,
                        password=password,
                        host=host,
                        port=port,
                        ssl_mode=ssl_mode,
                        ssl_ca=ssl_ca,
                        ssl_cert=ssl_cert,
                        ssl_key=ssl_key,
                        skip_secure_auth=skip_secure_auth,
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
        yield LocalCredentials(path=path)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@contextmanager
def remote_mysql_credentials(
    ssh: object,
    *,
    password: str,
    user: str | None = None,
    host: str | None = None,
    port: int | None = None,
    ssl_mode: str | None = None,
    ssl_ca: str | None = None,
    ssl_cert: str | None = None,
    ssl_key: str | None = None,
    skip_secure_auth: str | bool | None = None,
    real: bool,
) -> Generator[RemoteCredentials]:
    """Stage credentials remotely and always clean them up."""
    credentials = RemoteCredentials(
        ssh=ssh,
        password=password,
        user=user,
        host=host,
        port=port,
        ssl_mode=ssl_mode,
        ssl_ca=ssl_ca,
        ssl_cert=ssl_cert,
        ssl_key=ssl_key,
        skip_secure_auth=skip_secure_auth,
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

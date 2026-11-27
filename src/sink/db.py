"""Pull and push MySQL databases safely."""

import datetime
import os
import re
import shlex
import shutil
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import click

from sink.config.models import DatabaseConfig, Project, Server
from sink.credentials import (
    LocalCredentials,
    RemoteCredentials,
    local_mysql_credentials,
    remote_mysql_credentials,
)
from sink.errors import CommandError
from sink.shell import Argv, Command, Pipeline, Result, remote_command, run
from sink.ui import ui


def _port(db: DatabaseConfig) -> int | None:
    """Return a database port as an integer, or ``None``."""
    if db.port is None:
        return None
    try:
        return int(db.port)
    except AttributeError, TypeError, ValueError:
        return None


def _client_options(
    db: DatabaseConfig,
    credentials: RemoteCredentials | LocalCredentials | None = None,
) -> list[str]:
    """Build mysql client arguments without a password flag."""
    if credentials is not None:
        return [credentials.option]
    options: list[str] = []
    if db.hostname:
        options.extend(["--host", db.hostname])
    if db.username:
        options.extend(["--user", db.username])
    port = _port(db)
    if port and port != 3306:
        options.extend(["--port", str(port)])
    ssl_mode = db.effective_ssl_mode
    if ssl_mode:
        options.extend(["--ssl-mode", ssl_mode])
    if db.ssl_ca:
        options.extend(["--ssl-ca", db.ssl_ca])
    if db.ssl_cert:
        options.extend(["--ssl-cert", db.ssl_cert])
    if db.ssl_key:
        options.extend(["--ssl-key", db.ssl_key])
    if db.skip_secure_auth:
        options.append("--skip-secure-auth")
    return options


def _dump_argv(
    db: DatabaseConfig,
    credentials: RemoteCredentials | LocalCredentials | None = None,
    *,
    mysqlpump: bool = False,
) -> list[str]:
    """Build a dump argv, optionally using mysqlpump's progress mode."""
    binary = "mysqlpump" if mysqlpump else "mysqldump"
    argv = [binary, *_client_options(db, credentials)]
    if mysqlpump:
        argv.extend(["--watch-progress", db.db or ""])
    else:
        argv.extend(
            [
                "--single-transaction",
                "--triggers",
                "--events",
                "--routines",
                "--no-tablespaces",
                db.db or "",
            ]
        )
    return argv


_TAG_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _filename_component(value: str) -> str:
    """Turn a project or server name into one safe filename component.

    Names come from the config, so path separators, ``..`` segments, and
    shell syntax must not reach a filename.  Unsafe runs become ``-`` and
    the result is always a single component.
    """
    slug = _FILENAME_UNSAFE.sub("-", value).strip("-")
    return slug or "x"


def _validate_tag(tag: str | None) -> None:
    """Reject a tag that could escape the pulls directory.

    A tag becomes part of a local filename.  Allowing path separators or
    ``..`` lets a value such as ``../../../escape`` write outside
    ``pulls_dir``, even though the tag never reaches a shell.
    """
    if tag is None:
        return
    if tag in {".", ".."} or _TAG_PATTERN.fullmatch(tag) is None:
        raise CommandError(
            f"Invalid tag {tag!r}: use only letters, digits, dot, dash, "
            "or underscore"
        )


def _unique_path(path: Path) -> Path:
    """Return a dump path that does not overwrite an existing file."""
    if not path.exists():
        return path
    suffix = "".join(path.suffixes)
    base = path.name[: -len(suffix)] if suffix else path.name
    for index in range(2, 1000):
        candidate = path.with_name(f"{base}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise CommandError(f"Could not find a free dump name for {path}")


def _validate_gzip(path: Path) -> None:
    """Reject a file that is not gzip before any remote command runs."""
    try:
        with path.open("rb") as stream:
            magic = stream.read(2)
    except OSError as error:
        raise CommandError(f"Cannot read {path}: {error}") from error
    if magic != b"\x1f\x8b":
        raise CommandError(f"{path} is not a gzip file")


def _mysql_argv(
    db: DatabaseConfig,
    credentials: RemoteCredentials | LocalCredentials | None = None,
) -> list[str]:
    """Build the mysql import argv."""
    return [
        "mysql",
        *_client_options(db, credentials),
        db.db or "",
    ]


class DB:
    """Pull and push databases for one project and server."""

    def __init__(
        self,
        project: Project,
        server: Server,
        real: bool = False,
        verbose: bool = False,
        filename_only: bool = False,
    ) -> None:
        self.verbose = bool(verbose)
        self.real = real
        self.project = project
        self.server = server
        self.filename_only = filename_only
        self.secrets: tuple[str, ...] = ()

    def _database(self) -> DatabaseConfig:
        """Return the first configured database or raise."""
        if not self.server.databases:
            raise CommandError(
                f"Server {self.server.name} has no database configured"
            )
        database = self.server.databases[0]
        self.secrets = (database.password or "",)
        return database

    def dump_remote(self, dest: str | Path) -> None:
        """Write a dump on the remote server."""
        dest = Path(dest)
        self._pull(dest, local=False)

    def _ensure_pulls_dir(self) -> Path:
        """Create the pulls directory 0700 or refuse an unsafe one."""
        pulls = self.project.pulls_dir
        if pulls is None:
            raise CommandError("project.pulls_dir is not configured")
        if not pulls.exists():
            pulls.mkdir(parents=True)
            pulls.chmod(0o700)
        if not pulls.is_dir():
            raise CommandError(f"pulls path is not a directory: {pulls}")
        mode = pulls.stat().st_mode & 0o777
        if mode & 0o077:
            raise CommandError(
                f"pulls directory {pulls} is accessible by group or other "
                f"(mode {mode:o}); run: chmod 700 {pulls}"
            )
        return pulls

    @staticmethod
    def _part_path(final: Path) -> Path:
        """Return the temporary path used while a dump is written."""
        return final.with_name(f"{final.name}.part")

    @staticmethod
    def _part_candidates(part: Path) -> tuple[Path, Path]:
        """Return the part path and a tool-added gzip variant."""
        return part, Path(f"{part}.gz")

    def _cleanup_part(self, part: Path) -> None:
        """Remove a partial dump and any tool-added gzip variant."""
        for candidate in self._part_candidates(part):
            with suppress(OSError):
                candidate.unlink()

    def _actual_part(self, part: Path) -> Path | None:
        """Return the file the dump tool actually wrote, if any."""
        for candidate in self._part_candidates(part):
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _final_path(final: Path, actual: Path) -> Path:
        """Preserve the tool's gzip suffix in the committed filename."""
        if actual.suffix == ".gz" and final.suffix != ".gz":
            return Path(f"{final}.gz")
        return final

    def _cleanup_stale_parts(self, pulls: Path) -> None:
        """Remove partial dumps older than one day."""
        cutoff = time.time() - 24 * 60 * 60
        for pattern in ("*.part", "*.part.gz"):
            for path in pulls.glob(pattern):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                except OSError:
                    continue

    def _run_part_pull(
        self,
        part: Path,
        final: Path,
        action: Callable[[Path, Path], None],
    ) -> None:
        """Run one part-file pull and always clean up on failure."""
        self._cleanup_part(part)
        try:
            action(part, final)
        except FileExistsError as error:
            self._cleanup_part(part)
            raise CommandError(
                f"Could not create partial dump {part}: {error}"
            ) from error
        except OSError as error:
            self._cleanup_part(part)
            raise CommandError(
                f"Could not start the dump pipeline: {error}"
            ) from error
        except BaseException:
            self._cleanup_part(part)
            raise

    def pull(self, tag: str | None = None) -> None:
        """Pull a dump into the pulls directory."""
        p = self.project
        s = self.server
        self._database()
        pulls = self._ensure_pulls_dir()
        self._cleanup_stale_parts(pulls)
        sqlfile = self._dest(p.name, pulls, s.name, tag=tag)

        if s.server_type == "lando":
            # lando adds the gz extension itself so we remove here
            final = _unique_path(Path(str(sqlfile)[:-3]))
            self._run_part_pull(self._part_path(final), final, self._pull_lando)
        elif s.server_type == "ddev":
            final = _unique_path(sqlfile)
            self._run_part_pull(self._part_path(final), final, self._pull_ddev)
        else:
            final = _unique_path(sqlfile)
            self._run_part_pull(
                self._part_path(final),
                final,
                lambda part, target: self._pull(part, local=True, final=target),
            )

    def _pull_lando(self, sqlfile: Path, final: Path) -> None:
        """Pull through Lando, keeping stderr for real failures."""
        # Lando writes update messages to stderr even on success; the
        # return code decides whether they are errors.
        command = Pipeline((Argv(("lando", "db-export", str(sqlfile))),))
        self.run_pull_cmd(command, sqlfile, True, final)

    def _pull_ddev(self, sqlfile: Path, final: Path) -> None:
        """Pull through DDEV, keeping stderr for real failures."""
        # DDEV writes informational output to stderr even on success.
        command = Pipeline(
            (
                Argv(
                    (
                        "ddev",
                        "export-db",
                        "--gzip",
                        f"--file={sqlfile}",
                    )
                ),
            ),
        )
        self.run_pull_cmd(command, sqlfile, True, final)

    def _pull(
        self,
        sqlfile: str | Path,
        local: bool = True,
        final: Path | None = None,
    ) -> None:
        """Build and run a local or remote dump pipeline."""
        p = self.project
        s = self.server
        db = self._database()

        if p.pulls_dir is None or not p.pulls_dir.exists():
            ui.error(f"Pulls dir not found: {p.pulls_dir}")

        if not s.ssh:
            raise CommandError(f"Server has no ssh settings ({s.name})")
        ssh = s.ssh[0]

        if s.mamp:
            mysqldump = str(Path(s.mamp) / "mysqldump")
            with local_mysql_credentials(
                user=db.username,
                password=db.password or "",
                host=db.hostname,
                port=_port(db),
                ssl_mode=db.effective_ssl_mode,
                ssl_ca=db.ssl_ca,
                ssl_cert=db.ssl_cert,
                ssl_key=db.ssl_key,
                skip_secure_auth=db.skip_secure_auth,
                real=self.real,
            ) as credentials:
                argv = [mysqldump, *_dump_argv(db, credentials)[1:]]
                command = Pipeline(
                    (
                        Argv(tuple(argv)),
                        Argv(("gzip", "-c")),
                    ),
                    stdout_path=Path(sqlfile),
                    stdout_mode=0o600,
                    stdout_exclusive=True,
                )
                result = run(command, real=self.real, capture=True)
            self._report_pull(result, Path(sqlfile), local, final)
            return

        with remote_mysql_credentials(
            ssh,
            password=db.password or "",
            user=db.username,
            host=db.hostname,
            port=_port(db),
            ssl_mode=db.effective_ssl_mode,
            ssl_ca=db.ssl_ca,
            ssl_cert=db.ssl_cert,
            ssl_key=db.ssl_key,
            skip_secure_auth=db.skip_secure_auth,
            real=self.real,
        ) as credentials:
            dump_argv = _dump_argv(
                db, credentials, mysqlpump=self.project.mysqlpump
            )
            if local:
                fragment = credentials.trap_command(shlex.join(dump_argv))
                command = Pipeline(
                    (
                        remote_command(
                            ssh, fragment, compress=True, timeout=25
                        ),
                        Argv(("gzip", "-c")),
                    ),
                    stdout_path=Path(sqlfile),
                    stdout_mode=0o600,
                    stdout_exclusive=True,
                )
            else:
                destination = shlex.quote(str(sqlfile))
                fragment = credentials.trap_command(
                    f"{shlex.join(dump_argv)} | gzip -c | "
                    f"sudo tee {destination} >/dev/null"
                )
                command = remote_command(ssh, fragment, compress=True)
            result = run(command, real=self.real, capture=True)
            self._report_pull(result, Path(sqlfile), local, final)

    def _report_pull(
        self,
        result: Result,
        sqlfile: Path,
        local: bool,
        final: Path | None = None,
    ) -> None:
        """Report the result of a pull and commit a successful dump."""
        if not self.real:
            ui.display_success(
                self.real,
                server=self.server.name,
                message="sql download complete",
            )
        elif result.returncode:
            if local:
                self._cleanup_part(sqlfile)
            display = final or sqlfile
            if ui.quiet < 2:
                ui.err_console.print(str(display.absolute()), style="yellow")
            ui.error(
                f"\n{result.stderr or 'Command failed'}",
                secrets=self.secrets,
            )
        elif local:
            actual = self._actual_part(sqlfile)
            if actual is None:
                ui.error("Command failed")
                return
            if final is not None:
                target = self._final_path(final, actual)
                actual.replace(target)
            else:
                target = actual
            # Lando/DDEV and tools that create the file themselves may use a
            # wider mode.  The private pulls directory is the primary control;
            # this is defense in depth for the dump itself.
            with suppress(OSError):
                target.chmod(0o600)
            filename = str(target.absolute())
            if ui.quiet < 2:
                ui.console.print(filename, style="green")
            self.make_symlink(target)
            if not self.filename_only:
                ui.display_success(
                    self.real,
                    server=self.server.name,
                    message="sql download complete",
                )
        elif result.ok:
            ui.display_success(
                self.real,
                server=self.server.name,
                message="sql download complete",
            )
        else:
            ui.error("Command failed")

    def run_pull_cmd(
        self,
        cmd: Command,
        sqlfile: str | Path,
        local: bool,
        final: Path | None = None,
    ) -> None:
        """Run a pull command and report its result."""
        result = run(cmd, real=self.real, capture=True)
        self._report_pull(result, Path(sqlfile), local, final)

    def make_symlink(self, sqlfile: Path) -> None:
        """Point ``LATEST-<server>.sql.gz`` at the newest dump.

        Concurrent pulls finish at about the same time.  Build the link at a
        process-unique temporary name and replace the real link atomically so
        neither pull can observe a missing link or fail with ``FileExistsError``.
        """
        server = _filename_component(self.server.name)
        link_name = sqlfile.parent / f"LATEST-{server}.sql.gz"
        temporary = link_name.with_name(f".{link_name.name}.{os.getpid()}.tmp")
        try:
            temporary.symlink_to(f"./{sqlfile.name}")
            temporary.replace(link_name)
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()

    def load_remote(self, source: str | Path) -> None:
        """Load a dump that already exists on the server."""
        source = Path(source)
        self._put(source, local=False)

    def put(self, sqlfile: str | Path) -> None:
        """Push a local dump to the server."""
        sql = Path(sqlfile)
        _validate_gzip(sql)
        s = self.server
        self._database()
        if s.server_type == "lando":
            self._put_lando(sql)
        elif s.server_type == "ddev":
            self._put_ddev(sql)
        else:
            self._put(sql)

    def _put_lando(self, sql: Path) -> None:
        """Import through Lando."""
        command = Pipeline((Argv(("lando", "db-import", str(sql))),))
        self.run_put_cmd(command)

    def _put_ddev(self, sql: Path) -> None:
        """Import through DDEV."""
        command = Argv(("ddev", "import-db", "--progress", f"--src={sql}"))
        self.run_put_cmd(command)

    def _source_stage(self, sqlfile: Path) -> Argv:
        """Use pv only when configured and installed; otherwise cat."""
        if self.project.pv and shutil.which("pv"):
            return Argv(("pv", "--numeric", str(sqlfile)))
        return Argv(("cat", str(sqlfile)))

    def _put(self, sqlfile: Path, local: bool = True) -> None:
        """Build and run a local or remote import pipeline."""
        s = self.server
        db = self._database()
        if not self._confirm_overwrite():
            return
        if not s.ssh:
            raise CommandError(f"Server has no ssh settings ({s.name})")
        ssh = s.ssh[0]

        if local:
            if not sqlfile.exists():
                ui.error(f"{sqlfile} does not exist")
        else:
            command = remote_command(
                ssh,
                f"test -f {shlex.quote(str(sqlfile))}",
                batch=True,
                timeout=25,
            )
            result = run(command, real=self.real, capture=True)
            if self.real and result.returncode:
                ui.error(f"{sqlfile} does not exist")

        if s.mamp:
            mysql = str(Path(s.mamp) / "mysql")
            with local_mysql_credentials(
                user=db.username,
                password=db.password or "",
                host=db.hostname,
                port=_port(db),
                ssl_mode=db.effective_ssl_mode,
                ssl_ca=db.ssl_ca,
                ssl_cert=db.ssl_cert,
                ssl_key=db.ssl_key,
                skip_secure_auth=db.skip_secure_auth,
                real=self.real,
            ) as credentials:
                argv = [mysql, *_mysql_argv(db, credentials)[1:]]
                command = Pipeline(
                    (
                        self._source_stage(sqlfile),
                        Argv(("gunzip", "-c")),
                        Argv(tuple(argv)),
                    )
                )
                result = run(command, real=self.real, capture=True)
            self._report_put(result)
            return

        with remote_mysql_credentials(
            ssh,
            password=db.password or "",
            user=db.username,
            host=db.hostname,
            port=_port(db),
            ssl_mode=db.effective_ssl_mode,
            ssl_ca=db.ssl_ca,
            ssl_cert=db.ssl_cert,
            ssl_key=db.ssl_key,
            skip_secure_auth=db.skip_secure_auth,
            real=self.real,
        ) as credentials:
            mysql = shlex.join(_mysql_argv(db, credentials))
            if local:
                command = Pipeline(
                    (
                        self._source_stage(sqlfile),
                        remote_command(
                            ssh,
                            credentials.trap_command(f"gunzip -c | {mysql}"),
                            timeout=25,
                        ),
                    )
                )
            else:
                fragment = credentials.trap_command(
                    f"zcat {shlex.quote(str(sqlfile))} | {mysql}"
                )
                command = remote_command(ssh, fragment, timeout=25)
            result = run(command, real=self.real, capture=True)
            self._report_put(result)

    def _report_put(self, result: Result) -> None:
        """Report the result of an import."""
        if not self.real:
            ui.display_success(
                self.real,
                server=self.server.name,
                message="sql upload complete",
            )
            return
        # ``pv --numeric`` writes progress percentages to stderr.  They are
        # not errors, so keep only non-numeric lines for the failure report.
        errors = [
            line
            for line in result.stderr.splitlines()
            if line.strip() and not line.strip().isdigit()
        ]
        if result.returncode:
            if errors:
                for line in errors:
                    ui.error(line, exit=False, secrets=self.secrets)
            else:
                ui.error("Command failed", exit=False, secrets=self.secrets)
            sys.exit(1)
        ui.display_success(
            self.real,
            server=self.server.name,
            message="sql upload complete",
        )

    def _confirm_overwrite(self) -> bool:
        """Ask before overwriting a database on a warned server."""
        if not (self.real and self.server.warn):
            return True
        msg = (
            f" WARNING: You are about to overwrite the {self.server.name} "
            "database, continue?"
        )
        return click.confirm(msg)

    def run_put_cmd(self, cmd: Command) -> None:
        """Confirm, run, and report an import command."""
        if not self._confirm_overwrite():
            return
        result = run(cmd, real=self.real, capture=True)
        self._report_put(result)

    def _dest(
        self,
        project_name: str,
        dirname: Path,
        id: str,
        tag: str | None,
    ) -> Path:
        """Build the timestamped dump filename."""
        _validate_tag(tag)
        now = datetime.datetime.now(datetime.UTC).astimezone()
        now = now.strftime("%y-%m-%d_%H-%M-%S")
        tag = f"-{tag}" if tag else ""
        project = _filename_component(project_name)
        server = _filename_component(id)
        name = f"{project}-{server}-{now}{tag}.sql.gz"
        return Path(dirname, name)

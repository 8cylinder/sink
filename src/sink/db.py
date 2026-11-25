"""Pull and push MySQL databases safely."""

import datetime
import os
import shlex
import shutil
import sys
from contextlib import suppress
from pathlib import Path

import click

from sink.config.models import DatabaseConfig, Project, Server
from sink.credentials import RemoteCredentials, remote_mysql_credentials
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
    db: DatabaseConfig, credentials: RemoteCredentials | None = None
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
    if db.skip_secure_auth:
        options.append("--skip-secure-auth")
    return options


def _dump_argv(
    db: DatabaseConfig,
    credentials: RemoteCredentials | None = None,
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
    db: DatabaseConfig, credentials: RemoteCredentials | None = None
) -> list[str]:
    """Build the mysql import argv."""
    return [
        "mysql",
        *_client_options(db, credentials),
        db.db or "",
    ]


def _env_with_password(db: DatabaseConfig) -> dict[str, str]:
    """Return an environment carrying ``MYSQL_PWD``."""
    env = os.environ.copy()
    if db.password:
        env["MYSQL_PWD"] = db.password
    return env


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

    def pull(self, tag: str | None = None) -> None:
        """Pull a dump into the pulls directory."""
        p = self.project
        s = self.server
        self._database()

        if p.pulls_dir is None:
            raise CommandError("project.pulls_dir is not configured")
        sqlfile = self._dest(p.name, p.pulls_dir, s.name, tag=tag)

        if s.server_type == "lando":
            # lando adds the gz extension itself so we remove here
            sqlfile = Path(str(sqlfile)[:-3])
            self._pull_lando(sqlfile)
        elif s.server_type == "ddev":
            self._pull_ddev(sqlfile)
        else:
            self._pull(sqlfile, local=True)

    def _pull_lando(self, sqlfile: Path) -> None:
        """Pull through Lando, keeping stderr for real failures."""
        # Lando writes update messages to stderr even on success; the
        # return code decides whether they are errors.
        command = Pipeline((Argv(("lando", "db-export", str(sqlfile))),))
        self.run_pull_cmd(command, sqlfile, True)

    def _pull_ddev(self, sqlfile: Path) -> None:
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
        self.run_pull_cmd(command, sqlfile, True)

    def _pull(self, sqlfile: str | Path, local: bool = True) -> None:
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
            argv = [mysqldump, *_dump_argv(db)[1:]]
            command = Pipeline(
                (
                    Argv(tuple(argv), env_refs=("MYSQL_PWD",)),
                    Argv(("gzip", "-c")),
                ),
                stdout_path=Path(sqlfile),
            )
            env = _env_with_password(db)
            result = run(command, real=self.real, capture=True, env=env)
            self._report_pull(result, Path(sqlfile), local)
            return

        with remote_mysql_credentials(
            ssh,
            password=db.password or "",
            user=db.username,
            host=db.hostname,
            port=_port(db),
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
                )
            else:
                destination = shlex.quote(str(sqlfile))
                fragment = credentials.trap_command(
                    f"{shlex.join(dump_argv)} | gzip -c | "
                    f"sudo tee {destination} >/dev/null"
                )
                command = remote_command(ssh, fragment, compress=True)
            result = run(command, real=self.real, capture=True)
            self._report_pull(result, Path(sqlfile), local)

    def _report_pull(self, result: Result, sqlfile: Path, local: bool) -> None:
        """Report the result of a pull."""
        if not self.real:
            ui.display_success(
                self.real,
                server=self.server.name,
                message="sql download complete",
            )
        elif result.returncode:
            if ui.quiet < 2:
                ui.err_console.print(str(sqlfile.absolute()), style="yellow")
            ui.error(
                f"\n{result.stderr or 'Command failed'}",
                secrets=self.secrets,
            )
        elif local and (sqlfile.exists() or Path(f"{sqlfile}.gz").exists()):
            actual = sqlfile if sqlfile.exists() else Path(f"{sqlfile}.gz")
            filename = str(actual.absolute())
            if ui.quiet < 2:
                ui.console.print(filename, style="green")
            if not self.filename_only:
                ui.display_success(
                    self.real,
                    server=self.server.name,
                    message="sql download complete",
                )
            self.make_symlink(actual)
        elif not local and result.ok:
            ui.display_success(
                self.real,
                server=self.server.name,
                message="sql download complete",
            )
        elif local:
            ui.error("Command failed")

    def run_pull_cmd(
        self, cmd: Command, sqlfile: str | Path, local: bool
    ) -> None:
        """Run a pull command and report its result."""
        result = run(cmd, real=self.real, capture=True)
        self._report_pull(result, Path(sqlfile), local)

    def make_symlink(self, sqlfile: Path) -> None:
        """Point ``LATEST-<server>.sql.gz`` at the newest dump."""
        link_name = sqlfile.parent / f"LATEST-{self.server.name}.sql.gz"
        with suppress(FileNotFoundError):
            # The latest file may not exist yet.
            link_name.unlink()
        link_name.symlink_to(f"./{sqlfile.name}")

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
            argv = [mysql, *_mysql_argv(db)[1:]]
            command = Pipeline(
                (
                    self._source_stage(sqlfile),
                    Argv(("gunzip", "-c")),
                    Argv(tuple(argv), env_refs=("MYSQL_PWD",)),
                )
            )
            env = _env_with_password(db)
            result = run(command, real=self.real, capture=True, env=env)
            self._report_put(result)
            return

        with remote_mysql_credentials(
            ssh,
            password=db.password or "",
            user=db.username,
            host=db.hostname,
            port=_port(db),
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

    def run_put_cmd(self, cmd: Command) -> None:
        """Confirm, run, and report an import command."""
        s = self.server
        if self.real and s.warn:
            msg = (
                f" WARNING: You are about to overwrite the {s.name} "
                "database, continue?"
            )
            if not click.confirm(msg):
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
        now = datetime.datetime.now(datetime.UTC).astimezone()
        now = now.strftime("%y-%m-%d_%H-%M-%S")
        tag = f"-{tag}" if tag else ""
        name = f"{project_name}-{id}-{now}{tag}.sql.gz"
        return Path(dirname, name)

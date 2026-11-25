import datetime
import os
import shlex
import sys
from contextlib import contextmanager, suppress
from pathlib import Path

import click

from sink.config.models import DatabaseConfig, Project, Server
from sink.credentials import remote_mysql_credentials
from sink.errors import CommandError
from sink.shell import Argv, Pipeline, remote_command, run
from sink.ui import ui


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


def _port(db):
    try:
        return int(db.port)
    except AttributeError, TypeError, ValueError:
        return None


def _client_options(db, credentials=None):
    if credentials is not None:
        return [credentials.option]
    options = []
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


def _mysqldump_argv(db, credentials=None):
    return [
        "mysqldump",
        *_client_options(db, credentials),
        "--single-transaction",
        "--triggers",
        "--events",
        "--routines",
        "--no-tablespaces",
        db.db,
    ]


def _mysql_argv(db, credentials=None):
    return ["mysql", *_client_options(db, credentials), db.db]


def _env_with_password(db):
    env = os.environ.copy()
    if db.password:
        env["MYSQL_PWD"] = db.password
    return env


class DB:
    def __init__(
        self,
        project: Project,
        server: Server,
        real=False,
        verbose=False,
        filename_only=False,
    ):
        self.verbose = bool(verbose)
        self.real = real
        self.project = project
        self.server = server
        self.filename_only = filename_only
        self.secrets: tuple[str, ...] = ()

    def _database(self) -> DatabaseConfig:
        if not self.server.databases:
            raise CommandError(
                f"Server {self.server.name} has no database configured"
            )
        database = self.server.databases[0]
        self.secrets = (database.password or "",)
        return database

    def dump_remote(self, dest):
        dest = Path(dest)
        self._pull(dest, local=False)

    def pull(self, tag=None):
        p = self.project
        s = self.server
        db = self._database()

        if p.pulls_dir is None:
            raise CommandError("project.pulls_dir is not configured")
        sqlfile = self._dest(p.name, db.db, p.pulls_dir, s.name, tag=tag)

        if s.server_type == "lando":
            # lando adds the gz extension itself so we remove here
            sqlfile = Path(str(sqlfile)[:-3])
            self._pull_lando(sqlfile)
        elif s.server_type == "ddev":
            self._pull_ddev(sqlfile)
        else:
            self._pull(sqlfile, local=True)

    def _pull_lando(self, sqlfile):
        # suppress stderr since lando outputs update messages there
        command = Pipeline(
            (Argv(("lando", "db-export", str(sqlfile))),),
            stderr_devnull=True,
        )
        self.run_pull_cmd(command, sqlfile, True)

    def _pull_ddev(self, sqlfile):
        # ddev outputs informational output on stderr.
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
            stderr_devnull=True,
        )
        self.run_pull_cmd(command, sqlfile, True)

    def _pull(self, sqlfile, local=True):
        p = self.project
        s = self.server
        db = self._database()

        if p.pulls_dir is None or not p.pulls_dir.exists():
            ui.error(f"Pulls dir not found: {p.pulls_dir}")

        if not s.ssh:
            raise CommandError(f"Server has no ssh settings ({s.name})")
        ssh = s.ssh[0]

        if s.mamp:
            mysqldump = os.path.join(s.mamp, "mysqldump")
            argv = [mysqldump, *_mysqldump_argv(db)[1:]]
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
            dump_argv = _mysqldump_argv(db, credentials)
            if local:
                fragment = shlex.join(dump_argv)
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
                fragment = (
                    f"{shlex.join(dump_argv)} | gzip -c | "
                    f"sudo tee {destination} >/dev/null"
                )
                command = remote_command(ssh, fragment, compress=True)
            result = run(command, real=self.real, capture=True)
            self._report_pull(result, Path(sqlfile), local)

    def _report_pull(self, result, sqlfile, local):
        if not self.real:
            ui.display_success(
                self.real,
                server=self.server.name,
                message="sql download complete",
            )
        elif result.stderr:
            if ui.quiet < 2:
                ui.err_console.print(str(sqlfile.absolute()), style="yellow")
            ui.error(f"\n{result.stderr}", secrets=self.secrets)
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
            ui.error("Command failed", exit=False)

    def run_pull_cmd(self, cmd, sqlfile, local):
        result = run(cmd, real=self.real, capture=True)
        self._report_pull(result, Path(sqlfile), local)

    def make_symlink(self, sqlfile):
        link_name = Path(f"LATEST-{self.server.name}.sql.gz")
        with cd(sqlfile.parent):
            with suppress(FileNotFoundError):
                # The latest file may not exist yet.
                link_name.unlink()
            link_name.symlink_to(f"./{sqlfile.name}")

    def load_remote(self, source):
        source = Path(source)
        self._put(source, local=False)

    def put(self, sqlfile):
        s = self.server
        self._database()
        sql = Path(sqlfile)
        if s.server_type == "lando":
            self._put_lando(sql)
        elif s.server_type == "ddev":
            self._put_ddev(sql)
        else:
            self._put(sql)

    def _put_lando(self, sql):
        command = Pipeline(
            (Argv(("lando", "db-import", str(sql))),),
            stderr_devnull=True,
        )
        self.run_put_cmd(command)

    def _put_ddev(self, sql):
        command = Argv(("ddev", "import-db", "--progress", f"--src={sql}"))
        self.run_put_cmd(command)

    def _put(self, sqlfile, local=True):
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
            mysql = os.path.join(s.mamp, "mysql")
            argv = [mysql, *_mysql_argv(db)[1:]]
            command = Pipeline(
                (
                    Argv(("pv", "--numeric", str(sqlfile))),
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
                        Argv(("pv", "--numeric", str(sqlfile))),
                        remote_command(ssh, f"gunzip -c | {mysql}", timeout=25),
                    )
                )
            else:
                fragment = f"zcat {shlex.quote(str(sqlfile))} | {mysql}"
                command = remote_command(ssh, fragment, timeout=25)
            result = run(command, real=self.real, capture=True)
            self._report_put(result)

    def _report_put(self, result):
        if not self.real:
            ui.display_success(
                self.real,
                server=self.server.name,
                message="sql upload complete",
            )
            return
        errors = [
            line
            for line in result.stderr.splitlines()
            if line.strip() and not line.strip().isdigit()
        ]
        if result.returncode or errors:
            for line in errors:
                ui.error(line, exit=False, secrets=self.secrets)
            sys.exit(1)
        ui.display_success(
            self.real,
            server=self.server.name,
            message="sql upload complete",
        )

    def run_put_cmd(self, cmd):
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

    def _dest(self, project_name, dbname, dirname, id, tag):
        now = datetime.datetime.now()
        now = now.strftime("%y-%m-%d_%H-%M-%S")
        tag = f"-{tag}" if tag else ""
        name = f"{project_name}-{id}-{now}{tag}.sql.gz"
        return Path(dirname, name)

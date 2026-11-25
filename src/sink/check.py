import shlex
import ssl
import urllib.error
import urllib.request
from pathlib import Path

import click

from sink.config import Spinner, config
from sink.credentials import remote_mysql_credentials
from sink.shell import remote_command, run
from sink.ui import Color, ui


class TestConfig:
    good = click.style("[\u2713]", fg=Color.GREEN.value)
    bad = click.style("[X]", fg=Color.RED.value)
    timeout = 25

    def __init__(self, real=False, insecure=False):
        self.config = config
        self.real = real
        self.insecure = insecure

    def test_project(self):
        click.echo()
        click.secho("Local dirs", fg=Color.GREEN.value, bold=True)

        INDENT = 2
        for local_dir in ["pulls_dir", "log_dir", "cache_dir"]:
            try:
                d = Path(self.config.data["project"][local_dir])
            except KeyError:
                self.out(
                    f'{self.bad} "{local_dir}" setting in '
                    f"{self.config.config_file} does not exist.",
                    INDENT,
                )
                continue
            if d.exists():
                self.out(f"{self.good} {d}", INDENT)
            else:
                self.out(f"{self.bad} {d}", INDENT)

    def test_requirements(self):
        required = ["ssh -V", "git --version", "rsync --version"]
        required = [f"'{i}'" for i in required]
        req = " ".join(required)
        spliter = "==="
        cmd = f"""for prg in {req}; do echo '{spliter}'; $prg; done"""
        click.echo()
        click.echo("Run the following bash command:")
        click.echo(cmd)

    def test_servers(self, server_names=None):
        click.echo()
        for s in self.config.servers():
            if server_names and s.servername not in server_names:
                continue
            try:
                click.echo()
                click.secho(
                    f"{s.servername}",
                    fg=Color.GREEN.value,
                    bold=True,
                    underline=True,
                )
            except AttributeError:
                pass

            # ssh login
            for ssh in s.ssh:
                user = ssh.username
                url = ssh.server

                try:
                    ssh.username  # noqa: B018 - intentional attribute probe
                    ssh.server  # noqa: B018 - intentional attribute probe
                except AttributeError:
                    ui.error(f"ssh values are wrong in {s.servername}")
                if not ssh.username or not ssh.server:
                    ui.warn("missing values for ssh.", indent="  ")
                    continue

                cmd = "exit"
                good = f"ssh login good ({ssh.username})."
                bad = f'ssh login failed for "{user}@{url}".'

                if self.run_cmd_on_server(ssh, cmd, good, bad):
                    # root
                    cmd = f"cd {shlex.quote(str(s.root))}"
                    good = "root dir exists."
                    bad = f"root dir does not exist on server: {s.root}."
                    self.run_cmd_on_server(ssh, cmd, good, bad)

                    dbs = self.config.dbs(s.mysql)
                    for db in dbs:
                        with remote_mysql_credentials(
                            ssh,
                            password=db.password,
                            user=db.username,
                            host=db.hostname,
                            port=_port(db),
                            real=self.real,
                        ) as credentials:
                            argv = [
                                "mysql",
                                credentials.option,
                                db.db,
                                "--execute=exit",
                            ]
                            cmd = shlex.join(argv) + ";"
                            good = (
                                f"DB({db.db}): mysql username, password "
                                "and db are good."
                            )
                            bad = f"DB({db.db}): mysql error."
                            self.run_cmd_on_server(ssh, cmd, good, bad)

            urls = self.config.urls(s.urls) or []
            for u in urls:
                if not u.url:
                    # if there is a url section in the yaml file, but
                    # no values for it, continue.
                    continue
                if not self.real:
                    self.out(f"+ URL({u.url})", 2)
                    continue
                spinner = Spinner(indent=2, delay=0.1)
                spinner.start()
                try:
                    ctx = ssl.create_default_context()
                    if self.insecure:
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    urllib.request.urlopen(
                        u.url, timeout=self.timeout, context=ctx
                    )
                except urllib.error.HTTPError as e:
                    # Return code error (e.g. 404, 501, ...)
                    msg = f"{self.bad} URL({u.url}): HTTPError: {e.code}."
                except urllib.error.URLError as e:
                    # Not an HTTP-specific error (e.g. connection refused)
                    msg = f"{self.bad} URL({u.url}): URLError: {e.reason}."
                except ValueError:
                    msg = f"{self.bad} URL({u.url}): Not a valid URL."
                except AttributeError as e:
                    msg = f"AttributeError? {u.url} {e}"
                except TimeoutError:
                    msg = f"{self.bad} URL({u.url}) Timeout."
                else:
                    # 200
                    msg = f"{self.good} URL({u.url})"
                spinner.stop()
                self.out(msg, 2)

    def out(self, msg, spaces):
        indent = " " * spaces
        click.echo(f"{indent}{msg}")

    def run_cmd_on_server(self, ssh, cmd, good, bad):
        command = remote_command(
            ssh,
            cmd,
            batch=True,
            timeout=self.timeout,
        )
        result = run(command, real=self.real, capture=True)
        if not self.real:
            return True
        if result.returncode:
            self.out(f"{self.bad} {bad} (error: {result.returncode})", 2)
            if result.stderr:
                ui.error(result.stderr, exit=False, indent=8)
            return False

        self.out(f"{self.good} {good}", 2)
        return True


def _port(db):
    try:
        return int(db.port)
    except AttributeError, TypeError, ValueError:
        return None

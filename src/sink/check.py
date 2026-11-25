import shlex
import ssl
import urllib.error
import urllib.request

from sink.config.models import Config
from sink.credentials import remote_mysql_credentials
from sink.shell import remote_command, run
from sink.ui import Spinner, ui


class TestConfig:
    good = "[\u2713]"
    bad = "[X]"
    timeout = 25

    def __init__(self, config: Config, real=False, insecure=False):
        self.config = config
        self.real = real
        self.insecure = insecure

    def test_project(self):
        ui.echo()
        ui.heading("Local dirs")

        indent = 2
        for name in ["pulls_dir", "log_dir", "cache_dir"]:
            directory = getattr(self.config.project, name)
            if directory is None:
                self.out(
                    f'{self.bad} "{name}" setting in '
                    f"{self.config.path} does not exist.",
                    indent,
                )
                continue
            if directory.exists():
                self.out(f"{self.good} {directory}", indent)
            else:
                self.out(f"{self.bad} {directory}", indent)

    def test_requirements(self):
        required = ["ssh -V", "git --version", "rsync --version"]
        required = [f"'{i}'" for i in required]
        req = " ".join(required)
        spliter = "==="
        cmd = f"""for prg in {req}; do echo '{spliter}'; $prg; done"""
        ui.echo()
        ui.echo("Run the following bash command:")
        ui.echo(cmd)

    def test_servers(self, server_names=None):
        ui.echo()
        for s in self.config.servers.values():
            if server_names and s.name not in server_names:
                continue
            ui.echo()
            ui.heading(s.name, underline=True)

            # ssh login
            for ssh in s.ssh:
                user = ssh.username
                url = ssh.server

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

                    for db in s.databases:
                        with remote_mysql_credentials(
                            ssh,
                            password=db.password or "",
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

            for u in s.urls:
                if not u.url:
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
                    msg = f"{self.bad} URL({u.url}): HTTPError: {e.code}."
                except urllib.error.URLError as e:
                    msg = f"{self.bad} URL({u.url}): URLError: {e.reason}."
                except ValueError:
                    msg = f"{self.bad} URL({u.url}): Not a valid URL."
                except AttributeError as e:
                    msg = f"AttributeError? {u.url} {e}"
                except TimeoutError:
                    msg = f"{self.bad} URL({u.url}) Timeout."
                else:
                    msg = f"{self.good} URL({u.url})"
                spinner.stop()
                self.out(msg, 2)

    def out(self, msg, spaces):
        indent = " " * spaces
        ui.output(f"{indent}{msg}\n")

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

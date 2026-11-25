"""Check server, database, and URL configuration."""

import shlex
import shutil
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from sink.config.models import Config
from sink.credentials import remote_mysql_credentials
from sink.shell import remote_command, run
from sink.ui import ui


class TestConfig:
    """Run the configured server and URL checks."""

    good = "[\u2713]"
    bad = "[X]"
    timeout = 25

    def __init__(self, config: Config, real=False, insecure=False):
        self.config = config
        self.real = real
        self.insecure = insecure

    def test_project(self):
        """Check project dirs and the configured rsync binary."""
        ui.echo()
        ui.heading("Local dirs")

        rows = []
        for name in ["pulls_dir", "log_dir", "cache_dir"]:
            directory = getattr(self.config.project, name)
            if directory is None:
                rows.append((name, "(not configured)", "not configured"))
            else:
                status = "ok" if directory.exists() else "missing"
                rows.append((name, str(directory), status))

        rsync = self.config.project.rsync_binary
        resolved = shutil.which(rsync)
        if resolved is None and Path(rsync).is_file():
            resolved = str(Path(rsync).resolve())
        rows.append(
            (
                "rsync_binary",
                resolved or rsync,
                "ok" if resolved else "missing",
            )
        )
        self.table(rows)

    def test_requirements(self):
        """Print the local tool-version command."""
        required = ["ssh -V", "git --version", "rsync --version"]
        required = [f"'{i}'" for i in required]
        req = " ".join(required)
        spliter = "==="
        cmd = f"""for prg in {req}; do echo '{spliter}'; $prg; done"""
        ui.echo()
        ui.echo("Run the following bash command:")
        ui.echo(cmd)

    def test_servers(self, server_names=None):
        """Check ssh, root, database, and URL access."""
        ui.echo()
        for s in self.config.servers.values():
            if server_names and s.name not in server_names:
                continue
            ui.echo()
            ui.heading(s.name, underline=True)
            self.table(
                [
                    (
                        "root",
                        str(s.root) if s.root else "(not configured)",
                        "ok" if s.root else "not configured",
                    ),
                    ("warn", str(s.warn), "ok"),
                    ("automatic", str(s.automatic), "ok"),
                ]
            )

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
                with ui.status(f"Checking {u.url}"):
                    try:
                        # Default verifies the certificate chain and hostname;
                        # --insecure is the explicit opt-out for self-signed sites.
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
                self.out(msg, 2)

    def table(self, rows):
        """Print a stable Setting/Value/Status table."""
        name_width = max(
            (len(name) for name, _value, _status in rows), default=8
        )
        value_width = max(
            (len(value) for _name, value, _status in rows), default=5
        )
        self.out(
            f"{'Setting'.ljust(name_width)}  "
            f"{'Value'.ljust(value_width)}  Status",
            2,
        )
        for name, value, status in rows:
            mark = self.good if status == "ok" else self.bad
            self.out(
                f"{name.ljust(name_width)}  {value.ljust(value_width)}  "
                f"{mark} {status}",
                2,
            )

    def out(self, msg, spaces):
        """Print an indented status line."""
        indent = " " * spaces
        ui.output(f"{indent}{msg}\n")

    def run_cmd_on_server(self, ssh, cmd, good, bad):
        """Run one probe, printing the command and result."""
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
    """Return a database port as an integer, or ``None``."""
    try:
        return int(db.port)
    except AttributeError, TypeError, ValueError:
        return None

"""Check server, database, and URL configuration."""

import shlex
import shutil
import ssl
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from rich.text import Text

from sink.config.models import Config, DatabaseConfig, SSHConfig
from sink.credentials import remote_mysql_credentials
from sink.shell import remote_command, run
from sink.ui import ui


class TestConfig:
    """Run the configured server and URL checks."""

    good = "[\u2713]"
    bad = "[✗]"
    timeout = 25

    def __init__(self, config: Config, insecure: bool = False) -> None:
        self.config = config
        self.insecure = insecure

    def test_unknown_keys(self) -> None:
        """Report unknown config keys as warnings without failing the run."""
        for key in self.config.unknown_keys:
            ui.warn(f"unknown config key: {key}")

    def test_project(self) -> None:
        """Check project dirs and the configured rsync binary."""
        ui.echo()
        ui.heading("Local dirs")

        rows = []
        for name in ["pulls_dir"]:
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

    def test_requirements(self) -> None:
        """Print the local tool-version command."""
        required = ["ssh -V", "git --version", "rsync --version"]
        required = [f"'{i}'" for i in required]
        req = " ".join(required)
        spliter = "==="
        cmd = f"""for prg in {req}; do echo '{spliter}'; $prg; done"""
        ui.echo()
        ui.echo("Run the following bash command:")
        ui.echo(cmd)

    def test_servers(self, server_names: tuple[str, ...] | None = None) -> None:
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
                            real=True,
                        ) as credentials:
                            argv = [
                                "mysql",
                                credentials.option,
                                db.db,
                                "--execute=exit",
                            ]
                            cmd = shlex.join(str(value) for value in argv) + ";"
                            label = _db_label(db)
                            good = (
                                f"{label}: mysql username, password "
                                "and db are good."
                            )
                            bad = f"{label}: mysql error."
                            self.run_cmd_on_server(ssh, cmd, good, bad)

            for u in s.urls:
                if not u.url:
                    continue
                ok = False
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
                        msg = f"URL({u.url}): HTTPError: {e.code}."
                    except urllib.error.URLError as e:
                        msg = f"URL({u.url}): URLError: {e.reason}."
                    except ValueError:
                        msg = f"URL({u.url}): Not a valid URL."
                    except AttributeError as e:
                        msg = f"AttributeError? {u.url} {e}"
                    except TimeoutError:
                        msg = f"URL({u.url}) Timeout."
                    else:
                        ok = True
                        msg = f"URL({u.url})"
                self.line(ok, msg, spaces=2)

    def table(self, rows: Sequence[tuple[str, str, str]]) -> None:
        """Print status rows as ``[mark] key: value``."""
        for name, value, status in rows:
            self.line(status == "ok", name, value, spaces=2)

    def line(
        self,
        ok: bool,
        msg: str,
        value: str | None = None,
        spaces: int = 0,
    ) -> None:
        """Print one colored status line with the marker in front."""
        if ui.quiet >= 2:
            return
        text = Text()
        text.append(
            f"{' ' * spaces}{self.good if ok else self.bad} ",
            style="green" if ok else "red",
        )
        if value is None:
            text.append(msg)
        else:
            text.append(msg, style="cyan")
            text.append(": ")
            text.append(value, style="white")
        ui.console.print(text, soft_wrap=True)

    def run_cmd_on_server(
        self, ssh: SSHConfig, cmd: str, good: str, bad: str
    ) -> bool:
        """Run one probe, printing the command and result."""
        command = remote_command(
            ssh,
            cmd,
            batch=True,
            timeout=self.timeout,
        )
        result = run(command, real=True, capture=True)
        if result.returncode:
            self.line(False, f"{bad} (error: {result.returncode})", spaces=2)
            if result.stderr:
                ui.error(result.stderr, exit=False, indent=6)
            return False

        self.line(True, good, spaces=2)
        return True


def _db_label(db: DatabaseConfig) -> str:
    """Return a database label that distinguishes credential entries."""
    label = f"DB({db.db})"
    if db.username:
        label += f" as {db.username}"
    return label


def _port(db: DatabaseConfig) -> int | None:
    """Return a database port as an integer, or ``None``."""
    if db.port is None:
        return None
    try:
        return int(db.port)
    except AttributeError, TypeError, ValueError:
        return None

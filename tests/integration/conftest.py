"""Docker-backed fixtures for the real-world integration suite."""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner, Result

from sink.cli import cli

HERE = Path(__file__).resolve().parent
COMPOSE_FILE = HERE / "compose.yaml"
DEFAULT_UBUNTU = "26.04"
DB_NAME = "demo"
DB_USER = "sink"
# Exercise every quoting layer: the MySQL option file, the YAML loader, and
# the SQL initializer.  The SQL file represents the backslash as ``\\``.
DB_PASSWORD = r'p#ass "word" \ $ecret'  # noqa: S105 - test fixture
ROOT_PASSWORD = "rootsecret"  # noqa: S105 - test fixture
HOST_BINARIES = ("ssh", "ssh-keygen", "rsync", "git", "gzip")


def _skip_reason() -> str | None:
    """Return why the Docker sandbox cannot run, or ``None``."""
    if shutil.which("docker") is None:
        return "docker is not installed"
    compose = subprocess.run(
        ["docker", "compose", "version"],
        text=True,
        capture_output=True,
        check=False,
    )
    if compose.returncode:
        return "docker compose is not available"
    daemon = subprocess.run(
        ["docker", "info"],
        text=True,
        capture_output=True,
        check=False,
    )
    if daemon.returncode:
        return "Docker daemon is not available"
    missing = [name for name in HOST_BINARIES if shutil.which(name) is None]
    if missing:
        return f"missing integration binaries: {', '.join(missing)}"
    return None


def _run(
    argv: list[str],
    *,
    env: Mapping[str, str],
    input: str | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one local command with captured output."""
    return subprocess.run(
        argv,
        cwd=HERE,
        env=dict(env),
        input=input,
        text=True,
        capture_output=True,
        check=check,
    )


def _wait_for(
    predicate,
    *,
    timeout: float = 90.0,
    interval: float = 0.5,
    description: str,
) -> None:
    """Poll until *predicate* returns true or fail with a useful message."""
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            result = predicate()
        except OSError as error:
            last_error = str(error)
        else:
            if result:
                return
            last_error = str(result)
        time.sleep(interval)
    raise RuntimeError(f"Timed out waiting for {description}: {last_error}")


@dataclass(frozen=True)
class Sandbox:
    """A running Compose stack for one Ubuntu version."""

    compose: tuple[str, ...]
    env: Mapping[str, str]
    project: str
    ubuntu: str
    port: int
    key: Path
    home: Path
    bin_dir: Path

    def compose_run(
        self,
        *args: str,
        input: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run one ``docker compose`` command."""
        result = _run(
            [*self.compose, *args],
            env=self.env,
            input=input,
            check=False,
        )
        if check and result.returncode:
            raise RuntimeError(
                f"docker compose {' '.join(args)} failed "
                f"({result.returncode}):\n{result.stdout}{result.stderr}"
            )
        return result

    def copy_to(
        self,
        service: str,
        source: Path,
        destination: str,
    ) -> None:
        """Copy a local file into a Compose service."""
        result = self.compose_run(
            "cp",
            str(source),
            f"{service}:{destination}",
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"docker compose cp to {service}:{destination} failed "
                f"({result.returncode}):\n{result.stdout}{result.stderr}"
            )

    def exec(
        self,
        service: str,
        *args: str,
        input: str | None = None,
        user: str | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a command in one Compose service."""
        command = ["exec", "-T"]
        if user:
            command.extend(["-u", user])
        for key, value in (env or {}).items():
            command.extend(["-e", f"{key}={value}"])
        command.extend([service, *args])
        return self.compose_run(*command, input=input, check=check)

    def credentials_files(self) -> list[str]:
        """Return leftover remote credential files."""
        result = self.exec(
            "server",
            "sh",
            "-c",
            "ls -d /tmp/sink-mysql-* 2>/dev/null || true",
        )
        return [line for line in result.stdout.splitlines() if line.strip()]

    def db_query(self, sql: str) -> str:
        """Run a SQL statement as MySQL root."""
        return self.exec(
            "db",
            "mysql",
            "-uroot",
            DB_NAME,
            "-e",
            sql,
            env={"MYSQL_PWD": ROOT_PASSWORD},
        ).stdout

    def wait_for_db(self) -> None:
        """Wait until the MySQL service answers after a stop/start."""

        def ready() -> bool:
            result = _run(
                [
                    *self.compose,
                    "exec",
                    "-T",
                    "-e",
                    f"MYSQL_PWD={ROOT_PASSWORD}",
                    "db",
                    "mysqladmin",
                    "ping",
                    "-h",
                    "127.0.0.1",
                    "-uroot",
                ],
                env=self.env,
            )
            return result.returncode == 0

        _wait_for(ready, description="MySQL")


@dataclass(frozen=True)
class LiveProject:
    """A temporary Sink project pointed at the sandbox."""

    path: Path
    sandbox: Sandbox
    remote_root: str
    db_password: str = DB_PASSWORD

    def invoke(
        self,
        *args: str,
        input: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        """Invoke Sink in this project."""
        return CliRunner().invoke(
            cli,
            list(args),
            input=input,
            env=dict(env) if env is not None else None,
            catch_exceptions=True,
        )

    def run(
        self, *args: str, timeout: float = 120
    ) -> subprocess.CompletedProcess[str]:
        """Run the installed Sink in this project as a subprocess."""
        return subprocess.run(
            [sys.executable, "-m", "sink", *args],
            cwd=self.path,
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )

    def remote_path(self, name: str) -> str:
        """Return an absolute path under this project's remote root."""
        return f"{self.remote_root}/{name}"

    def remote_write(self, name: str, content: str) -> None:
        """Write a file on the server as the deploy user."""
        local = self.path / f".remote-{uuid.uuid4().hex}"
        local.write_text(content)
        try:
            self.sandbox.copy_to("server", local, self.remote_path(name))
        finally:
            local.unlink(missing_ok=True)
        self.sandbox.exec(
            "server",
            "chown",
            "deploy:deploy",
            self.remote_path(name),
        )

    def remote_read(self, name: str) -> str:
        """Read a file on the server as the deploy user."""
        return self.sandbox.exec(
            "server",
            "cat",
            self.remote_path(name),
            user="deploy",
        ).stdout

    def remote_exists(self, name: str) -> bool:
        """Return whether a remote path exists."""
        result = self.sandbox.exec(
            "server",
            "test",
            "-e",
            self.remote_path(name),
            user="deploy",
            check=False,
        )
        return result.returncode == 0


@pytest.fixture(scope="session")
def sandbox(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Sandbox]:
    """Start one Docker stack for the selected Ubuntu version."""
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)

    ubuntu = os.environ.get("SINK_TEST_UBUNTU", DEFAULT_UBUNTU)
    work = tmp_path_factory.mktemp(f"integration-{ubuntu.replace('.', '-')}")
    key = work / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
    )

    project = (
        f"sink-integration-{ubuntu.replace('.', '-')}-{uuid.uuid4().hex[:8]}"
    )
    compose = (
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "-p",
        project,
    )
    env = os.environ.copy()
    env["SINK_TEST_UBUNTU"] = ubuntu

    def down() -> None:
        _run([*compose, "down", "-v", "--remove-orphans"], env=env)

    try:
        build = (
            [] if os.environ.get("SINK_TEST_SKIP_BUILD") == "1" else ["--build"]
        )
        up = _run([*compose, "up", "-d", *build], env=env)
        if up.returncode:
            raise RuntimeError(
                f"docker compose up failed ({up.returncode}):\n"
                f"{up.stdout}{up.stderr}"
            )

        def port_number() -> int | None:
            result = _run([*compose, "port", "server", "22"], env=env)
            if result.returncode or not result.stdout.strip():
                return None
            return int(result.stdout.strip().rsplit(":", 1)[1])

        port_holder: list[int] = []

        def port_ready() -> bool:
            port = port_number()
            if port is None:
                return False
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    port_holder.append(port)
                    return True
            except OSError:
                return False

        _wait_for(port_ready, description="the SSH port")
        port = port_holder[0]

        def db_ready() -> bool:
            result = _run(
                [
                    *compose,
                    "exec",
                    "-T",
                    "-e",
                    f"MYSQL_PWD={ROOT_PASSWORD}",
                    "db",
                    "mysqladmin",
                    "ping",
                    "-h",
                    "127.0.0.1",
                    "-uroot",
                ],
                env=env,
            )
            return result.returncode == 0

        _wait_for(db_ready, description="MySQL")

        public_key = key.with_suffix(".pub")
        install = _run(
            [
                *compose,
                "exec",
                "-T",
                "server",
                "install",
                "-d",
                "-m",
                "700",
                "-o",
                "deploy",
                "-g",
                "deploy",
                "/home/deploy/.ssh",
            ],
            env=env,
        )
        if install.returncode:
            raise RuntimeError(
                f"could not create the SSH directory:\n"
                f"{install.stdout}{install.stderr}"
            )
        copy_key = _run(
            [
                *compose,
                "cp",
                str(public_key),
                "server:/home/deploy/.ssh/authorized_keys",
            ],
            env=env,
        )
        if copy_key.returncode:
            raise RuntimeError(
                f"could not copy the test key:\n"
                f"{copy_key.stdout}{copy_key.stderr}"
            )
        fix_key = _run(
            [
                *compose,
                "exec",
                "-T",
                "server",
                "sh",
                "-c",
                "chown deploy:deploy /home/deploy/.ssh/authorized_keys "
                "&& chmod 600 /home/deploy/.ssh/authorized_keys",
            ],
            env=env,
        )
        if fix_key.returncode:
            raise RuntimeError(
                f"could not set SSH key permissions:\n"
                f"{fix_key.stdout}{fix_key.stderr}"
            )

        ssh_probe = [
            "ssh",
            "-vvv",
            "-i",
            str(key),
            "-p",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "PreferredAuthentications=publickey",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=3",
            "deploy@127.0.0.1",
            "true",
        ]
        last_ssh: list[subprocess.CompletedProcess[str]] = []

        def ssh_ready() -> bool:
            result = subprocess.run(
                ssh_probe,
                text=True,
                capture_output=True,
                check=False,
            )
            last_ssh.append(result)
            return result.returncode == 0

        try:
            _wait_for(ssh_ready, description="SSH key authentication")
        except RuntimeError as error:
            logs = _run(
                [*compose, "logs", "--no-color", "server"],
                env=env,
            )
            inspect = _run(
                [
                    *compose,
                    "exec",
                    "-T",
                    "server",
                    "sh",
                    "-c",
                    "id deploy 2>&1; passwd -S deploy 2>&1; "
                    "ls -ld /home/deploy /home/deploy/.ssh "
                    "/home/deploy/.ssh/authorized_keys 2>&1; "
                    "wc -c /home/deploy/.ssh/authorized_keys 2>&1; "
                    "head -c 80 /home/deploy/.ssh/authorized_keys 2>&1; "
                    "echo; cat /proc/1/comm 2>&1; "
                    "/usr/sbin/sshd -T 2>&1 | head -n 20",
                ],
                env=env,
            )
            ssh_debug = last_ssh[-1] if last_ssh else None
            ssh_text = ""
            if ssh_debug is not None:
                ssh_text = ssh_debug.stderr[-4000:]
            raise RuntimeError(
                f"{error}\n"
                f"--- last ssh ---\n{ssh_text}\n"
                f"--- server logs ---\n{logs.stdout}{logs.stderr}\n"
                f"--- diagnostics ---\n{inspect.stdout}{inspect.stderr}"
            ) from error

        host_keys = _run(
            [
                *compose,
                "exec",
                "-T",
                "server",
                "sh",
                "-c",
                "cat /etc/ssh/ssh_host_*_key.pub",
            ],
            env=env,
        )
        if host_keys.returncode:
            raise RuntimeError(
                "could not read the server host keys:\n"
                f"{host_keys.stdout}{host_keys.stderr}"
            )
        known_lines = [
            f"[127.0.0.1]:{port} {line}"
            for line in host_keys.stdout.splitlines()
            if line.strip()
        ]
        if not any("ssh-ed25519" in line for line in known_lines):
            raise RuntimeError(
                "the server did not publish an ED25519 host key:\n"
                + "\n".join(known_lines)
            )

        home = work / "home"
        ssh_dir = home / ".ssh"
        ssh_dir.mkdir(parents=True)
        ssh_dir.chmod(0o700)
        known_hosts = ssh_dir / "known_hosts"
        known_hosts.write_text("\n".join(known_lines) + "\n")
        known_hosts.chmod(0o600)

        # OpenSSH resolves ~/.ssh/known_hosts from the passwd home directory,
        # not from $HOME.  An ssh wrapper keeps the test away from the real
        # user's known_hosts while preserving strict host-key checking.
        bin_dir = work / "bin"
        bin_dir.mkdir()
        real_ssh = shutil.which("ssh")
        if real_ssh is None:
            raise RuntimeError("ssh disappeared after the skip check")
        wrapper = bin_dir / "ssh"
        wrapper.write_text(
            "#!/bin/sh\n"
            f'known_hosts="${{SINK_TEST_KNOWN_HOSTS:-{known_hosts}}}"\n'
            f"exec {shlex.quote(real_ssh)} "
            '-o "UserKnownHostsFile=$known_hosts" '
            '-o GlobalKnownHostsFile=/dev/null "$@"\n'
        )
        wrapper.chmod(0o755)

        strict_env = os.environ.copy()
        strict_env["HOME"] = str(home)
        strict_env["SINK_TEST_KNOWN_HOSTS"] = str(known_hosts)
        strict_env["PATH"] = (
            f"{bin_dir}{os.pathsep}{strict_env.get('PATH', '')}"
        )
        strict = subprocess.run(
            [
                "ssh",
                "-vvv",
                "-i",
                str(key),
                "-p",
                str(port),
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=3",
                "deploy@127.0.0.1",
                "true",
            ],
            env=strict_env,
            text=True,
            capture_output=True,
            check=False,
        )
        if strict.returncode:
            raise RuntimeError(
                "strict known_hosts verification failed:\n"
                f"{strict.stderr[-4000:]}\n"
                f"--- known_hosts ---\n{known_hosts.read_text()}"
            )

        yield Sandbox(
            compose=compose,
            env=env,
            project=project,
            ubuntu=ubuntu,
            port=port,
            key=key,
            home=home,
            bin_dir=bin_dir,
        )
    finally:
        # CI sets SINK_TEST_KEEP=1 so a failed run can dump container logs
        # before the cleanup step removes the stack.
        if os.environ.get("SINK_TEST_KEEP") != "1":
            down()


@pytest.fixture
def live_project(tmp_path: Path, sandbox: Sandbox, monkeypatch):
    """Return a factory for temporary projects on the sandbox."""
    counter = 0

    def factory(
        *,
        warn: bool = False,
        server_name: str = "dev",
        mysql_username: str = DB_USER,
        mysql_password: str = DB_PASSWORD,
        databases: list[dict[str, object]] | None = None,
        extra_databases: list[dict[str, object]] | None = None,
        urls: list[dict[str, object]] | None = None,
        project_overrides: dict[str, object] | None = None,
        server_overrides: dict[str, object] | None = None,
        ssh_overrides: dict[str, object] | None = None,
        extra_servers: dict[str, dict[str, object]] | None = None,
    ) -> LiveProject:
        nonlocal counter
        counter += 1
        project_dir = tmp_path / f"case{counter}"
        project_root = project_dir / "project"
        (project_root / "sub").mkdir(parents=True)
        (project_root / "index.html").write_text("local index\n")
        (project_root / "sub" / "file.txt").write_text("local sub\n")
        (project_dir / "pulls").mkdir()
        (project_dir / "pulls").chmod(0o700)

        remote_root = f"/var/www/sink-{uuid.uuid4().hex[:12]}"
        sandbox.exec(
            "server",
            "install",
            "-d",
            "-o",
            "deploy",
            "-g",
            "deploy",
            remote_root,
        )

        project_document: dict[str, object] = {
            "name": "demo",
            "root": "project",
            "pulls_dir": "pulls",
            "exclude": [".git", ".env"],
        }
        project_document.update(project_overrides or {})

        if databases is None:
            databases = [
                {
                    "username": mysql_username,
                    "password": mysql_password,
                    "db": DB_NAME,
                    "hostname": "db",
                    "ssl_mode": "DISABLED",
                }
            ]
        databases = [*databases, *(extra_databases or [])]

        ssh_entry: dict[str, object] = {
            "name": "deploy",
            "username": "deploy",
            "server": "127.0.0.1",
            "key": str(sandbox.key),
            "port": sandbox.port,
        }
        ssh_entry.update(ssh_overrides or {})
        server_document: dict[str, object] = {
            "root": remote_root,
            "default": True,
            "warn": warn,
            "ssh": [ssh_entry],
            "mysql": databases,
            "urls": urls or [],
            "actions": {"hello": "echo hello"},
        }
        server_document.update(server_overrides or {})

        servers_document: dict[str, dict[str, object]] = {
            server_name: server_document
        }
        servers_document.update(extra_servers or {})
        document = {
            "project": project_document,
            "servers": servers_document,
        }
        (project_dir / "sink.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False)
        )
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("HOME", str(sandbox.home))
        monkeypatch.setenv(
            "SINK_TEST_KNOWN_HOSTS",
            str(sandbox.home / ".ssh" / "known_hosts"),
        )
        monkeypatch.setenv(
            "PATH",
            f"{sandbox.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        )
        monkeypatch.setenv("SINK_TEST_UBUNTU", sandbox.ubuntu)
        return LiveProject(
            path=project_dir,
            sandbox=sandbox,
            remote_root=remote_root,
            db_password=mysql_password,
        )

    return factory

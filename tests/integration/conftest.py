"""Docker-backed fixtures for the real-world integration suite."""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
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
DB_PASSWORD = "p#ass word"  # noqa: S105 - test fixture
ROOT_PASSWORD = "rootsecret"  # noqa: S105 - test fixture
HOST_BINARIES = ("ssh", "ssh-keygen", "ssh-keyscan", "rsync", "git", "gzip")


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
            "ls /tmp/sink-mysql-*.cnf 2>/dev/null || true",
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


@dataclass(frozen=True)
class LiveProject:
    """A temporary Sink project pointed at the sandbox."""

    path: Path
    sandbox: Sandbox
    remote_root: str

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

    def remote_path(self, name: str) -> str:
        """Return an absolute path under this project's remote root."""
        return f"{self.remote_root}/{name}"

    def remote_write(self, name: str, content: str) -> None:
        """Write a file on the server as the deploy user."""
        self.sandbox.exec(
            "server",
            "sh",
            "-c",
            f"cat > {shlex.quote(self.remote_path(name))}",
            input=content,
            user="deploy",
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
        up = _run([*compose, "up", "-d", "--build"], env=env)
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

        public_key = key.with_suffix(".pub").read_text()
        install = _run(
            [
                *compose,
                "exec",
                "-T",
                "server",
                "sh",
                "-c",
                "install -d -m 700 -o deploy -g deploy /home/deploy/.ssh "
                "&& cat > /home/deploy/.ssh/authorized_keys "
                "&& chown deploy:deploy /home/deploy/.ssh/authorized_keys "
                "&& chmod 600 /home/deploy/.ssh/authorized_keys",
            ],
            env=env,
            input=public_key,
        )
        if install.returncode:
            raise RuntimeError(
                f"could not install the test key:\n{install.stdout}{install.stderr}"
            )

        ssh_probe = [
            "ssh",
            "-i",
            str(key),
            "-p",
            str(port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=3",
            "deploy@127.0.0.1",
            "true",
        ]

        def ssh_ready() -> bool:
            result = subprocess.run(
                ssh_probe,
                text=True,
                capture_output=True,
                check=False,
            )
            return result.returncode == 0

        _wait_for(ssh_ready, description="SSH key authentication")

        scan = subprocess.run(
            ["ssh-keyscan", "-p", str(port), "127.0.0.1"],
            text=True,
            capture_output=True,
            check=True,
        )
        home = work / "home"
        ssh_dir = home / ".ssh"
        ssh_dir.mkdir(parents=True)
        ssh_dir.chmod(0o700)
        known_hosts = ssh_dir / "known_hosts"
        known_hosts.write_text(scan.stdout)
        known_hosts.chmod(0o600)

        yield Sandbox(
            compose=compose,
            env=env,
            project=project,
            ubuntu=ubuntu,
            port=port,
            key=key,
            home=home,
        )
    finally:
        down()


@pytest.fixture
def live_project(tmp_path: Path, sandbox: Sandbox, monkeypatch):
    """Return a factory for temporary projects on the sandbox."""
    counter = 0

    def factory(
        *,
        warn: bool = False,
        mysql_password: str = DB_PASSWORD,
        urls: list[dict[str, object]] | None = None,
    ) -> LiveProject:
        nonlocal counter
        counter += 1
        project_dir = tmp_path / f"case{counter}"
        project_root = project_dir / "project"
        (project_root / "sub").mkdir(parents=True)
        (project_root / "index.html").write_text("local index\n")
        (project_root / "sub" / "file.txt").write_text("local sub\n")
        (project_dir / "pulls").mkdir()

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

        document = {
            "project": {
                "name": "demo",
                "root": "project",
                "pulls_dir": "pulls",
                "exclude": [".git", ".env"],
            },
            "servers": {
                "dev": {
                    "root": remote_root,
                    "default": True,
                    "warn": warn,
                    "ssh": [
                        {
                            "name": "deploy",
                            "username": "deploy",
                            "server": "127.0.0.1",
                            "key": str(sandbox.key),
                            "port": sandbox.port,
                        }
                    ],
                    "mysql": [
                        {
                            "username": DB_USER,
                            "password": mysql_password,
                            "db": DB_NAME,
                            "hostname": "db",
                        }
                    ],
                    "urls": urls or [],
                    "actions": {"hello": "echo hello"},
                }
            },
        }
        (project_dir / "sink.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False)
        )
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("HOME", str(sandbox.home))
        monkeypatch.setenv("SINK_TEST_UBUNTU", sandbox.ubuntu)
        return LiveProject(
            path=project_dir,
            sandbox=sandbox,
            remote_root=remote_root,
        )

    return factory

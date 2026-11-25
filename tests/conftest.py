from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner, Result

from sink.sink import sink


@dataclass(frozen=True)
class ProjectFixture:
    path: Path
    stub_log: Path
    bin_dir: Path

    def invoke(
        self,
        *args: str,
        input: str | None = None,
        env: dict[str, str] | None = None,
    ) -> Result:
        return CliRunner().invoke(
            sink,
            list(args),
            input=input,
            env=env,
            catch_exceptions=True,
        )

    def clear_log(self) -> None:
        self.stub_log.write_text("")


# Every test starts outside a project and outside the real home directory.
# Stage 5 replaces the global singleton; until then the reset below keeps the
# pre-modernization suite deterministic.
@pytest.fixture(autouse=True)
def isolated_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    for name in ("config", "data", "cache", "state"):
        (tmp_path / f".{name}").mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / ".cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / ".state"))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.delenv("BASH_COMPLETION_USER_DIR", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("SINK_DB_PULL", raising=False)
    monkeypatch.chdir(cwd)


def _stub_body(name: str) -> str:
    key = name.upper().replace("-", "_")
    return f"""#!/usr/bin/env bash
lock="$STUB_LOG.lock"
while ! mkdir "$lock" 2>/dev/null; do
  sleep 0.001 2>/dev/null || sleep 1
done
trap 'rmdir "$lock" 2>/dev/null' EXIT
{{
  printf 'CMD %s\\n' "{name}"
  for arg in "$@"; do
    printf 'ARG %s\\n' "$arg"
  done
  printf 'END\\n'
}} >> "$STUB_LOG"
if [ -n "${{STUB_OUT_{key}:-}}" ]; then
  printf '%s' "$STUB_OUT_{key}"
fi
if [ -n "${{STUB_ERR_{key}:-}}" ]; then
  printf '%s' "$STUB_ERR_{key}" >&2
fi
exit "${{STUB_EXIT_{key}:-0}}"
"""


STUB_NAMES = (
    "rsync",
    "ssh",
    "scp",
    "mysql",
    "mysqldump",
    "git",
    "less",
    "pv",
    "lando",
    "ddev",
)


@pytest.fixture
def project_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    counter = 0

    def factory(
        *,
        default: bool = True,
        automatic: bool = True,
        warn: bool = False,
        server_type: str | None = None,
        urls: list[dict[str, Any]] | None = None,
        project_actions: dict[str, str] | None = None,
        project_overrides: dict[str, Any] | None = None,
        server_overrides: dict[str, Any] | None = None,
        extra_servers: dict[str, dict[str, Any]] | None = None,
    ) -> ProjectFixture:
        nonlocal counter
        counter += 1
        root = tmp_path / f"case{counter}"
        (root / "project").mkdir(parents=True)
        (root / "project" / "index.html").write_text("<h1>demo</h1>\n")
        (root / "project" / "sub").mkdir()
        (root / "project" / "sub" / "file.txt").write_text("hello\n")
        (root / "pulls").mkdir()
        (root / "outside.txt").write_text("outside\n")
        (root / "id_rsa").write_text("dummy key\n")

        bin_dir = root / "bin"
        bin_dir.mkdir()
        stub_log = root / "stub.log"
        stub_log.write_text("")
        for name in STUB_NAMES:
            executable = bin_dir / name
            executable.write_text(_stub_body(name))
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

        server: dict[str, Any] = {
            "root": "/var/www/demo",
            "deploy_root": "/var/www/deploys",
            "default": default,
            "automatic": automatic,
            "warn": warn,
            "group": "",
            "user": "",
            "exclude": ["storage/logs"],
            "ssh": [
                {
                    "name": "deploy",
                    "username": "deploy",
                    "server": "example.com",
                    "key": "id_rsa",
                    "port": 2222,
                    "password": "",
                }
            ],
            "mysql": [
                {
                    "username": "dbuser",
                    "password": "secret",
                    "db": "demo",
                    "hostname": "localhost",
                    "skip_secure_auth": "",
                }
            ],
            "urls": urls or [],
            "actions": {"files": "ls -al"},
            "hosting": {},
            "control_panel": {},
        }
        server.update(server_overrides or {})
        if server_type is not None:
            server["type"] = server_type

        project: dict[str, Any] = {
            "name": "demo",
            "root": "project",
            "pulls_dir": "pulls",
            "exclude": [".git", ".env"],
            "difftool": "meld {local} {remote}",
        }
        project.update(project_overrides or {})
        if project_actions is not None:
            project["actions"] = project_actions

        servers = {"dev": server}
        servers.update(extra_servers or {})
        document = {"project": project, "servers": servers}
        (root / "sink.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False)
        )

        monkeypatch.chdir(root)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("STUB_LOG", str(stub_log))
        monkeypatch.setenv("NO_COLOR", "1")
        return ProjectFixture(path=root, stub_log=stub_log, bin_dir=bin_dir)

    return factory

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from sink.config import config as global_config
from sink.sink import sink


@dataclass(frozen=True)
class ProjectFixture:
    path: Path
    stub_log: Path

    def invoke(self, *args: str):
        return CliRunner().invoke(sink, list(args), catch_exceptions=True)


# Stage 0 keeps the existing global config alive.  Reset it between tests so
# the pre-modernization suite is deterministic; Stage 5 deletes the singleton.
@pytest.fixture(autouse=True)
def reset_global_config():
    global_config.config_file = "sink.yaml"
    global_config.data = {}
    global_config.o = None
    global_config.project_root = None
    global_config.suppress_commands = False
    yield


STUBS: dict[str, str] = {
    "rsync": """#!/usr/bin/env bash
printf 'rsync %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
    "ssh": """#!/usr/bin/env bash
printf 'ssh %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
    "scp": """#!/usr/bin/env bash
printf 'scp %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
    "mysql": """#!/usr/bin/env bash
printf 'mysql %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
    "mysqldump": """#!/usr/bin/env bash
printf 'mysqldump %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
    "git": """#!/usr/bin/env bash
printf 'git %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
    "pv": """#!/usr/bin/env bash
printf 'pv %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
    "lando": """#!/usr/bin/env bash
printf 'lando %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
    "ddev": """#!/usr/bin/env bash
printf 'ddev %s\\n' "$*" >> "$STUB_LOG"
exit 0
""",
}


@pytest.fixture
def project_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    counter = 0

    def factory(
        *,
        default: bool = True,
        automatic: bool = True,
        project_actions: dict[str, str] | None = None,
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
        for name, body in STUBS.items():
            executable = bin_dir / name
            executable.write_text(body)
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

        server: dict[str, Any] = {
            "root": "/var/www/demo",
            "deploy_root": "/var/www/deploys",
            "default": default,
            "automatic": automatic,
            "warn": False,
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
            "urls": [],
            "actions": {"files": "ls -al"},
            "hosting": {},
            "control_panel": {},
        }
        project: dict[str, Any] = {
            "name": "demo",
            "root": "project",
            "pulls_dir": "pulls",
            "exclude": [".git", ".env"],
            "difftool": "meld {local} {remote}",
        }
        if project_actions is not None:
            project["actions"] = project_actions

        document = {"project": project, "servers": {"dev": server}}
        (root / "sink.yaml").write_text(yaml.safe_dump(document, sort_keys=False))

        monkeypatch.chdir(root)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("STUB_LOG", str(stub_log))
        monkeypatch.setenv("NO_COLOR", "1")
        return ProjectFixture(path=root, stub_log=stub_log)

    return factory

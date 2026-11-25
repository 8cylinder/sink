"""Feature objects take Project/Server values, not the config container."""

from __future__ import annotations

import inspect
from pathlib import Path

from sink.actions import Actions
from sink.config.models import (
    DatabaseConfig,
    Project,
    Server,
    SSHConfig,
)
from sink.db import DB
from sink.rsync import Transfer
from sink.ssh import SSH


def sample() -> tuple[Project, Server]:
    project = Project(name="demo", root=Path("/srv/project"))
    server = Server(
        name="dev",
        root=Path("/var/www/demo"),
        ssh=(SSHConfig(username="deploy", server="example.com"),),
        databases=(DatabaseConfig(db="demo"),),
    )
    return project, server


def test_transfer_constructor_takes_project_and_server() -> None:
    project, server = sample()
    parameters = list(inspect.signature(Transfer).parameters)

    assert parameters[:2] == ["project", "server"]
    assert Transfer(project, server).server is server


def test_db_constructor_takes_project_and_server() -> None:
    project, server = sample()
    parameters = list(inspect.signature(DB).parameters)

    assert parameters[:2] == ["project", "server"]
    db = DB(project, server)
    assert db.project is project
    assert db.server is server


def test_ssh_constructor_takes_server() -> None:
    _, server = sample()
    parameters = list(inspect.signature(SSH).parameters)

    assert parameters[:1] == ["server"]
    assert SSH(server).server is server


def test_actions_constructor_takes_project_and_optional_server() -> None:
    project, server = sample()

    local = Actions(project, None, real=False)
    remote = Actions(project, server, real=True)

    assert local.servername == "local"
    assert remote.servername == "dev"

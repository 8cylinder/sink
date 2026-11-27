"""SEC-10: a configured but missing SSH key never falls back implicitly."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import combined, commands_named

from sink.config.loader import load
from sink.config.models import Server, SSHConfig
from sink.errors import CommandError
from sink.ssh import SSH


def _missing_key_ssh() -> list[dict[str, object]]:
    """Return an SSH entry that names a key that does not exist."""
    return [
        {
            "name": "deploy",
            "username": "deploy",
            "server": "example.com",
            "key": "missing_key",
            "port": 2222,
            "password": "",
        }
    ]


def _agent_ssh() -> list[dict[str, object]]:
    """Return an SSH entry that explicitly selects the agent."""
    return [
        {
            "name": "deploy",
            "username": "deploy",
            "server": "example.com",
            "key": "agent",
            "port": 2222,
            "password": "",
        }
    ]


def test_missing_key_warns_in_dry_run(project_factory) -> None:
    project = project_factory(server_overrides={"ssh": _missing_key_ssh()})

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert "ssh key does not exist: missing_key" in combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert rsync
    rsh = rsync[0].args[rsync[0].args.index("--rsh") + 1]
    assert "-i" not in rsh
    assert "IdentitiesOnly=yes" not in rsh


def test_missing_key_fails_in_real_mode(project_factory) -> None:
    project = project_factory(server_overrides={"ssh": _missing_key_ssh()})

    result = project.invoke("file", "put", "dev", "--real")

    assert result.exit_code != 0, combined(result)
    assert "ssh key does not exist: missing_key" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_missing_key_blocks_check(project_factory) -> None:
    project = project_factory(server_overrides={"ssh": _missing_key_ssh()})

    result = project.invoke("check", "dev")

    assert result.exit_code != 0, combined(result)
    assert "ssh key does not exist: missing_key" in combined(result)
    assert project.stub_log.read_text() == ""


def test_missing_key_blocks_a_remote_action(project_factory) -> None:
    project = project_factory(server_overrides={"ssh": _missing_key_ssh()})

    result = project.invoke("action", "dev", "files", "--real")

    assert result.exit_code != 0, combined(result)
    assert "ssh key does not exist: missing_key" in combined(result)
    assert project.stub_log.read_text() == ""


def test_agent_key_is_an_explicit_fallback(project_factory) -> None:
    project = project_factory(server_overrides={"ssh": _agent_ssh()})

    result = project.invoke("file", "put", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert rsync
    rsh = rsync[0].args[rsync[0].args.index("--rsh") + 1]
    assert "-i" not in rsh
    assert "IdentitiesOnly=yes" not in rsh


def test_agent_key_loads_without_an_error(project_factory) -> None:
    project = project_factory(server_overrides={"ssh": _agent_ssh()})

    config = load(project.path / "sink.yaml")

    ssh = config.server().ssh[0]
    assert ssh.key is None
    assert ssh.key_error is None


def test_scp_blocks_a_missing_key(tmp_path: Path) -> None:
    server = Server(
        name="dev",
        ssh=(
            SSHConfig(
                username="deploy",
                server="example.com",
                key_error="ssh key does not exist",
            ),
        ),
    )
    ssh = SSH(server, dry_run=False)

    with pytest.raises(CommandError):
        ssh.scp_put(tmp_path / "file")

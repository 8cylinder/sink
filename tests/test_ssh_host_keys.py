"""SEC-07: non-interactive SSH paths enforce host-key and identity policy."""

from __future__ import annotations

from types import SimpleNamespace

from helpers import combined, commands_named

from sink.config.loader import load
from sink.shell import scp_argv


def _ssh_config(known_hosts: str) -> list[dict[str, object]]:
    """Return a fixture SSH entry with a dedicated known-hosts file."""
    return [
        {
            "name": "deploy",
            "username": "deploy",
            "server": "example.com",
            "key": "id_rsa",
            "known_hosts": known_hosts,
            "port": 2222,
            "password": "",
        }
    ]


def test_rsync_rsh_enforces_host_key_policy(project_factory) -> None:
    project = project_factory(
        server_overrides={"ssh": _ssh_config("known_hosts_sink")}
    )
    (project.path / "known_hosts_sink").write_text("")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    args = rsync[0].args
    rsh = args[args.index("--rsh") + 1]
    assert "StrictHostKeyChecking=yes" in rsh
    assert "BatchMode=yes" in rsh
    assert "IdentitiesOnly=yes" in rsh
    assert f"-i {project.path / 'id_rsa'}" in rsh
    assert f"UserKnownHostsFile={project.path / 'known_hosts_sink'}" in rsh
    assert "GlobalKnownHostsFile=/dev/null" in rsh
    assert "ConnectTimeout=10" in rsh


def test_scp_enforces_host_key_policy() -> None:
    ssh = SimpleNamespace(
        username="deploy",
        server="example.com",
        port=2222,
        key="/keys/id",
        known_hosts="/keys/known_hosts",
    )

    argv = scp_argv(ssh, "local", "remote")

    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "IdentitiesOnly=yes" in argv
    assert "UserKnownHostsFile=/keys/known_hosts" in argv
    assert "GlobalKnownHostsFile=/dev/null" in argv


def test_interactive_ssh_enforces_host_keys_without_batch_mode(
    project_factory,
) -> None:
    project = project_factory()

    result = project.invoke("ssh", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    ssh = commands_named(project.stub_log, "ssh")[0]
    assert "StrictHostKeyChecking=yes" in ssh.args
    assert "IdentitiesOnly=yes" in ssh.args
    assert "BatchMode=yes" not in ssh.args


def test_remote_action_enforces_identity_and_host_keys(project_factory) -> None:
    project = project_factory()

    result = project.invoke("action", "dev", "files", "--real")

    assert result.exit_code == 0, combined(result)
    ssh = commands_named(project.stub_log, "ssh")[0]
    assert "StrictHostKeyChecking=yes" in ssh.args
    assert "BatchMode=yes" in ssh.args
    assert "IdentitiesOnly=yes" in ssh.args


def test_known_hosts_path_is_resolved(project_factory) -> None:
    project = project_factory(
        server_overrides={"ssh": _ssh_config("known_hosts_sink")}
    )
    (project.path / "known_hosts_sink").write_text("")

    config = load(project.path / "sink.yaml")

    assert config.server().ssh[0].known_hosts == str(
        (project.path / "known_hosts_sink").resolve()
    )

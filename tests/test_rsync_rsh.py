"""SEC-14: the rsync --rsh value round-trips safely."""

from __future__ import annotations

import shlex
from pathlib import Path

from sink.config.models import Action, Project, Server, SSHConfig
from sink.rsync import Transfer


def _rsh(tmp_path: Path, key: str, known_hosts: str | None = None) -> str:
    """Return the built --rsh value for one SSH config."""
    project = Project(name="demo", root=tmp_path)
    server = Server(
        name="dev",
        root=Path("/remote"),
        ssh=(
            SSHConfig(
                username="deploy",
                server="example.com",
                key=key,
                known_hosts=known_hosts,
            ),
        ),
    )
    command = Transfer(project, server)._rsync_command(
        tmp_path / "file.txt",
        Path("/remote/file.txt"),
        Action.PUT,
        server,
    )
    args = command.argv
    return args[args.index("--rsh") + 1]


def test_rsh_round_trips_a_key_path_with_spaces(tmp_path: Path) -> None:
    key = str(tmp_path / "key with space")
    rsh = _rsh(tmp_path, key)

    parsed = shlex.split(rsh)
    assert parsed[parsed.index("-i") + 1] == key


def test_rsh_round_trips_shell_metacharacters_in_the_key_path(
    tmp_path: Path,
) -> None:
    key = str(tmp_path / "key;$(touch pwned)")
    rsh = _rsh(tmp_path, key)

    parsed = shlex.split(rsh)
    assert parsed[parsed.index("-i") + 1] == key
    assert "--" not in parsed
    assert "touch" not in parsed


def test_rsh_treats_a_leading_dash_as_a_key_path(tmp_path: Path) -> None:
    key = str(tmp_path / "-oProxyCommand=evil")
    rsh = _rsh(tmp_path, key)

    parsed = shlex.split(rsh)
    assert parsed[parsed.index("-i") + 1] == key


def test_rsh_round_trips_a_known_hosts_path_with_spaces(
    tmp_path: Path,
) -> None:
    key = str(tmp_path / "key")
    known_hosts = str(tmp_path / "known hosts")
    rsh = _rsh(tmp_path, key, known_hosts)

    parsed = shlex.split(rsh)
    assert f"UserKnownHostsFile={known_hosts}" in parsed

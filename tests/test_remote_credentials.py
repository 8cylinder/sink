"""SEC-15: remote credentials live in a private, non-followed directory."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from sink.credentials import RemoteCredentials
from sink.errors import CommandError


def _credentials(**overrides: object) -> RemoteCredentials:
    """Return remote credentials for a disposable SSH config."""
    values: dict[str, object] = {
        "ssh": SimpleNamespace(),
        "password": "secret",
    }
    values.update(overrides)
    return RemoteCredentials(**values)  # ty: ignore[invalid-argument-type]


def test_remote_credentials_use_a_private_directory() -> None:
    credentials = _credentials()

    path = Path(credentials.path)
    assert path.name == "client.cnf"
    assert path.parent.name.startswith("sink-mysql-")
    assert path.parent.parent == Path(tempfile.gettempdir()).resolve()


def test_stage_command_creates_a_private_file_without_following_links() -> None:
    credentials = _credentials()
    stage = credentials.stage_command().fragment

    assert "umask 077" in stage
    assert "mkdir -m 700" in stage
    assert "set -C" in stage
    assert "cat >" in stage
    assert "client.cnf" in stage


def test_cleanup_and_trap_remove_the_private_directory() -> None:
    credentials = _credentials()
    directory = str(Path(credentials.path).parent)

    assert directory in credentials.cleanup_command().fragment
    assert "rm -rf" in credentials.cleanup_command().fragment
    guarded = credentials.trap_command("mysqldump demo")
    assert directory in guarded
    assert "rm -rf" in guarded


@pytest.mark.parametrize("value", ["a\nb", "a\rb", "a\x00b"])
def test_option_values_reject_control_characters(value: str) -> None:
    credentials = _credentials(password=value)

    with pytest.raises(CommandError, match="NUL, CR, or LF"):
        _ = credentials.content


def test_option_values_reject_control_characters_in_other_fields() -> None:
    credentials = _credentials(user="deploy\npassword=evil")

    with pytest.raises(CommandError, match="NUL, CR, or LF"):
        _ = credentials.content

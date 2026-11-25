"""Static bash completion generation and installation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from sink.cli import cli
from sink.completions import (
    completion_path,
    generate_bash,
    install_bash_completion,
)


def test_destination_uses_first_bash_completion_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    monkeypatch.setenv("BASH_COMPLETION_USER_DIR", f":{first}:{second}")

    path = completion_path("sink")

    assert path.parent.parent.parent == first
    assert path.name == "sink.bash"


def test_destination_falls_back_to_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BASH_COMPLETION_USER_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    path = completion_path("sink")

    assert path == (
        tmp_path / "xdg" / "bash-completion" / "completions" / "sink.bash"
    )


def test_installer_writes_a_script(tmp_path: Path) -> None:
    script = tmp_path / "bash-completion" / "completions" / "sink.bash"
    old = os.environ.get("BASH_COMPLETION_USER_DIR")
    os.environ["BASH_COMPLETION_USER_DIR"] = str(tmp_path)
    try:
        installed = install_bash_completion(cli, "sink", "0.3.0")
    finally:
        if old is None:
            os.environ.pop("BASH_COMPLETION_USER_DIR", None)
        else:
            os.environ["BASH_COMPLETION_USER_DIR"] = old

    assert installed == script
    assert installed.stat().st_mode & 0o777 == 0o644
    text = installed.read_text()
    assert "python" not in text.lower()
    assert "$(sink" not in text
    assert "_sink_complete" in text


def test_generated_script_is_valid_bash(tmp_path: Path) -> None:
    path = tmp_path / "sink.bash"
    path.write_text(generate_bash(cli, "sink", "0.3.0"))

    result = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_completion_suggests_commands_and_options(tmp_path: Path) -> None:
    path = tmp_path / "sink.bash"
    path.write_text(generate_bash(cli, "sink", "0.3.0"))
    command = f"""
    source {path}
    COMP_WORDS=(sink --col)
    COMP_CWORD=1
    _sink_complete
    printf '%s\\n' "${{COMPREPLY[@]}}"
    """
    result = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--color" in result.stdout.splitlines()
    assert "dev" not in result.stdout.splitlines()

    command = f"""
    source {path}
    COMP_WORDS=(sink --color "")
    COMP_CWORD=2
    _sink_complete
    printf '%s\\n' "${{COMPREPLY[@]}}"
    """
    result = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert {"auto", "always", "never"} <= set(result.stdout.splitlines())


def test_completion_does_not_offer_parent_options_after_subcommand(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sink.bash"
    path.write_text(generate_bash(cli, "sink", "0.3.0"))
    command = f"""
    source {path}
    COMP_WORDS=(sink db --f)
    COMP_CWORD=2
    _sink_complete
    printf '%s\\n' "${{COMPREPLY[@]}}"
    """
    result = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        check=False,
    )

    assert "--filename-only" in result.stdout.splitlines()
    assert "--color" not in result.stdout.splitlines()

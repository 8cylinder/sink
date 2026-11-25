"""Root-level options, entry points, and project discovery."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest
from click.testing import CliRunner
from helpers import combined

from sink.sink import sink

REPO = Path(__file__).resolve().parents[1]


def project_version() -> str:
    with (REPO / "pyproject.toml").open("rb") as file:
        value = tomllib.load(file)["project"]["version"]
    assert isinstance(value, str)
    return value


def test_version_matches_pyproject() -> None:
    result = CliRunner().invoke(sink, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"sink, version {project_version()}"
    assert version("sink") == project_version()


def test_python_dash_m_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "sink", "-h"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Usage: sink" in result.stdout
    assert "\x1b[" not in result.stdout


def test_vm_group_is_removed() -> None:
    result = CliRunner().invoke(sink, ["vm"])

    assert result.exit_code != 0
    assert "No such command 'vm'" in combined(result)


def test_not_in_a_project() -> None:
    result = CliRunner().invoke(sink, ["info"])

    assert result.exit_code == 1
    assert "You are not in a project" in combined(result)


def test_home_and_xdg_dirs_are_isolated(tmp_path: Path) -> None:
    assert Path.home() == tmp_path / "home"
    assert os.environ["XDG_CONFIG_HOME"] == str(tmp_path / ".config")
    assert os.environ["XDG_DATA_HOME"] == str(tmp_path / ".data")
    assert os.environ["XDG_CACHE_HOME"] == str(tmp_path / ".cache")


def test_no_arguments_shows_help() -> None:
    result = CliRunner().invoke(sink, [])

    assert result.exit_code == 2
    assert "Usage: sink" in result.output


@pytest.mark.xfail(
    strict=True, reason="Stage 6: --config prints the discovered path"
)
def test_config_prints_the_discovered_path(project_factory) -> None:
    project = project_factory()
    result = project.invoke("--config")

    assert result.exit_code == 0, combined(result)
    printed = Path(result.output.strip())
    assert printed.is_absolute()
    assert printed == (project.path / "sink.yaml")
    assert "\x1b[" not in result.output


@pytest.mark.xfail(
    strict=True, reason="Stage 6: --completions installs a static script"
)
def test_completions_writes_a_static_script(project_factory) -> None:
    project = project_factory()
    result = project.invoke("--completions")

    assert result.exit_code == 0, combined(result)
    printed = Path(result.output.strip())
    assert printed.is_absolute()
    assert printed.name == "sink.bash"
    assert printed.is_file()
    assert "\x1b[" not in result.output


@pytest.mark.xfail(
    strict=True, reason="Stage 6: root --color option is not implemented"
)
def test_color_never_is_accepted_and_plain(project_factory) -> None:
    project = project_factory()
    result = project.invoke("--color", "never", "--help")

    assert result.exit_code == 0, combined(result)
    assert "Usage: sink" in result.output
    assert "\x1b[" not in result.output


@pytest.mark.xfail(
    strict=True,
    reason="Stage 6: root -q/--quiet count option is not implemented",
)
def test_quiet_hides_only_the_rendered_command(project_factory) -> None:
    project = project_factory()
    result = project.invoke("-q", "file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert "+ rsync" not in result.output
    assert "Success (DRY RUN)" in result.output


@pytest.mark.xfail(
    strict=True, reason="Stage 6: root -qq silent mode is not implemented"
)
def test_double_quiet_suppresses_everything(project_factory) -> None:
    project = project_factory()
    result = project.invoke("-qq", "file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert result.output == ""
    assert result.stderr == ""


@pytest.mark.xfail(
    strict=True, reason="Stage 6: root --silent alias is not implemented"
)
def test_silent_alias_still_exists(project_factory) -> None:
    project = project_factory()
    result = project.invoke("--silent", "file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert result.output == ""
    assert result.stderr == ""


def test_suppress_commands_hides_only_the_render(project_factory) -> None:
    project = project_factory()

    result = project.invoke("-s", "file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert "+ rsync" not in result.output
    assert "Success (DRY RUN)" in result.output


def test_suppress_commands_is_documented() -> None:
    result = CliRunner().invoke(sink, ["--help"])

    assert "--suppress-commands" in result.output
    assert "-s" in result.output

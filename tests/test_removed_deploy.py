"""The deploy workflow has been removed from Sink."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from click.testing import CliRunner
from helpers import combined

from sink.cli import cli

ROOT = Path(__file__).resolve().parents[1]


def test_deploy_command_is_gone() -> None:
    result = CliRunner().invoke(cli, ["deploy"])

    assert result.exit_code != 0
    assert "No such command 'deploy'" in combined(result)


def test_deploy_modules_are_gone() -> None:
    assert importlib.util.find_spec("sink.deploy") is None
    assert not (ROOT / "src/sink/cli/deploy.py").exists()


def test_coolname_dependency_is_gone() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert "coolname" not in pyproject

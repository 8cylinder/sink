"""The deploy workflow has been removed from Sink."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from click.testing import CliRunner

from sink.cli import cli

from helpers import combined

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.xfail(strict=True, reason="Deploy workflow removal is in progress")
def test_deploy_command_is_gone() -> None:
    result = CliRunner().invoke(cli, ["deploy"])

    assert result.exit_code != 0
    assert "No such command 'deploy'" in combined(result)


@pytest.mark.xfail(strict=True, reason="Deploy workflow removal is in progress")
def test_deploy_modules_are_gone() -> None:
    assert importlib.util.find_spec("sink.deploy") is None
    assert not (ROOT / "src/sink/cli/deploy.py").exists()


@pytest.mark.xfail(strict=True, reason="Deploy workflow removal is in progress")
def test_coolname_dependency_is_gone() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert "coolname" not in pyproject

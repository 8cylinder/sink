"""SEC-18: output, git, pager, PATH, and YAML hardening."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

import pytest
from helpers import combined, unwrap

from sink.cli import info as info_module
from sink.config.loader import load
from sink.errors import ConfigError
from sink.rsync import _safe_pager_env
from sink.ui import ui


def test_status_escapes_rich_markup(monkeypatch) -> None:
    seen: list[str] = []

    class FakeStatus:
        """Minimal context manager for the status spinner."""

        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    def fake_status(message: str) -> FakeStatus:
        seen.append(message)
        return FakeStatus()

    monkeypatch.setattr(ui.console, "status", fake_status)

    with ui.status("Checking [red]literal"):
        pass

    assert seen == [r"Checking \[red]literal"]


def test_git_diff_disables_external_diff_and_textconv(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    git_line = next(
        line
        for line in unwrap(combined(result)).splitlines()
        if line.startswith("+ git ")
    )
    args = shlex.split(git_line[2:])
    assert "--no-ext-diff" in args
    assert "--no-textconv" in args


def test_safe_pager_env_removes_lessopen(monkeypatch) -> None:
    monkeypatch.setenv("LESSOPEN", "|evil %s")
    monkeypatch.setenv("LESSCLOSE", "|evil %s %s")

    env = _safe_pager_env()

    assert "LESSOPEN" not in env
    assert "LESSCLOSE" not in env


def test_recursive_yaml_alias_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sink.yaml"
    path.write_text("a: &a [*a]\n")

    with pytest.raises(ConfigError, match="recursive YAML alias"):
        load(path)


def test_path_with_current_directory_warns(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    monkeypatch.setenv("PATH", f".{os.pathsep}{os.environ.get('PATH', '')}")

    result = project.invoke("misc", "api", "project", "name")

    assert result.exit_code == 0, combined(result)
    assert "PATH contains" in combined(result)


def test_info_edit_warns_about_the_environment_editor(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    monkeypatch.setenv("EDITOR", "vi")
    monkeypatch.setattr(info_module.click, "edit", lambda **_kwargs: None)

    result = project.invoke("info", "--edit")

    assert result.exit_code == 0, combined(result)
    assert "Using editor from environment" in combined(result)

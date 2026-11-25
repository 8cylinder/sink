"""Color, redaction, machine output, and editor behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from helpers import combined

from sink.cli import cli
from sink.cli import info as info_module


def test_color_always_emits_ansi(project_factory) -> None:
    project = project_factory()

    result = project.invoke("--color", "always", "file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert "\x1b[" in result.output


def test_color_never_is_plain(project_factory) -> None:
    project = project_factory()

    result = project.invoke("--color", "never", "file", "put", "dev")

    assert "\x1b[" not in result.output


def test_double_quiet_preserves_failure_exit(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "-qq",
        "file",
        "put",
        "dev",
        "--real",
        env={"STUB_EXIT_RSYNC": "1"},
    )

    assert result.exit_code == 1
    assert result.output == ""
    assert result.stderr == ""


def test_misc_api_is_json_only(project_factory) -> None:
    project = project_factory()

    result = project.invoke("misc", "api", "-n", "project", "name")

    assert result.exit_code != 0


def test_misc_api_can_show_secrets(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "misc",
        "api",
        "servers",
        "dev",
        "mysql",
        "0",
        "password",
        "--show-secrets",
    )

    assert result.exit_code == 0, combined(result)
    assert result.output.strip() == '"secret"'


def test_misc_api_redacts_by_default(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "misc", "api", "servers", "dev", "mysql", "0", "password"
    )

    assert result.exit_code == 0, combined(result)
    assert result.output.strip() == '"********"'


def test_misc_settings_can_show_secrets(project_factory) -> None:
    project = project_factory()

    result = project.invoke("misc", "settings", "mysql", "--show-secrets")

    assert result.exit_code == 0, combined(result)
    assert "secret" in combined(result)


def test_misc_settings_redacts_by_default(project_factory) -> None:
    project = project_factory()

    result = project.invoke("misc", "settings", "mysql")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)


def test_misc_pack_prints_a_plain_command(project_factory) -> None:
    project = project_factory()

    result = project.invoke("misc", "pack")

    assert result.exit_code == 0, combined(result)
    assert "git ls-files -mz | xargs -0 tar -czvf" in result.output
    assert "changed-demo-" in result.output
    assert "\x1b[" not in result.output


def test_info_edit_passes_a_string_path(
    project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_factory()
    seen: list[str] = []

    def fake_edit(filename):
        seen.append(filename)
        return None

    monkeypatch.setattr(info_module.click, "edit", fake_edit)

    result = project.invoke("info", "--edit")

    assert result.exit_code == 0, combined(result)
    assert seen == [str(project.path / "sink.yaml")]


def test_config_outside_a_project() -> None:
    result = CliRunner().invoke(cli, ["--config"])

    assert result.exit_code != 0
    assert "You are not in a project" in combined(result)


def test_completions_outside_a_project(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        ["--completions"],
        env={
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "HOME": str(tmp_path / "home"),
        },
    )

    assert result.exit_code == 0, combined(result)
    assert Path(result.stdout.strip()).is_file()

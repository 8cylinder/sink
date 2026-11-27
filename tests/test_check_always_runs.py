"""Check probes run without a dry-run/--real switch."""

from __future__ import annotations

import json

from click.testing import CliRunner
from helpers import combined

from sink.cli import cli


def test_check_runs_probes_by_default(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() != ""


def test_check_fails_when_a_probe_fails(project_factory) -> None:
    project = project_factory(project_overrides={"pulls_dir": None})

    result = project.invoke("check", "dev")

    assert result.exit_code != 0, combined(result)


def test_check_allow_failures_restores_zero(project_factory) -> None:
    project = project_factory(project_overrides={"pulls_dir": None})

    result = project.invoke("check", "dev", "--allow-failures")

    assert result.exit_code == 0, combined(result)


def test_check_double_quiet_still_fails(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "-qq",
        "check",
        "dev",
        env={"STUB_EXIT_SSH": "1"},
    )

    assert result.exit_code != 0
    assert result.output == ""
    assert result.stderr == ""


def test_check_json_reports_probe_status(project_factory) -> None:
    project = project_factory(project_overrides={"pulls_dir": None})

    result = project.invoke("check", "dev", "--json")

    assert result.exit_code != 0, combined(result)
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["config"] == str((project.path / "sink.yaml").resolve())
    assert any(probe["ok"] is False for probe in payload["probes"])


def test_check_json_allow_failures_exits_zero(project_factory) -> None:
    project = project_factory(project_overrides={"pulls_dir": None})

    result = project.invoke("check", "dev", "--json", "--allow-failures")

    assert result.exit_code == 0, combined(result)
    payload = json.loads(result.stdout)
    assert payload["ok"] is False


def test_check_has_no_real_flag() -> None:
    result = CliRunner().invoke(cli, ["check", "--help"])

    assert "--real" not in result.output

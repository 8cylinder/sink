"""Check probes run without a dry-run/--real switch."""

from __future__ import annotations

from click.testing import CliRunner
from helpers import combined

from sink.cli import cli


def test_check_runs_probes_by_default(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() != ""


def test_check_has_no_real_flag() -> None:
    result = CliRunner().invoke(cli, ["check", "--help"])

    assert "--real" not in result.output

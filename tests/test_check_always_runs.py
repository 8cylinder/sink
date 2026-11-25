"""Check probes run without a dry-run/--real switch."""

from __future__ import annotations

import pytest

from helpers import combined


@pytest.mark.xfail(
    strict=True, reason="check still defaults to print-only probes"
)
def test_check_runs_probes_by_default(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() != ""


@pytest.mark.xfail(strict=True, reason="check still exposes the --real option")
def test_check_has_no_real_flag() -> None:
    from click.testing import CliRunner

    from sink.cli import cli

    result = CliRunner().invoke(cli, ["check", "--help"])

    assert "--real" not in result.output
    assert "-r" not in result.output

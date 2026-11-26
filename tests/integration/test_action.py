"""Real remote action execution against the Docker server."""

from __future__ import annotations

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_action_runs_a_remote_command(live_project) -> None:
    project = live_project()

    result = project.invoke("action", "dev", "hello", "--real")

    assert result.exit_code == 0, combined(result)
    assert "hello" in combined(result)


def test_action_reports_a_failing_remote_command(live_project) -> None:
    project = live_project(
        server_overrides={
            "actions": {
                "hello": "echo hello",
                "fail": "echo boom >&2; exit 7",
            }
        }
    )

    result = project.invoke("action", "dev", "fail", "--real")

    assert result.exit_code != 0, combined(result)
    assert "boom" in combined(result)

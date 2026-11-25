"""Red tests for behavior the modernization has not fixed yet.

Every strict xfail here must fail at the assertion shown in its body.  When a
stage fixes the bug it will XPASS, and the marker must be removed in that
stage's fix commit.
"""

from __future__ import annotations

import pytest
from helpers import combined, unwrap


@pytest.mark.xfail(
    strict=True,
    reason="N6: git's exit status is hidden by the pipeline to less",
)
def test_diff_propagates_a_git_failure(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "diff",
        "dev",
        "project/index.html",
        env={"STUB_EXIT_GIT": "1"},
    )

    assert result.exit_code != 0


@pytest.mark.xfail(
    strict=True,
    reason="N21: db put accepts a non-gzip file and fails on the server",
)
def test_db_put_rejects_a_non_gzip_file(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "put", "dev", "project/index.html")

    assert result.exit_code != 0
    assert "gzip" in combined(result).lower()


@pytest.mark.xfail(
    strict=True,
    reason="Stage 8: lando stderr is discarded and a failed pull exits 0",
)
def test_lando_pull_failure_is_reported(project_factory) -> None:
    project = project_factory(server_type="lando")

    result = project.invoke(
        "db",
        "pull",
        "dev",
        "--real",
        env={
            "STUB_EXIT_LANDO": "1",
            "STUB_ERR_LANDO": "lando exploded\n",
        },
    )

    assert result.exit_code != 0
    assert "lando exploded" in combined(result)


@pytest.mark.xfail(
    strict=True,
    reason="Stage 8: ddev stderr is discarded and a failed pull exits 0",
)
def test_ddev_pull_failure_is_reported(project_factory) -> None:
    project = project_factory(server_type="ddev")

    result = project.invoke(
        "db",
        "pull",
        "dev",
        "--real",
        env={
            "STUB_EXIT_DDEV": "1",
            "STUB_ERR_DDEV": "ddev exploded\n",
        },
    )

    assert result.exit_code != 0
    assert "ddev exploded" in combined(result)


@pytest.mark.xfail(
    strict=True,
    reason="N10/N23/S5: settings crashes on the ssh list and prints passwords",
)
def test_misc_settings_redacts_passwords(project_factory) -> None:
    project = project_factory()

    result = project.invoke("misc", "settings", "mysql")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)


@pytest.mark.xfail(
    strict=True,
    reason="N23/S5: misc api prints database passwords",
)
def test_misc_api_redacts_passwords(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "misc", "api", "servers", "dev", "mysql", "0", "password"
    )

    assert result.exit_code == 0, combined(result)
    assert "secret" not in result.output


def test_lando_pull_uses_lando(project_factory) -> None:
    project = project_factory(server_type="lando")

    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    text = unwrap(combined(result))
    assert "+ lando db-export" in text
    assert "ssh " not in text


def test_ddev_pull_uses_ddev(project_factory) -> None:
    project = project_factory(server_type="ddev")

    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    text = unwrap(combined(result))
    assert "+ ddev export-db" in text
    assert "ssh " not in text


def test_warn_prompt_is_asked_once_per_put(project_factory) -> None:
    """Characterization: one rsync action asks one confirmation question."""
    project = project_factory(warn=True)

    result = project.invoke("file", "put", "dev", "--real", input="y\n")

    assert result.exit_code == 0, combined(result)
    assert combined(result).count("WARNING") == 1

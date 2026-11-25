"""Stage 4 contract: one command object, argv execution, no leaked secrets."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest
from helpers import combined, commands_named, unwrap

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "sink"


@pytest.mark.xfail(
    strict=True, reason="Stage 4: remove every shell=True call site"
)
def test_no_shell_true_remains() -> None:
    offenders = [
        path.name
        for path in SRC.glob("*.py")
        if "shell=True" in path.read_text()
    ]
    assert offenders == []


@pytest.mark.xfail(
    strict=True,
    reason="Stage 4: subprocess belongs in the shell execution layer only",
)
def test_only_the_shell_module_imports_subprocess() -> None:
    offenders = [
        path.name
        for path in SRC.glob("*.py")
        if path.name != "shell.py" and "import subprocess" in path.read_text()
    ]
    assert offenders == []


@pytest.mark.xfail(
    strict=True,
    reason="Stage 4: remove the plumbum-backed command module",
)
def test_command_module_and_plumbum_are_gone() -> None:
    assert not (SRC / "command.py").exists()
    pyproject = (REPO / "pyproject.toml").read_text()
    assert "plumbum" not in pyproject


@pytest.mark.xfail(
    strict=True, reason="Stage 4: check must not execute without --real"
)
def test_check_defaults_to_dry_run(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() == ""


@pytest.mark.xfail(
    strict=True, reason="Stage 4: check must accept the shared --real flag"
)
def test_check_accepts_real(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() != ""


@pytest.mark.xfail(
    strict=True, reason="Stage 4: check must offer an explicit TLS opt-out"
)
def test_check_accepts_insecure(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev", "--insecure")

    assert result.exit_code == 0, combined(result)


@pytest.mark.xfail(
    strict=True,
    reason="Stage 4: check must verify TLS certificates by default",
)
def test_check_does_not_disable_tls_verification() -> None:
    source = (SRC / "check.py").read_text()
    assert "CERT_NONE" not in source


@pytest.mark.xfail(
    strict=True,
    reason="Stage 4: diff must print both commands and touch nothing by default",
)
def test_diff_defaults_to_print_only(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() == ""
    text = unwrap(combined(result))
    assert "rsync" in text
    assert "git" in text


@pytest.mark.xfail(
    strict=True,
    reason="Stage 4: diff must accept the shared --real flag",
)
def test_diff_accepts_real(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project/index.html", "--real")

    assert result.exit_code == 0, combined(result)
    assert [c.name for c in commands_named(project.stub_log, "rsync")]
    assert [c.name for c in commands_named(project.stub_log, "git")]


@pytest.mark.xfail(
    strict=True, reason="S1/S7: db pull renders the database password"
)
def test_db_pull_does_not_leak_the_password(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert "secret" not in project.stub_log.read_text()


@pytest.mark.xfail(
    strict=True, reason="S1/S7: db put renders the database password"
)
def test_db_put_does_not_leak_the_password(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "put", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert "secret" not in project.stub_log.read_text()


@pytest.mark.xfail(
    strict=True, reason="S1/S7: check renders the database password"
)
def test_check_does_not_leak_the_password(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert "secret" not in project.stub_log.read_text()


@pytest.mark.xfail(
    strict=True,
    reason="Stage 4: display wrapping currently splits quoted arguments",
)
def test_file_put_renders_the_argv_that_executes(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    rendered = next(
        line[2:]
        for line in unwrap(combined(result)).splitlines()
        if line.startswith("+ ")
    )
    executed = commands_named(project.stub_log, "rsync")[0]
    argv = shlex.split(rendered)
    assert argv[0] == executed.name
    assert tuple(argv[1:]) == executed.args

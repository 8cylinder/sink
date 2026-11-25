"""Stage 4 contract: one command object, argv execution, no leaked secrets."""

from __future__ import annotations

import shlex
import ssl
from pathlib import Path

import pytest
from helpers import combined, commands_named, unwrap

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "sink"


def test_no_shell_true_remains() -> None:
    offenders = [
        path.name
        for path in SRC.glob("*.py")
        if "shell=True" in path.read_text()
    ]
    assert offenders == []


def test_only_the_shell_module_imports_subprocess() -> None:
    offenders = [
        path.name
        for path in SRC.glob("*.py")
        if path.name != "shell.py" and "import subprocess" in path.read_text()
    ]
    assert offenders == []


def test_command_module_and_plumbum_are_gone() -> None:
    assert not (SRC / "command.py").exists()
    pyproject = (REPO / "pyproject.toml").read_text()
    assert "plumbum" not in pyproject


def test_check_defaults_to_dry_run(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() == ""


def test_check_accepts_real(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() != ""


def test_check_accepts_insecure(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev", "--insecure")

    assert result.exit_code == 0, combined(result)


def test_check_verifies_tls_by_default(
    project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_factory(urls=[{"url": "https://example.test"}])
    contexts: list[ssl.SSLContext] = []

    def fake_urlopen(url, timeout=None, context=None):
        contexts.append(context)
        return object()

    monkeypatch.setattr("sink.check.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("sink.check.Spinner.start", lambda self: None)
    monkeypatch.setattr("sink.check.Spinner.stop", lambda self: None)

    result = project.invoke("check", "dev", "--real")
    assert result.exit_code == 0, combined(result)
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname is True

    contexts.clear()
    result = project.invoke("check", "dev", "--real", "--insecure")
    assert result.exit_code == 0, combined(result)
    assert contexts[0].verify_mode == ssl.CERT_NONE


def test_diff_defaults_to_print_only(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() == ""
    text = unwrap(combined(result))
    assert "rsync" in text
    assert "git" in text


def test_diff_accepts_real(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project/index.html", "--real")

    assert result.exit_code == 0, combined(result)
    assert [c.name for c in commands_named(project.stub_log, "rsync")], (
        combined(result) + "\n" + project.stub_log.read_text()
    )
    assert [c.name for c in commands_named(project.stub_log, "git")], (
        combined(result) + "\n" + project.stub_log.read_text()
    )


def test_db_pull_does_not_leak_the_password(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert "secret" not in project.stub_log.read_text()


def test_db_put_does_not_leak_the_password(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "put", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert "secret" not in project.stub_log.read_text()


def test_check_does_not_leak_the_password(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert "secret" not in project.stub_log.read_text()


def test_db_pull_real_executes_and_does_not_leak(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert "secret" not in project.stub_log.read_text()
    assert "ssh" in [c.name for c in commands_named(project.stub_log, "ssh")]


def test_db_put_real_executes_and_does_not_leak(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "put", "dev", "project/index.html", "--real")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)
    assert "secret" not in project.stub_log.read_text()
    assert "ssh" in [c.name for c in commands_named(project.stub_log, "ssh")]


def test_action_local_runs_with_real(project_factory) -> None:
    project = project_factory(project_actions={"hello": "touch action-ran"})

    result = project.invoke("action", "local", "hello", "--real")

    assert result.exit_code == 0, combined(result)
    assert (project.path / "action-ran").exists()


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

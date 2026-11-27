"""Unit tests for the command objects that render and execute argv."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sink.errors import CommandError
from sink.shell import (
    Argv,
    Pipeline,
    RemoteCommand,
    remote_command,
    run,
    scp_argv,
    ssh_argv,
)


def test_argv_render_round_trips() -> None:
    command = Argv(
        ("rsync", "--itemize", "a b"),
        dry_run_flag="--dry-run",
    )

    assert shlex.split(command.render(True)) == list(command.argv_for(True))
    assert shlex.split(command.render(False)) == list(command.argv_for(False))
    assert command.render(True) == "rsync --itemize 'a b'"
    assert command.argv_for(False) == (
        "rsync",
        "--dry-run",
        "--itemize",
        "a b",
    )


def test_argv_executes_the_rendered_argv(tmp_path: Path) -> None:
    script = tmp_path / "record.py"
    script.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    command = Argv((sys.executable, str(script), "a b", "--flag"))

    result = run(command, real=True, capture=True)

    assert result.ok
    assert result.stdout.strip() == '["a b", "--flag"]'


def test_native_dry_run_flag_is_executed(tmp_path: Path) -> None:
    script = tmp_path / "record.sh"
    script.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > "$ARGS_FILE"\n'
    )
    script.chmod(0o755)
    args_file = tmp_path / "args.txt"
    command = Argv((str(script),), dry_run_flag="--dry-run")

    run(
        command,
        real=False,
        capture=True,
        env={"ARGS_FILE": str(args_file)},
    )
    assert args_file.read_text() == "--dry-run\n"

    args_file.write_text("")
    run(
        command,
        real=True,
        capture=True,
        env={"ARGS_FILE": str(args_file)},
    )
    assert args_file.read_text().strip() == ""


def test_print_only_does_not_spawn(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    script = tmp_path / "mark.sh"
    script.write_text(f"#!/usr/bin/env bash\ntouch {marker}\n")
    script.chmod(0o755)
    command = Argv((str(script),))

    result = run(command, real=False, capture=True)

    assert result.ok
    assert not marker.exists()

    result = run(command, real=True, capture=True)
    assert result.ok
    assert marker.exists()


def test_identity_error_blocks_real_execution(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    command = Argv(
        ("touch", str(marker)),
        identity_error="ssh key does not exist",
    )

    with pytest.raises(CommandError):
        run(command, real=True)

    assert not marker.exists()
    dry = run(command, real=False)
    assert dry.ok


def test_pipeline_executes_the_rendered_stages() -> None:
    upper = "import sys; sys.stdout.write(sys.stdin.read().upper())"
    pipeline = Pipeline(
        (
            Argv((sys.executable, "-c", "print('abc')")),
            Argv((sys.executable, "-c", upper)),
        )
    )

    assert " | " in pipeline.render(True)
    result = pipeline.execute(real=True, capture=True)

    assert result.ok
    assert result.stdout == "ABC\n"


def test_pipeline_writes_the_redirection(tmp_path: Path) -> None:
    destination = tmp_path / "out.txt"
    pipeline = Pipeline(
        (Argv((sys.executable, "-c", "print('hello')")),),
        stdout_path=destination,
    )

    result = pipeline.execute(real=True, capture=True)

    assert result.ok
    assert destination.read_text() == "hello\n"
    assert str(destination) in pipeline.render(True)


def test_pipeline_output_mode_is_private(tmp_path: Path) -> None:
    destination = tmp_path / "dump.sql.gz"
    pipeline = Pipeline(
        (Argv((sys.executable, "-c", "print('dump')")),),
        stdout_path=destination,
        stdout_mode=0o600,
    )
    previous = os.umask(0o022)
    try:
        result = pipeline.execute(real=True, capture=True)
    finally:
        os.umask(previous)

    assert result.ok
    assert destination.stat().st_mode & 0o777 == 0o600


def test_pipeline_reports_a_failing_producer() -> None:
    pipeline = Pipeline(
        (
            Argv(
                (
                    sys.executable,
                    "-c",
                    "import sys; sys.exit(3)",
                )
            ),
            Argv(
                (
                    sys.executable,
                    "-c",
                    "import sys; sys.stdin.read(); sys.exit(0)",
                )
            ),
        )
    )

    result = pipeline.execute(real=True, capture=True)

    assert result.returncode == 3


def test_pipeline_keeps_stderr_from_every_stage() -> None:
    pipeline = Pipeline(
        (
            Argv(
                (
                    sys.executable,
                    "-c",
                    "import sys; print('producer failed', file=sys.stderr); "
                    "sys.exit(3)",
                )
            ),
            Argv(
                (
                    sys.executable,
                    "-c",
                    "import sys; sys.stdin.read(); "
                    "print('consumer note', file=sys.stderr)",
                )
            ),
        )
    )

    result = pipeline.execute(real=True, capture=True)

    assert result.returncode == 3
    assert "producer failed" in result.stderr
    assert "consumer note" in result.stderr


def test_remote_command_quotes_the_fragment() -> None:
    ssh = SimpleNamespace(username="deploy", server="example.com", port=2222)
    command = remote_command(ssh, "echo hi", batch=True)

    assert isinstance(command, RemoteCommand)
    rendered = command.render(True)
    assert "'echo hi'" in rendered
    assert shlex.split(rendered)[-1] == "echo hi"
    assert command.argv_for(True)[-1] == "echo hi"


def test_ssh_and_scp_builders() -> None:
    ssh = SimpleNamespace(
        username="deploy",
        server="example.com",
        port=2222,
        key="/keys/id",
    )

    argv = ssh_argv(ssh, "exit", batch=True, timeout=25)
    assert argv[-1] == "exit"
    assert "-p" in argv
    assert "-i" in argv

    scp = scp_argv(ssh, "local", "remote")
    assert scp[0] == "scp"
    assert "-P" in scp
    assert scp[-2:] == ("local", "remote")

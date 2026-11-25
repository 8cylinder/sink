"""Direct branch coverage for shell, database, rsync, and credential helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from sink.config.models import (
    Action,
    DatabaseConfig,
    Project,
    Server,
    SSHConfig,
)
from sink.credentials import RemoteCredentials, remote_mysql_credentials
from sink.db import DB, _client_options, _port, _validate_gzip
from sink.errors import CommandError, TransferError
from sink.rsync import Transfer
from sink.shell import Argv, Pipeline, Result, devnull, run


def server(**overrides: Any) -> Server:
    values: dict[str, Any] = {
        "name": "dev",
        "root": Path("/var/www/demo"),
        "ssh": (
            SSHConfig(
                username="deploy",
                server="example.com",
                key="/srv/key",
                port=2222,
            ),
        ),
        "databases": (
            DatabaseConfig(
                db="demo",
                username="u",
                password="p",  # noqa: S106 - fixture
            ),
        ),
    }
    values.update(overrides)
    return Server(**values)


def project(tmp_path: Path) -> Project:
    return Project(name="demo", root=tmp_path, pulls_dir=tmp_path / "pulls")


def test_shell_edge_cases(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Argv(())
    with pytest.raises(ValueError):
        Pipeline(())
    with pytest.raises(TypeError):
        Pipeline((Argv(("echo",)),)).argv_for(True)

    args = Argv((str(Path(sys.executable)), "-c", "print('x')"))
    destination = tmp_path / "out"
    executed = args.execute(real=True, stdout=destination.open("w"))
    assert executed.returncode == 0
    assert destination.read_text() == "x\n"
    args.execute(real=True, capture=False)
    run(args, real=True, capture=True, quiet=2)
    assert devnull() == os.devnull

    pipeline = Pipeline(
        (Argv((sys.executable, "-c", "import sys; print('x')")),),
        stderr_devnull=True,
    )
    assert pipeline.execute(real=True, capture=False).returncode == 0

    error_path = tmp_path / "err"
    pipeline = Pipeline(
        (
            Argv(
                (
                    sys.executable,
                    "-c",
                    "import sys; print('e', file=sys.stderr)",
                )
            ),
        ),
        stderr_path=error_path,
    )
    pipeline.execute(real=True, capture=True)
    assert "e" in error_path.read_text()

    result = Pipeline((Argv((sys.executable, "-c", "print('abc')")),)).execute(
        real=True, capture=True
    )
    assert result.stdout == "abc\n"


def test_db_internal_edges(tmp_path: Path) -> None:
    db_config = DatabaseConfig(
        db="demo",
        username="user",
        hostname="host",
        port=3307,
        skip_secure_auth="yes",
    )
    assert _port(DatabaseConfig(port=None)) is None
    assert (
        _port(
            DatabaseConfig(port="bad")  # ty: ignore[invalid-argument-type]
        )
        is None
    )
    options = _client_options(db_config)
    assert "--host" in options and "--port" in options

    bad = tmp_path / "bad.sql.gz"
    bad.write_text("not gzip")
    with pytest.raises(CommandError):
        _validate_gzip(bad)
    with pytest.raises(CommandError):
        _validate_gzip(tmp_path)

    db = DB(project(tmp_path), server(), real=True)
    db._database()
    with pytest.raises(SystemExit):
        db._report_put(Result(1, "", "boom"))
    db._report_put(Result(0, "", "1\n2\n"))

    assert db._dest("demo", tmp_path, "dev", "tag").name.endswith("-tag.sql.gz")

    latest = tmp_path / "LATEST-dev.sql.gz"
    latest.write_text("")
    dump = tmp_path / "dump.sql.gz"
    dump.write_text("x")
    db.make_symlink(dump)
    assert latest.is_symlink()


def test_db_missing_pulls_dir(tmp_path: Path) -> None:
    db = DB(Project(name="demo", root=tmp_path), server())
    with pytest.raises(CommandError):
        db.pull()


def test_db_warn_cancel(tmp_path: Path, monkeypatch) -> None:
    db = DB(project(tmp_path), server(warn=True), real=True)
    monkeypatch.setattr("sink.db.click.confirm", lambda *_a, **_k: False)
    db.run_put_cmd(Argv(("true",)))


def test_credentials_edges() -> None:
    ssh = server().ssh[0]
    credentials = RemoteCredentials(
        ssh=ssh,
        password="",
        user="u",
        host="h",
        port=3306,
    )
    assert "password" not in credentials.content
    assert "port=3306" in credentials.content
    assert credentials.option.startswith("--defaults-extra-file=")
    assert "cat >" in credentials.stage_command().render(False)
    assert "rm -f" in credentials.cleanup_command().render(False)

    password = "p"  # noqa: S105 - test fixture
    with remote_mysql_credentials(ssh, password=password, real=False):
        pass


def test_credentials_stage_failure(monkeypatch) -> None:
    ssh = server().ssh[0]
    monkeypatch.setattr(
        "sink.credentials.run", lambda *_a, **_k: Result(1, "", "boom")
    )

    password = "p"  # noqa: S105 - test fixture
    with (
        pytest.raises(CommandError),
        remote_mysql_credentials(ssh, password=password, real=True),
    ):
        pass


def test_rsync_internal_edges(tmp_path: Path) -> None:
    project_value = project(tmp_path)
    transfer = Transfer(project_value, server())
    assert transfer._flags("") == ()
    assert transfer._flags("--delete --compress") == ("--delete", "--compress")
    assert transfer._flags(["--delete"]) == ("--delete",)

    with pytest.raises(TransferError):
        Transfer(project_value, server(root=None))._locations(tmp_path)
    outside = tmp_path.parent / "outside"
    outside.write_text("x")
    with pytest.raises(TransferError):
        transfer._locations(outside)

    with pytest.raises(SystemExit):
        Transfer(project_value, server(ssh=()))._rsync_command(
            tmp_path,
            Path("/remote"),
            Action.PUT,
            server(ssh=()),
        )

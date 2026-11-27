"""SEC-08: a pulled dump is committed only after a successful transfer."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from helpers import combined

from sink.db import DB


def test_startup_failure_leaves_no_partial_dump(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    real_popen = subprocess.Popen

    def fake_popen(*args, **kwargs):
        argv = kwargs.get("args", args[0] if args else [])
        if argv and argv[0] == "gzip":
            raise FileNotFoundError("gzip")
        return real_popen(*args, **kwargs)

    monkeypatch.setattr("sink.shell.subprocess.Popen", fake_popen)

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code != 0, combined(result)
    assert "Could not start" in combined(result)
    pulls = project.path / "pulls"
    assert not list(pulls.glob("*.sql.gz"))
    assert not list(pulls.glob("*.part*"))


def test_failed_pipeline_leaves_no_partial_dump(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "db",
        "pull",
        "dev",
        "--real",
        env={"STUB_EXIT_SSH": "1"},
    )

    assert result.exit_code != 0, combined(result)
    pulls = project.path / "pulls"
    assert not list(pulls.glob("*.sql.gz"))
    assert not list(pulls.glob("*.part*"))


def test_success_renames_the_part_and_updates_latest(project_factory) -> None:
    project = project_factory()

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    pulls = project.path / "pulls"
    dumps = list(pulls.glob("demo-dev-*.sql.gz"))
    assert dumps
    assert not list(pulls.glob("*.part*"))
    latest = pulls / "LATEST-dev.sql.gz"
    assert latest.is_symlink()
    assert latest.resolve() == dumps[0].resolve()


def test_stale_part_is_removed(project_factory) -> None:
    project = project_factory()
    pulls = project.path / "pulls"
    stale = pulls / "stale.sql.gz.part"
    stale.write_text("old")
    old = time.time() - 2 * 24 * 60 * 60
    os.utime(stale, (old, old))

    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    assert not stale.exists()


def test_final_path_preserves_a_tool_added_gzip_suffix() -> None:
    assert DB._final_path(Path("dump.sql"), Path("dump.sql.part.gz")) == Path(
        "dump.sql.gz"
    )

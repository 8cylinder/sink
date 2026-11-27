"""Interrupt a slow real transfer and check that it never claims success."""

from __future__ import annotations

import os
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _wait_for_text(path: Path, needle: str, timeout: float = 20) -> None:
    """Wait until *needle* appears in *path*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and needle in path.read_text(errors="replace"):
            return
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {needle!r} in {path}")


def _run_and_interrupt(
    project,
    log_name: str,
    args: tuple[str, ...],
    *,
    needle: str = "rsync",
    delay: float = 0.5,
) -> tuple[int, str]:
    """Start Sink, wait for *needle*, send SIGINT to the process group."""
    log = project.path / log_name
    with log.open("w") as output:
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "sink", *args],
            cwd=project.path,
            env=os.environ.copy(),
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        _wait_for_text(log, needle)
        time.sleep(delay)
        if process.poll() is None:
            os.killpg(os.getpgid(process.pid), signal.SIGINT)
        process.wait(timeout=30)
    return int(process.returncode), str(log.read_text(errors="replace"))


def test_sigint_during_a_large_file_put_does_not_claim_success(
    live_project,
) -> None:
    project = live_project()
    payload = project.path / "project" / "payload.bin"
    payload.write_bytes(os.urandom(2 * 1024 * 1024))

    code, text = _run_and_interrupt(
        project,
        "put.log",
        (
            "file",
            "put",
            "dev",
            "project/payload.bin",
            "--real",
            "--extra-flags=--bwlimit=20",
        ),
    )

    assert code != 0
    assert "[Success" not in text
    assert not project.remote_exists("payload.bin")
    leftovers = project.sandbox.exec(
        "server",
        "find",
        project.remote_root,
        "-maxdepth",
        "1",
        "-name",
        ".payload.bin.*",
        "-print",
        user="deploy",
    ).stdout
    assert leftovers.strip() == ""


def test_sigint_during_a_large_file_pull_does_not_claim_success(
    live_project,
) -> None:
    project = live_project()
    project.sandbox.exec(
        "server",
        "dd",
        "if=/dev/urandom",
        f"of={project.remote_path('remote.bin')}",
        "bs=1M",
        "count=2",
        user="deploy",
    )
    local = project.path / "project" / "remote.bin"
    local.unlink(missing_ok=True)
    backup = project.path / "project" / ".remote.bin.backup"
    backup.write_text("keep\n")
    swap = project.path / "project" / ".remote.bin.swp"
    swap.write_text("keep\n")

    code, text = _run_and_interrupt(
        project,
        "pull.log",
        (
            "file",
            "pull",
            "dev",
            "project/remote.bin",
            "--real",
            "--extra-flags=--bwlimit=20",
        ),
    )

    assert code != 0
    assert "[Success" not in text
    assert not local.exists()
    assert backup.exists()
    assert swap.exists()
    leftovers = [
        path
        for path in (project.path / "project").glob(".remote.bin.*")
        if path not in {backup, swap}
    ]
    assert leftovers == []


def _create_big_table(project, rows: int = 10_000) -> None:
    """Create a dump sized table for interruption tests."""
    project.sandbox.db_query("DROP TABLE IF EXISTS big_dump")
    project.sandbox.db_query(
        "CREATE TABLE big_dump ("
        "id INT PRIMARY KEY AUTO_INCREMENT, payload TEXT)"
    )
    project.sandbox.db_query(
        "INSERT INTO big_dump (payload) "  # noqa: S608 - test SQL
        "SELECT '' "
        "FROM information_schema.columns a, information_schema.columns b "
        f"LIMIT {rows}"
    )
    segments = ", ".join(
        f"SHA2(CONCAT(id, '{index}'), 256)" for index in range(16)
    )
    project.sandbox.db_query(
        f"UPDATE big_dump SET payload = CONCAT_WS('', {segments})"  # noqa: S608 - test SQL
    )


def _drop_big_table(project) -> None:
    """Remove the interruption-test table."""
    project.sandbox.db_query("DROP TABLE IF EXISTS big_dump")


def test_sigint_during_db_pull_does_not_create_latest(live_project) -> None:
    project = live_project()
    _create_big_table(project)
    try:
        code, text = _run_and_interrupt(
            project,
            "db.log",
            ("db", "pull", "dev", "--real"),
            needle="mysqldump",
            delay=0.2,
        )
    finally:
        _drop_big_table(project)

    assert code != 0
    assert "[Success" not in text
    assert not (project.path / "pulls" / "LATEST-dev.sql.gz").exists()
    pulls = project.path / "pulls"
    assert not list(pulls.glob("*.sql.gz"))
    assert not list(pulls.glob("*.part*"))
    assert project.sandbox.credentials_files() == []


def test_disk_pressure_during_db_pull_does_not_claim_success(
    live_project,
) -> None:
    project = live_project()
    _create_big_table(project)

    def limit_file_size() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))

    try:
        process = subprocess.run(
            [sys.executable, "-u", "-m", "sink", "db", "pull", "dev", "--real"],
            cwd=project.path,
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
            preexec_fn=limit_file_size,
        )
    finally:
        _drop_big_table(project)

    text = process.stdout + process.stderr
    assert process.returncode != 0
    assert "[Success" not in text
    assert not (project.path / "pulls" / "LATEST-dev.sql.gz").exists()
    pulls = project.path / "pulls"
    assert not list(pulls.glob("*.sql.gz"))
    assert not list(pulls.glob("*.part*"))
    assert project.sandbox.credentials_files() == []


def _wait_for_child(parent: int, name: str, timeout: float = 10) -> int:
    """Return the pid of a named direct child of *parent*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        listing = subprocess.run(
            ["ps", "-o", "pid=,comm=", "--ppid", str(parent)],
            text=True,
            capture_output=True,
            check=False,
        )
        for line in listing.stdout.splitlines():
            fields = line.split(None, 1)
            if len(fields) == 2 and fields[1].strip() == name:
                return int(fields[0])
        time.sleep(0.1)
    raise AssertionError(f"no {name!r} child of {parent}")


def test_ssh_drop_during_db_pull_reports_error_and_cleans(
    live_project,
) -> None:
    project = live_project()
    _create_big_table(project)
    log = project.path / "ssh-drop.log"
    try:
        with log.open("w") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    "-m",
                    "sink",
                    "db",
                    "pull",
                    "dev",
                    "--real",
                ],
                cwd=project.path,
                env=os.environ.copy(),
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            _wait_for_text(log, "mysqldump")
            ssh_pid = _wait_for_child(process.pid, "ssh")
            os.kill(ssh_pid, signal.SIGKILL)
            process.wait(timeout=30)
        text = log.read_text(errors="replace")
    finally:
        _drop_big_table(project)

    assert process.returncode != 0
    assert "[Success" not in text
    assert not (project.path / "pulls" / "LATEST-dev.sql.gz").exists()
    pulls = project.path / "pulls"
    assert not list(pulls.glob("*.sql.gz"))
    assert not list(pulls.glob("*.part*"))
    assert project.sandbox.credentials_files() == []


_MEMORY_WRAPPER = """
import os
import sys

pid = os.fork()
if pid == 0:
    os.execvp(sys.argv[1], sys.argv[1:])
_, status, usage = os.wait4(pid, 0)
print(f"SINK_MAXRSS {usage.ru_maxrss}", file=sys.stderr)
sys.exit(os.waitstatus_to_exitcode(status))
"""


def test_large_db_pull_stays_within_memory_budget(live_project) -> None:
    project = live_project()
    _create_big_table(project, rows=100_000)
    try:
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                _MEMORY_WRAPPER,
                sys.executable,
                "-u",
                "-m",
                "sink",
                "db",
                "pull",
                "dev",
                "--real",
            ],
            cwd=project.path,
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            check=False,
            timeout=180,
        )
    finally:
        _drop_big_table(project)

    assert process.returncode == 0, process.stdout + process.stderr
    assert "[Success" in process.stdout
    max_rss = next(
        int(line.split()[1])
        for line in process.stderr.splitlines()
        if line.startswith("SINK_MAXRSS ")
    )
    if sys.platform == "darwin":
        max_rss //= 1024
    assert max_rss < 80 * 1024
    assert (project.path / "pulls" / "LATEST-dev.sql.gz").is_symlink()
    assert not list((project.path / "pulls").glob("*.part*"))

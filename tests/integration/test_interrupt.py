"""Interrupt a slow real transfer and check that it never claims success."""

from __future__ import annotations

import os
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
    project, log_name: str, args: tuple[str, ...]
) -> tuple[int, str]:
    """Start Sink, wait for rsync, send SIGINT to the process group."""
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
        _wait_for_text(log, "rsync")
        time.sleep(0.5)
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
    assert not list((project.path / "project").glob(".remote.bin.*"))

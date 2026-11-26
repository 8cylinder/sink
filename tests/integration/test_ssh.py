"""Interactive SSH sessions against the Docker server."""

from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import time
import uuid

import pytest

pytestmark = pytest.mark.integration


def test_interactive_ssh_starts_in_the_server_root(live_project) -> None:
    project = live_project()
    marker = f"/home/deploy/sink-interactive-{uuid.uuid4().hex[:8]}"
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "sink", "ssh", "dev", "--real"],
            cwd=project.path,
            env=os.environ.copy(),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
        )
        os.close(slave)
        os.write(master, f"pwd > {marker}; exit\n".encode())

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    if not os.read(master, 4096):
                        break
                except OSError:
                    break
            if process.poll() is not None:
                break
        process.wait(timeout=10)
    finally:
        os.close(master)

    content = project.sandbox.exec(
        "server", "cat", marker, user="deploy", check=False
    ).stdout
    project.sandbox.exec("server", "rm", "-f", marker, check=False)

    assert process.returncode == 0
    assert content.strip() == project.remote_root

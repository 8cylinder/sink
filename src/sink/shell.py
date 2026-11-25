"""Single execution layer for rendered shell commands.

Every command has one representation.  ``render()`` prints it and
``execute()`` runs the same argv/pipeline; there is no second construction
path that can drift.  Tools with a native dry-run flag (rsync) execute their
dry-run variant by default.  Tools without one are printed and not spawned.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from sink.ui import ui


@dataclass(frozen=True, slots=True)
class Result:
    """Captured command result."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        """Whether the command exited successfully."""
        return self.returncode == 0


class Command(Protocol):
    """Protocol shared by argv, remote, and pipeline commands."""

    def argv_for(self, real: bool) -> tuple[str, ...]:
        """Return the local argv for the selected mode."""
        ...

    def render(self, real: bool) -> str:
        """Render the command as valid shell text."""
        ...

    def can_execute(self, real: bool) -> bool:
        """Whether this mode may spawn a process."""
        ...

    def execute(
        self,
        *,
        real: bool,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        capture: bool = True,
        input: str | None = None,
        stdout: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> Result:
        """Execute the selected variant."""
        ...


@dataclass(frozen=True, slots=True)
class Argv:
    """A program and its arguments."""

    argv: tuple[str, ...]
    dry_run_flag: str | None = None
    env_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.argv:
            raise ValueError("argv must contain at least the program")

    def argv_for(self, real: bool) -> tuple[str, ...]:
        """Return the argv, adding a native dry-run flag when asked."""
        # The flag belongs to the tool, not the shell, so it sits directly
        # after the program name and is part of the same argv that executes.
        if not real and self.dry_run_flag:
            return (self.argv[0], self.dry_run_flag, *self.argv[1:])
        return self.argv

    def can_execute(self, real: bool) -> bool:
        """Whether this mode may spawn a process."""
        return real or self.dry_run_flag is not None

    def render(self, real: bool) -> str:
        """Render the argv as a safe shell command."""
        command = shlex.join(self.argv_for(real))
        if self.env_refs:
            prefix = " ".join(f'{name}="${{{name}}}"' for name in self.env_refs)
            return f"{prefix} {command}"
        return command

    def execute(
        self,
        *,
        real: bool,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        capture: bool = True,
        input: str | None = None,
        stdout: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> Result:
        """Run the selected argv."""
        argv = self.argv_for(real)
        return _execute_argv(
            argv,
            env=env,
            cwd=cwd,
            capture=capture,
            input=input,
            stdout=stdout,
            stderr=stderr,
        )


@dataclass(frozen=True, slots=True)
class RemoteCommand:
    """A local ssh argv plus the fragment sent to the remote shell."""

    ssh_argv: tuple[str, ...]
    fragment: str

    def argv_for(self, real: bool) -> tuple[str, ...]:
        """Append the remote fragment as one ssh argument."""
        return (*self.ssh_argv, self.fragment)

    def render(self, real: bool) -> str:
        """Render the ssh argv with a quoted fragment."""
        return shlex.join(self.argv_for(real))

    def can_execute(self, real: bool) -> bool:
        """Remote commands never have a native dry-run."""
        return real

    def execute(
        self,
        *,
        real: bool,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        capture: bool = True,
        input: str | None = None,
        stdout: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> Result:
        """Run the ssh argv."""
        return _execute_argv(
            self.argv_for(real),
            env=env,
            cwd=cwd,
            capture=capture,
            input=input,
            stdout=stdout,
            stderr=stderr,
        )


@dataclass(frozen=True, slots=True)
class Pipeline:
    """A local pipeline with optional file redirections."""

    stages: tuple[Command, ...]
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    stderr_devnull: bool = False

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("pipeline must contain at least one stage")

    def argv_for(self, real: bool) -> tuple[str, ...]:
        """Pipelines have no single argv."""
        raise TypeError("a pipeline has no single argv")

    def render(self, real: bool) -> str:
        """Render stages and redirections as shell text."""
        text = " | ".join(stage.render(real) for stage in self.stages)
        if self.stdout_path is not None:
            text += f" > {shlex.quote(str(self.stdout_path))}"
        if self.stderr_devnull:
            text += " 2>/dev/null"
        elif self.stderr_path is not None:
            text += f" 2> {shlex.quote(str(self.stderr_path))}"
        return text

    def can_execute(self, real: bool) -> bool:
        """Pipelines only execute in real mode."""
        return real

    def execute(
        self,
        *,
        real: bool,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        capture: bool = True,
        input: str | None = None,
        stdout: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> Result:
        """Connect stages with pipes and apply redirections."""
        return _execute_pipeline(
            self,
            env=env,
            cwd=cwd,
            capture=capture,
            input=input,
            stdout=stdout,
            stderr=stderr,
        )


def _execute_argv(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None,
    cwd: Path | None,
    capture: bool,
    input: str | None,
    stdout: IO[str] | None,
    stderr: IO[str] | None,
) -> Result:
    """Execute one argv with optional capture and stdin."""
    run_kwargs: dict[str, object] = {
        "args": list(argv),
        "env": dict(env) if env is not None else None,
        "cwd": str(cwd) if cwd is not None else None,
        "check": False,
        "text": True,
    }
    if input is not None:
        run_kwargs["input"] = input
    if stdout is not None:
        run_kwargs["stdout"] = stdout
        run_kwargs["stderr"] = stderr
    elif capture:
        run_kwargs["capture_output"] = True
    else:
        run_kwargs["stdout"] = None
        run_kwargs["stderr"] = None

    completed = subprocess.run(**run_kwargs)
    return Result(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _execute_pipeline(
    pipeline: Pipeline,
    *,
    env: Mapping[str, str] | None,
    cwd: Path | None,
    capture: bool,
    input: str | None,
    stdout: IO[str] | None,
    stderr: IO[str] | None,
) -> Result:
    """Execute a Popen chain and return its result."""
    processes: list[subprocess.Popen[str]] = []
    previous: subprocess.Popen[str] | None = None
    output_file: IO[str] | None = None

    try:
        if stdout is not None:
            output = stdout
        elif pipeline.stdout_path is not None:
            output_file = pipeline.stdout_path.open("w")
            output = output_file
        else:
            output = subprocess.PIPE

        if pipeline.stderr_devnull:
            error_target: object = subprocess.DEVNULL
        elif stderr is not None:
            error_target = stderr
        else:
            error_target = subprocess.PIPE

        for index, stage in enumerate(pipeline.stages):
            last = index == len(pipeline.stages) - 1
            # Each stage receives the previous stage's stdout.  The writer
            # side is closed in the parent after connecting the next stage;
            # otherwise the reader would never see EOF.
            process = subprocess.Popen(
                list(stage.argv_for(True)),
                stdin=previous.stdout if previous is not None else None,
                stdout=output if last else subprocess.PIPE,
                stderr=error_target,
                env=dict(env) if env is not None else None,
                cwd=str(cwd) if cwd is not None else None,
                text=True,
            )
            if previous is not None and previous.stdout is not None:
                previous.stdout.close()
            previous = process
            processes.append(process)

        if previous is None:
            raise RuntimeError("pipeline did not start")
        # Only the final process writes to the caller's output; earlier
        # processes are drained/wait'ed below so their stderr is not lost.
        output_text, error_text = previous.communicate(input=input)
    finally:
        if output_file is not None:
            output_file.close()

    for process in processes[:-1]:
        process.wait()

    if output_text is None:
        output_text = ""
    if error_text is None:
        error_text = ""

    return Result(
        returncode=previous.returncode,
        stdout=output_text,
        stderr=error_text,
    )


def run(
    command: Command,
    *,
    real: bool,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    capture: bool = True,
    input: str | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    quiet: int = 0,
) -> Result:
    """Print *command* and run the variant that belongs to this mode."""
    if quiet < 1:
        ui.display_cmd(command.render(real))
    if not command.can_execute(real):
        return Result(returncode=0)
    return command.execute(
        real=real,
        env=env,
        cwd=cwd,
        capture=capture,
        input=input,
        stdout=stdout,
        stderr=stderr,
    )


def _ssh_base(
    ssh: object,
    *,
    tty: bool = False,
    batch: bool = False,
    timeout: int | None = None,
    port: int | None = None,
    key: str | None = None,
    compress: bool = False,
) -> tuple[str, ...]:
    """Build the local ssh argv before the remote fragment."""
    argv: list[str] = ["ssh"]
    if compress:
        argv.append("-C")
    argv.append("-t" if tty else "-T")
    if port is None:
        port = getattr(ssh, "port", None)
    if port:
        argv.extend(["-p", str(port)])
    if key is None:
        key = getattr(ssh, "key", None)
    if key:
        argv.extend(["-i", str(key)])
    if batch:
        argv.extend(["-o", "BatchMode=yes"])
        argv.extend(["-o", "StrictHostKeyChecking=yes"])
    if timeout:
        argv.extend(["-o", f"ConnectTimeout={timeout}"])
    host = getattr(ssh, "server", None)
    username = getattr(ssh, "username", None)
    argv.append(f"{username}@{host}")
    return tuple(argv)


def ssh_argv(
    ssh: object,
    fragment: str,
    *,
    tty: bool = False,
    batch: bool = False,
    timeout: int | None = None,
    port: int | None = None,
    key: str | None = None,
    compress: bool = False,
) -> tuple[str, ...]:
    """Build a full ssh argv including the remote fragment."""
    return (
        *_ssh_base(
            ssh,
            tty=tty,
            batch=batch,
            timeout=timeout,
            port=port,
            key=key,
            compress=compress,
        ),
        fragment,
    )


def remote_command(
    ssh: object,
    fragment: str,
    *,
    tty: bool = False,
    batch: bool = False,
    timeout: int | None = None,
    port: int | None = None,
    key: str | None = None,
    compress: bool = False,
) -> RemoteCommand:
    """Build a reusable remote command object."""
    return RemoteCommand(
        ssh_argv=_ssh_base(
            ssh,
            tty=tty,
            batch=batch,
            timeout=timeout,
            port=port,
            key=key,
            compress=compress,
        ),
        fragment=fragment,
    )


def scp_argv(
    ssh: object,
    source: str,
    destination: str,
    *,
    timeout: int = 10,
) -> tuple[str, ...]:
    """Build an scp argv for a source and destination."""
    argv: list[str] = [
        "scp",
        "-o",
        f"ConnectTimeout={timeout}",
    ]
    port = getattr(ssh, "port", None)
    if port:
        argv.extend(["-P", str(port)])
    key = getattr(ssh, "key", None)
    if key:
        argv.extend(["-i", str(key)])
    argv.extend([source, destination])
    return tuple(argv)


def devnull() -> str:
    """Return the platform null device path."""
    return os.devnull

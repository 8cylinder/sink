"""Small, dependency-free helpers shared by the test suite."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    return ANSI_RE.sub("", text)


def combined(result) -> str:
    """Return stdout and stderr without ANSI escapes.

    Click 8.5's ``Result.output`` already interleaves stdout and stderr;
    ``Result.stdout`` and ``Result.stderr`` stay separate.  Use the
    separate streams so stderr is not counted twice.
    """
    stdout = getattr(result, "stdout", result.output)
    stderr = getattr(result, "stderr", "")
    return strip_ansi(stdout + stderr)


def unwrap(text: str) -> str:
    """Undo the display layer's shell line continuations.

    ``ui.display_cmd`` wraps long commands with a backslash/newline pair.
    Splitting that text with ``shlex`` is not useful until the continuation
    is joined again.  Spinner backspaces are also removed so ``check``
    output is stable.
    """
    text = strip_ansi(text).replace("\x08", "")
    text = re.sub(r"\\\n[ \t]*", " ", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines)


@dataclass(frozen=True)
class LoggedCommand:
    """One invocation recorded by a stub executable."""

    name: str
    args: tuple[str, ...]

    @property
    def dry_run(self) -> bool:
        return "--dry-run" in self.args


def parse_stub_log(path: Path) -> list[LoggedCommand]:
    """Parse the ``CMD``/``ARG``/``END`` records written by the stubs."""
    commands: list[LoggedCommand] = []
    name: str | None = None
    args: list[str] = []
    for line in path.read_text().splitlines():
        if line.startswith("CMD "):
            name = line[4:]
            args = []
        elif line.startswith("ARG "):
            args.append(line[4:])
        elif line == "END" and name is not None:
            commands.append(LoggedCommand(name=name, args=tuple(args)))
            name = None
            args = []
    return commands


def commands_named(path: Path, name: str) -> list[LoggedCommand]:
    """Return every recorded invocation of *name*."""
    return [command for command in parse_stub_log(path) if command.name == name]

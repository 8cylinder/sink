"""Rich console output, status labels, and redaction."""

import os
import sys
from collections.abc import Generator, Iterable, Mapping
from contextlib import contextmanager

import click
from rich.console import Console
from rich.text import Text


class ui:
    """Console output, labels, redaction, and output levels."""

    quiet = 0
    verbose = 0
    suppress = False
    console = Console(highlight=False)
    err_console = Console(stderr=True, highlight=False)

    @classmethod
    def configure(
        cls,
        *,
        color: str = "auto",
        quiet: int = 0,
        verbose: int = 0,
        suppress: bool = False,
    ) -> None:
        """Configure colors and output levels for this invocation."""
        # quiet=1 hides rendered commands; quiet=2 hides every status/output
        # line.  ``suppress`` mirrors the legacy -s flag.
        cls.quiet = quiet
        cls.verbose = verbose
        cls.suppress = suppress
        if color == "always":
            cls.console = Console(
                force_terminal=True, highlight=False, color_system="standard"
            )
            cls.err_console = Console(
                stderr=True,
                force_terminal=True,
                highlight=False,
                color_system="standard",
            )
        elif color == "never":
            cls.console = Console(no_color=True, highlight=False)
            cls.err_console = Console(
                stderr=True, no_color=True, highlight=False
            )
        else:
            no_color = bool(os.environ.get("NO_COLOR"))
            cls.console = Console(no_color=no_color, highlight=False)
            cls.err_console = Console(
                stderr=True, no_color=no_color, highlight=False
            )

    @classmethod
    @contextmanager
    def status(cls, message: str) -> Generator[object]:
        """Show a Rich status spinner unless output is fully suppressed."""
        if cls.quiet >= 2:
            yield None
            return
        with cls.console.status(message) as status:
            yield status

    @staticmethod
    def heading(msg: str, *, underline: bool = False) -> None:
        """Print a section heading."""
        if ui.quiet >= 2:
            return
        text = Text(msg, style="bold green")
        text.stylize("underline" if underline else "bold")
        ui.console.print(text, soft_wrap=True)

    @staticmethod
    def redact(text: str, secrets: Iterable[str] = ()) -> str:
        """Mask known secret values in text."""
        for secret in secrets:
            if secret:
                text = text.replace(str(secret), "********")
        return text

    @staticmethod
    def echo(msg: str = "", nl: bool = True) -> None:
        """Print plain text unless ``-qq`` is active."""
        if ui.quiet >= 2:
            return
        click.echo(msg, nl=nl)

    @staticmethod
    def output(text: str) -> None:
        """Print command output verbatim unless -qq is active."""
        if ui.quiet >= 2 or not text:
            return
        click.echo(text, nl=False)

    @staticmethod
    def msg(message: str) -> None:
        """Print a multi-line message."""
        lines = [line.strip() for line in message.split("\n")]
        if ui.quiet >= 2:
            return
        click.echo("\n".join(lines))

    @staticmethod
    def notice(msg: str) -> None:
        """Print a notice to stderr."""
        if ui.quiet >= 2:
            return
        ui.err_console.print(
            Text(f"[Notice] {msg}", style="blue"), soft_wrap=True
        )

    @staticmethod
    def warn(msg: str, indent: str = "") -> None:
        """Print a warning to stderr."""
        if ui.quiet >= 2:
            return
        ui.err_console.print(
            Text(f"{indent}[Warning] {msg}", style="yellow"), soft_wrap=True
        )

    @staticmethod
    def error(
        msg: str,
        exit: bool = True,
        indent: int = 0,
        secrets: Iterable[str] = (),
    ) -> None:
        """Print an error and optionally exit non-zero."""
        msg = ui.redact(str(msg), secrets).strip("\n")
        distance = ""
        if indent:
            distance = " " * indent
            # Keep the indentation before the label, not after it.
            msg = f"\n{distance}".join(msg.split("\n"))
        if ui.quiet < 2:
            ui.err_console.print(
                Text(f"{distance}[Error] {msg}", style="red"), soft_wrap=True
            )
        if exit:
            sys.exit(1)

    @staticmethod
    def display_cmd(
        cmd: str,
        indent: int = 0,
        suppress_commands: bool = False,
        secrets: Iterable[str] = (),
    ) -> None:
        """Print a rendered command unless quiet or suppressed."""
        if ui.quiet >= 1 or ui.suppress or suppress_commands:
            return
        cmd = ui.redact(cmd, secrets)
        distance = " " * indent
        # soft_wrap keeps one copy-pasteable line; wrapping inside a quoted
        # argument would change the shell command when pasted.
        ui.console.print(
            Text(f"{distance}+ {cmd}", style="yellow dim"),
            soft_wrap=True,
        )

    @staticmethod
    def display_success(
        real: bool,
        extra: str | None = None,
        *,
        server: str | None = None,
        message: str | None = None,
    ) -> None:
        """Print a success label with optional server/details."""
        if ui.quiet >= 2:
            return
        label = "[Success]" if real else "[Success (DRY RUN)]"
        style = "bold white on green" if real else "bold white on blue"
        text = Text(label, style=style)
        detail = ""
        if server is not None:
            detail = f"{server}: {message or 'complete'}"
        elif message is not None:
            detail = message
        elif extra:
            detail = extra
        if detail:
            text.append(f" {detail}")
        ui.console.print(text)

    @staticmethod
    def display_options(data: Mapping[str, object]) -> None:
        """Print aligned key/value options."""
        if ui.quiet >= 2:
            return
        width = max((len(key) for key in data), default=0)
        for key, val in data.items():
            text = Text()
            text.append(key.ljust(width), style="bold")
            text.append(f"  ({val})", style="blue")
            ui.console.print(text, soft_wrap=True)

    @staticmethod
    def print_stack() -> None:
        """Print a compact stack trace."""
        import traceback

        if ui.quiet >= 2:
            return
        for line in traceback.format_stack()[:-1]:
            filename, code = line.strip().split("\n")
            ui.console.print(Text(f"\u25a0 {filename}", style="red"))
            ui.console.print(Text(code, style="yellow"))

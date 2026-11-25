import os
import random
import sys
import threading
import time

import click
from rich.console import Console
from rich.text import Text


class Spinner:
    busy = False
    delay = 0.1

    @staticmethod
    def spinning_cursor(indent):
        cursors = [
            "|/-\\",
            "_.oO||Oo._",
            "\u237a\u237b\u237c\u237d__\u237d\u237c\u237b\u237a",
            "\u2588\u2589\u258a\u258b\u258c\u258d\u258e\u258f\u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588",
            " \u2591\u2592\u2593\u2588\u2588\u2593\u2592\u2591 ",
        ]
        cursors = random.choice(cursors)
        while True:
            for cursor in cursors:
                yield f"{indent}[{cursor}]"

    def __init__(self, delay=None, indent=0):
        self.indent = indent
        indent_char = " " * indent
        self.spinner_generator = self.spinning_cursor(indent_char)
        if delay and float(delay):
            self.delay = delay

    def spinner_task(self):
        while self.busy:
            sys.stdout.write(next(self.spinner_generator))
            sys.stdout.flush()
            time.sleep(self.delay)
            sys.stdout.write("\b" * (self.indent + 3))
            sys.stdout.flush()

    def start(self):
        self.busy = True
        threading.Thread(target=self.spinner_task).start()

    def stop(self):
        self.busy = False
        time.sleep(self.delay)


class ui:
    quiet = 0
    verbose = 0
    suppress = False
    console = Console(highlight=False)
    err_console = Console(stderr=True, highlight=False)

    @classmethod
    def configure(
        cls,
        *,
        color="auto",
        quiet=0,
        verbose=0,
        suppress=False,
    ):
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

    @staticmethod
    def heading(msg, *, underline=False):
        if ui.quiet >= 2:
            return
        text = Text(msg, style="bold green")
        text.stylize("underline" if underline else "bold")
        ui.console.print(text, soft_wrap=True)

    @staticmethod
    def redact(text, secrets=()):
        for secret in secrets:
            if secret:
                text = text.replace(str(secret), "********")
        return text

    @staticmethod
    def echo(msg="", nl=True):
        if ui.quiet >= 2:
            return
        click.echo(msg, nl=nl)

    @staticmethod
    def output(text):
        """Print command output verbatim unless -qq is active."""
        if ui.quiet >= 2 or not text:
            return
        click.echo(text, nl=False)

    @staticmethod
    def msg(msg):
        msg = [i.strip() for i in msg.split("\n")]
        if ui.quiet >= 2:
            return
        click.echo("\n".join(msg))

    @staticmethod
    def notice(msg):
        if ui.quiet >= 2:
            return
        ui.err_console.print(
            Text(f"[Notice:] {msg}", style="blue"), soft_wrap=True
        )

    @staticmethod
    def warn(msg, indent=""):
        if ui.quiet >= 2:
            return
        ui.err_console.print(
            Text(f"{indent}[Warning:] {msg}", style="yellow"), soft_wrap=True
        )

    @staticmethod
    def error(msg, exit=True, indent=0, secrets=()):
        msg = ui.redact(msg, secrets)
        distance = ""
        if indent:
            distance = " " * indent
            msg = "\n".join([f"{distance}{i}" for i in msg.split("\n")])
        if ui.quiet < 2:
            ui.err_console.print(
                Text(f"{distance}[Error:] {msg}", style="red"), soft_wrap=True
            )
        if exit:
            sys.exit(1)

    @staticmethod
    def display_cmd(cmd, indent=0, suppress_commands=False, secrets=()):
        if ui.quiet >= 1 or ui.suppress or suppress_commands:
            return
        cmd = ui.redact(cmd, secrets)
        distance = " " * indent
        ui.console.print(
            Text(f"{distance}+ {cmd}", style="yellow dim"),
            soft_wrap=True,
        )

    @staticmethod
    def display_success(real, extra=None, *, server=None, message=None):
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
    def display_options(data):
        if ui.quiet >= 2:
            return
        width = max((len(key) for key in data), default=0)
        for key, val in data.items():
            text = Text()
            text.append(key.ljust(width), style="bold")
            text.append(f"  ({val})", style="blue")
            ui.console.print(text, soft_wrap=True)

    @staticmethod
    def print_stack():
        import traceback

        if ui.quiet >= 2:
            return
        for line in traceback.format_stack()[:-1]:
            filename, code = line.strip().split("\n")
            ui.console.print(Text(f"\u25a0 {filename}", style="red"))
            ui.console.print(Text(code, style="yellow"))

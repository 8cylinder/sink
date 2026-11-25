import random
import sys
import threading
import time
from enum import Enum

import click


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
                yield click.style(
                    f"{indent}[{cursor}]", fg=str(Color.YELLOW.value)
                )

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


class Color(Enum):
    BLACK = "black"
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"
    MAGENTA = "magenta"
    CYAN = "cyan"
    WHITE = "white"
    # RESET = 'reset'


class ui:
    suppress = False

    @staticmethod
    def msg(msg):
        msg = [i.strip() for i in msg.split("\n")]
        click.echo("\n".join(msg))

    @staticmethod
    def notice(msg):
        w = click.style("Notice:", bold=True, fg=Color.BLUE.value)
        m = click.style(msg, fg=Color.BLUE.value, reset=True)
        click.echo(f"{w} {m}", err=True)

    @staticmethod
    def warn(msg, indent=""):
        w = click.style("Warning:", bold=True, fg=Color.YELLOW.value)
        m = click.style(msg, fg=Color.YELLOW.value, reset=True)
        click.echo(f"{indent}{w} {m}", err=True)

    @staticmethod
    def error(msg, exit=True, indent=0, secrets=()):
        msg = ui.redact(msg, secrets)
        distance = ""
        if indent:
            distance = " " * indent
            msg = "\n".join([f"{distance}{i}" for i in msg.split("\n")])
        e = click.style(f"\n{distance}Error:", bold=True, fg=Color.RED.value)
        m = click.style(msg, fg="red", reset=True)
        click.echo(f"{e} {m}", err=True)
        if exit:
            sys.exit(1)

    @staticmethod
    def redact(text, secrets=()):
        for secret in secrets:
            if secret:
                text = text.replace(str(secret), "********")
        return text

    @staticmethod
    def display_cmd(cmd, indent=0, suppress_commands=False, secrets=()):
        if ui.suppress or suppress_commands:
            return
        cmd = ui.redact(cmd, secrets)
        distance = " " * indent
        click.secho(f"{distance}+ {cmd}", fg=Color.YELLOW.value, dim=True)

    @staticmethod
    def display_success(real, extra=None):
        nl = True
        if extra:
            nl = False
            extra = f" {extra}"
        if real:
            click.secho(
                "Success",
                nl=nl,
                bg=Color.GREEN.value,
                fg=Color.WHITE.value,
                bold=True,
            )
        else:
            click.secho(
                "Success (DRY RUN)",
                nl=nl,
                bg=Color.BLUE.value,
                fg=Color.WHITE.value,
                bold=True,
            )
        if extra:
            # click.secho(extra)
            print(extra)

    @staticmethod
    def display_options(data):
        max = 0
        for key, _val in data.items():
            if len(key) > max:
                max = len(key)
        for key, val in data.items():
            key = click.style(key.ljust(max), bold=True)
            val = click.style(f"({val})", fg=Color.BLUE.value)
            click.echo(f"  {key}  {val}")

    @staticmethod
    def print_stack():
        import traceback

        for line in traceback.format_stack()[:-1]:
            filename, code = line.strip().split("\n")
            print(click.style("■", fg="red"), filename)
            print(click.style(code, fg="yellow"))

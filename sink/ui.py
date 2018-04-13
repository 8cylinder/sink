import sys
import os
import click
from pprint import pprint as pp
from enum import Enum
from textwrap import TextWrapper


class Color(Enum):
    BLACK = 'black'
    RED = 'red'
    GREEN = 'green'
    YELLOW = 'yellow'
    BLUE = 'blue'
    MAGENTA = 'magenta'
    CYAN = 'cyan'
    WHITE = 'white'
    # RESET = 'reset'


class ui:
    @staticmethod
    def error(msg, exit=True):
        # e = click.style('\nError', fg=Color.WHITE.value, bg=Color.RED.value)
        # msg = click.style(msg, reset=True)
        click.secho(f'\nError: {msg}', err=True, reset=True)
        if exit:
            sys.exit(1)

    @staticmethod
    def display_cmd(cmd, indent=0):
        console_width = os.get_terminal_size().columns
        if not console_width:
            console_width = 80
        indent = ' ' * indent
        leader = '+ '
        initial_indent = indent + leader
        subsequent_indent = indent + (' ' * len(leader))
        w = TextWrapper(initial_indent=initial_indent,
                        subsequent_indent=subsequent_indent,
                        break_on_hyphens=False,
                        break_long_words=False,
                        width=(console_width - len(subsequent_indent)))
        lines = w.wrap(cmd)
        # Add a space & backslash to the end of each line then remove it from
        # the end of the joined string.
        para = '\n'.join([f'{i} \\' for i in lines])[:-2]
        click.secho(f'{para}', fg=Color.YELLOW.value, dim=True)

    @staticmethod
    def display_success(real):
        if real:
            click.secho('Success', bg=Color.GREEN.value, fg=Color.BLACK.value)
        else:
            click.secho('Success (DRY RUN)', bg=Color.BLUE.value, fg=Color.WHITE.value)

    @staticmethod
    def display_options(data):
        max = 0
        for key, val in data.items():
            if len(key) > max:
                max = len(key)
        for key, val in data.items():
            key = click.style(key.ljust(max), bold=True)
            val = click.style(f'({val})', fg=Color.BLUE.value)
            click.echo(f'  {key}  {val}')

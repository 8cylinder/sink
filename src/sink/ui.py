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
    def msg(msg):
        msg = [i.strip() for i in msg.split('\n')]
        click.echo('\n'.join(msg))

    @staticmethod
    def notice(msg):
        w = click.style('Notice:', bold=True, fg=Color.BLUE.value)
        m = click.style(msg, fg=Color.BLUE.value, reset=True)
        click.echo(f'{w} {m}', err=True)

    @staticmethod
    def warn(msg, indent=''):
        w = click.style('Warning:', bold=True, fg=Color.YELLOW.value)
        m = click.style(msg, fg=Color.YELLOW.value, reset=True)
        click.echo(f'{indent}{w} {m}', err=True)

    @staticmethod
    def error(msg, exit=True, indent=0):
        distance = ''
        if indent:
            distance = ' ' * indent
            msg = '\n'.join([f'{distance}{i}' for i in msg.split('\n')])
        e = click.style(f'\n{distance}Error:', bold=True, fg=Color.RED.value)
        m = click.style(msg, fg='red', reset=True)
        click.echo(f'{e} {m}', err=True)
        if exit:
            sys.exit(1)

    @staticmethod
    def display_cmd(cmd, indent=0, suppress_commands=False):
        if suppress_commands:
            return
        try:
            console_width = os.get_terminal_size().columns
        except OSError:
            console_width = 80
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
    def display_success(real, extra=None):
        nl = True
        if extra:
            nl = False
            extra = f' {extra}'
        if real:
            click.secho('Success', nl=nl, bg=Color.GREEN.value, fg=Color.WHITE.value, bold=True)
        else:
            click.secho('Success (DRY RUN)', nl=nl, bg=Color.BLUE.value, fg=Color.WHITE.value, bold=True)
        if extra:
            # click.secho(extra)
            print(extra)

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

    @staticmethod
    def print_stack():
        import traceback
        for line in traceback.format_stack()[:-1]:
            filename, code = line.strip().split('\n')
            print(click.style('■', fg='red'), filename)
            print(click.style(code, fg='yellow'))

#!/usr/bin/env python3
import os
import sys
import re
import subprocess
import click
from pprint import pprint as pp
import yaml
from pathlib import Path
import datetime
from collections import namedtuple
import tempfile
import gzip

from sink.config import Config
from sink.config import TestConfig
from sink.config import Color
from sink.config import Action
from sink.config import Project
from sink.db import DB
from sink.rsync import Transfer
from sink.ui import ui
from sink.ssh import SSH

# def get_servers(ctx, args, incomplete):
    # config = Config()
    # servers = config.data['servers']
    # return servers

CONTEXT_SETTINGS = {
    'help_option_names': ['-h', '--help'],
    # 'token_normalize_func': lambda x: x.lower(),
}
@click.group(context_settings=CONTEXT_SETTINGS)
def util():
    """Tools to manage project."""
    # global config
    # config = Config()

# --------------------------------- DB ---------------------------------
@util.command('db', context_settings=CONTEXT_SETTINGS)
@click.argument('action', type=click.Choice([i.value for i in Action]))
@click.argument('server', type=click.STRING)  # autocompletion=get_servers
@click.argument('sql-gz', type=click.Path(exists=True), required=False)
@click.option('-d', '--real', is_flag=True)
def database(action, sql_gz, server, real):
    """Overwrite a db with a gzipped sql file.

    \b
    ACTION: pull or put.
    SERVER: server name (defined in util.yaml).
    SQL-GZ: gziped sql file to upload.  Required if action is "put".

    When pulling, a gziped file name is created using the project
    name, the server name, the date and time.  It is created in the
    pulls_dir.  eg:

    \b
    pulls_dir/projectname-servername-20-01-01_01-01-01.sql.gz
    """
    db = DB(real=real)
    if action == Action.PULL.value:
        db.pull(server)
    elif action == Action.PUT.value:
        if not sql_gz:
            ui.error('When action is "put", SQL-GZ is required.')
        db.put(server, sql_gz)

# ------------------------------- Files -------------------------------
@util.command('file', context_settings=CONTEXT_SETTINGS)
@click.argument('action', type=click.Choice([i.value for i in Action]))
@click.argument('filename', type=click.Path(exists=True), required=True)
@click.argument('server', required=False)
@click.option('-d', '--real', '-r', is_flag=True)
@click.option('--extra-flags',
              help='extra flags to pass to rsync.')
def files(action, filename, server, real, extra_flags):
    """Push or pull a single file or directory from a remote server.

    \b
    ACTION: pull or put
    FILENAME: file/dir to be transfered.
    SERVER: server name, if not specified sink will use the default server."""

    f = Path(os.path.abspath(filename))
    xfer = Transfer(real)
    extra_flags = '' if not extra_flags else extra_flags

    if action == Action.PULL.value:
        xfer.pull(f, server, extra_flags)
    elif action == Action.PUT.value:
        xfer.put(f, server, extra_flags)

@util.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', required=False)
@click.option('--dry-run', '-d', is_flag=True,
              help='Do nothing, show the command only.')
def ssh(server, dry_run):
    """SSH into a server."""
    ssh = SSH()
    ssh.ssh(server=server, dry_run=dry_run)

@util.command('diff', context_settings=CONTEXT_SETTINGS)
@click.argument('filename', type=click.Path(exists=True), required=True)
@click.argument('server', required=False)
@click.option('--ignore-whitespace', '-i', is_flag=True,
              help='Ignore whitespace in diff.')
@click.option('--difftool', '-d', is_flag=True,
              help='Use meld instead of "git diff".')
def diff_files(filename, server, ignore_whitespace, difftool):
    """Diff a local and remote file.

    \b
    FILENAME: file to be transfered
    SERVER: server name (defined in sink.yaml)."""

    fx = Path(os.path.abspath(filename))
    xfer = Transfer(True)
    xfer.diff(fx, server, ignore=ignore_whitespace, difftool=difftool)

# ------------------------------- Misc --------------------------------

@util.group(context_settings=CONTEXT_SETTINGS)
def misc():
    """Misc stuff."""

@misc.command(context_settings=CONTEXT_SETTINGS)
@click.argument('keys', nargs=-1, required=True)
def api(keys):
    '''Retrieve information from the config file.

    Some examples

    \b
    To get the project name:
      sink misc api project name

    \b
    To get the 2nd excluded filename:
      sink misc api project exclude 1

    \b
    To get the dev servers user name:
      sink misc api servers dev user
    '''
    config = Config(suppress_config_location=True)
    data = config.data

    for k in keys:
        try:
            k = int(k)
        except ValueError:
            # could not convert to an int, continue on as string.
            pass

        try:
            data = data[k]
        except KeyError:
            ui.error(f'key "{k}" does not exist in config.')

    click.echo(data)

# @misc.command(context_settings=CONTEXT_SETTINGS)
# @click.argument('root')
# def roots(root):
#     """"""
#     # config = Config()
#     projects = Project()
#     match = projects.first_match(root)
#     click.echo(match)

@misc.command(context_settings=CONTEXT_SETTINGS)
def test():
    """Test settings in config"""
    tc = TestConfig()
    # tc.test_project()
    tc.test_servers()

@misc.command(context_settings=CONTEXT_SETTINGS)
@click.argument('servers', nargs=-1)
def generate_config(servers):
    """Create a blank config

    The servers arg will create an entry for each server name given.

    \b
    To write the config to a file use:
    `hurl generate_config > hurl.yaml`
    """
    blank_config = '''
      project:
        # used for db pull file name (as well as the server id).
        name:
        # dir to put pulled db's in.
        pulls_dir:
        root:
        # these files will be excluded from any dir syncing.
        exclude:
          - .well-known
          - '*.sass'
          - '*.scss'
          - '.sass-cache'
          - storage/runtime

      servers:'''
    if not servers:
        servers = ['example_server']
    for server in servers:
        blank_config = blank_config + f'''
        {server}:
          name: {server.upper()}  # this is used for the pulled filename.
          root:
          warn: yes  # this will warn you when puting multiple files to this server.
          default: no
          note: |
          control_panel:
            url:
            username:
            password:
            note: |
          ssh:
            username:
            password:
            server:
            key:
            port:
            note: |
          hosting:
            name:
            url:
            username:
            password:
            note: |
          mysql:
            - username:
              password:
              db:
              hostname:
              note: |
          urls:
            - url:
              admin_url:
              username:
              password:
              note: |
            - url:
              admin_url:
              username:
              password:
              note: |
        '''

    blank_config = blank_config.split('\n')
    blank_config = '\n'.join([i[6:] for i in blank_config])
    click.echo(blank_config)


if __name__ == '__main__':
    try:
        util()
    except KeyboardInterrupt:
        sys.exit(1)

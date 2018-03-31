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
from sink.db import DB
from sink.rsync import Transfer
from sink.ui import ui
from sink.ssh import SSH

def get_servers(ctx, args, incomplete):
    config = Config()
    servers = config.data['servers']
    return servers

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
@util.command(context_settings=CONTEXT_SETTINGS)
@click.argument('action', type=click.Choice([i.value for i in Action]))
@click.argument('sync-point')  # autocompletion=get_sync_points
@click.argument('server')
@click.option('-d', '--real', is_flag=True)
def rsync(action, sync_point, server, real):
    """Rsync files to and fro.

    \b
    ACTION: pull or put
    SYNC-POINT: name of dir to sync (defined in util.yaml).
    SERVER: server name (defined in util.yaml).
    """
    files = Transfer(real)
    if action == Action.PULL.value:
        files.pull(sync_point, server)
    elif action == Action.PUT.value:
        files.put(sync_point, server)

@util.command(context_settings=CONTEXT_SETTINGS)
@click.argument('action', type=click.Choice([i.value for i in Action]))
@click.argument('filename', type=click.Path(exists=True), required=True)
@click.argument('server', required=False)
@click.option('--dry-run', '-d', is_flag=True,
              help='Do nothing, show the command only.')
def single(action, filename, server, dry_run):
    """Push or pull a single file to a remote server.

    \b
    ACTION: pull or put
    FILENAME: file to be transfered
    SERVER: server name (defined in sink.yaml)."""
    real = True
    if dry_run:
        real = False
    f = Path(os.path.abspath(filename))
    files = Transfer(real)

    if action == Action.PULL.value:
        files.single_pull(f, server)
    elif action == Action.PUT.value:
        files.single_put(f, server)

@util.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', required=False)
@click.option('--dry-run', '-d', is_flag=True,
              help='Do nothing, show the command only.')
def ssh(server, dry_run):
    """SSH into a server."""
    ssh = SSH()
    ssh.ssh(server=server, dry_run=dry_run)

@util.command(context_settings=CONTEXT_SETTINGS)
@click.argument('filename', type=click.Path(exists=True), required=True)
@click.argument('server', required=False)
@click.option('--dry-run', '-d', is_flag=True,
              help='Do nothing, show the command only.')
def diff(filename, server, dry_run):
    """Diff a local and remote file.

    \b
    FILENAME: file to be transfered
    SERVER: server name (defined in sink.yaml)."""
    pass

# ------------------------------- Misc --------------------------------

@util.command(context_settings=CONTEXT_SETTINGS)
@click.option('--show-passwords', '-s', is_flag=True,
              help='Show the passwords instead of ***.')
def info(show_passwords):
    """Show all of the projects info."""
    pass

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

def key_get(data, keys):
    for k in keys:
        data = data[k]

# @misc.command(context_settings=CONTEXT_SETTINGS)
# def clearassets():
#     commercial_docs = 'maccom/macdonaldcommercial.com/html/docs/listings/'
#     commercial_listings = 'maccom/macdonaldcommercial.com/html/img/listings/'
#     pm_listings = ''

# @misc.command(context_settings=CONTEXT_SETTINGS)
# @click.argument('log-name', required=False)
# def viewlog(log_name):
#     """List log files.

#     If LOG-NAME is passed, load that file into multitail.
#     """
#     c = Config()
#     p = c.project()
#     log_dir = os.path.abspath(p.log_dir)
#     os.chdir(log_dir)
#     ui.display_cmd(log_dir)
#     if not log_name:
#         cmd = 'ls -lh'
#         subprocess.run(cmd, shell=True)
#     else:
#         cmd = f'''multitail -x 'Logging window' -cS craft -ev '^in ' \
#                   -ke '^.*\[plugin\] ' -n 1000 {log_name}'''
#         subprocess.run(cmd, shell=True)

# @misc.command(context_settings=CONTEXT_SETTINGS)
# def clearcache():
#     c = Config()
#     p = c.project()
#     cache_dir = os.path.abspath(p.cache_dir)
#     cmd = f'ls "{cache_dir}" | wc -l'
#     ui.display_cmd(cmd)
#     subprocess.run(cmd, shell=True)
#     delcmd = f'rm "{cache_dir}/"*'
#     ui.display_cmd(delcmd)
#     subprocess.run(delcmd, shell=True)

@misc.command(context_settings=CONTEXT_SETTINGS)
def test():
    """Test settings in config"""
    tc = TestConfig()
    tc.test_project()
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
        # used for db pull file name (as well as the server id)
        name:
        # dir to put pulled db's in
        pulls_dir:
        # dir that contains logs that can be viewed
        log_dir:
        # dir with cached data that can be deleted
        cache_dir:
        # dir that matches root in the servers section.  Every thing
        # below this must be exaxtly the same on each server.
        root:
        exclude:
          - .well-known
          - '*.sass'
          - '*.scss'
          - '.sass-cache'
          - storage/runtime

      # sync points are named dir's which can be synced.
      sync points:
        test: dir/dir/

      servers:'''
    if not servers:
        servers = ['example_server']
    for server in servers:
        blank_config = blank_config + f'''
        {server}:
          user:
          password:
          server:
          mysql_user:
          mysql_password:
          mysql_db:
          root:
          id: {server.upper()}
          warn: yes'''

    blank_config = blank_config.split('\n')
    blank_config = '\n'.join([i[6:] for i in blank_config])
    click.echo(blank_config)


if __name__ == '__main__':
    try:
        util()
    except KeyboardInterrupt:
        sys.exit(1)

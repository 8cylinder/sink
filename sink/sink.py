#!/usr/bin/env python3
import os
import click
from pprint import pprint as pp
from pathlib import Path
import datetime

from sink.config import config
from sink.config import Color
from sink.config import Action
from sink.check import TestConfig
from sink.db import DB
from sink.rsync import Transfer
from sink.ui import ui
from sink.ssh import SSH
from sink.applications import Applications
from sink.init import Init
from sink.deploy import DeployViaSymlink
from sink.deploy import DeployViaRename
from sink.actions import Actions


# from IPython import embed
# embed()

def get_servers(ctx, args, incomplete):
    config.load_config()
    servers = [i.name for i in config.servers() if i.name.startswith(incomplete)]
    return servers

__version__ = '0.1.0'

CONTEXT_SETTINGS = {
    'help_option_names': ['-h', '--help'],
    # 'token_normalize_func': lambda x: x.lower(),
}
@click.group(context_settings=CONTEXT_SETTINGS)
@click.option('-s', '--suppress-commands', is_flag=True,
              help="Don't display the bash commands used.")
def sink(suppress_commands):
    """🐙 Tools to manage projects."""
    config.suppress_commands = suppress_commands
    config.load_config()

# --------------------------------- DB ---------------------------------
@sink.command('db', context_settings=CONTEXT_SETTINGS)
@click.argument('action', type=click.Choice([i.value for i in Action]))
@click.argument('server', type=click.STRING, autocompletion=get_servers)
@click.argument('sql-gz', type=click.Path(exists=True), required=False)
@click.option('--real', '-r', is_flag=True)
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
@sink.command('file', context_settings=CONTEXT_SETTINGS)
@click.argument('action', type=click.Choice([i.value for i in Action]))
# @click.argument('filename', type=click.Path(exists=True), required=True)
@click.argument('server', autocompletion=get_servers)
@click.argument('filename', type=click.Path(), required=True)
@click.option('--real', '-r', is_flag=True)
@click.option('--silent', '-s', is_flag=True,
              help='Zero output, for use in Emacs.')
@click.option('--extra-flags',
              help='extra flags to pass to rsync.')
def files(action, filename, server, real, silent, extra_flags):
    """Send files to and fro.

    Push or pull a single file or directory from a remote server.

    \b
    ACTION: pull or put
    FILENAME: file/dir to be transfered.
    SERVER: server name, if not specified sink will use the default server."""

    f = Path(os.path.abspath(filename))
    xfer = Transfer(real, silent=silent)
    extra_flags = '' if not extra_flags else extra_flags

    if action == Action.PULL.value:
        xfer.pull(f, server, extra_flags)
    elif action == Action.PUT.value:
        xfer.put(f, server, extra_flags)

@sink.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.option('--dry-run', '-d', is_flag=True,
              help='Do nothing, show the command only.')
def ssh(server, dry_run):
    """SSH into a server."""
    ssh = SSH()
    ssh.ssh(server=server, dry_run=dry_run)

@sink.command('diff', context_settings=CONTEXT_SETTINGS)
@click.argument('filename', type=click.Path(exists=True), required=True)
@click.argument('server', autocompletion=get_servers)
@click.option('--ignore-whitespace', '-i', is_flag=True,
              help='Ignore whitespace in diff.')
@click.option('--difftool', '-d', is_flag=True,
              help='Use meld instead of "git diff".')
@click.option('--word-diff', '-w', type=click.Choice(['word', 'letter']),
              help='Refine diffs to word or letter differences.')
def diff_files(filename, server, ignore_whitespace, word_diff, difftool):
    """Diff a local and remote file.

    \b
    FILENAME: file to be transfered
    SERVER: server name (defined in sink.yaml)."""

    fx = Path(os.path.abspath(filename))
    xfer = Transfer(True)
    xfer.diff(fx, server, ignore=ignore_whitespace,
              word_diff=word_diff, difftool=difftool)

@sink.command(context_settings=CONTEXT_SETTINGS)
@click.option('--view/--edit', '-v/-e', default=True,
              help='View or edit config file.')
def info(view):
    """View or edit the config file.

    If edit, it will be opened in the default editor.

    To config the default editor, add the following lines to
    ~/.bashrc.  Change the 'program' to editor name.

    \b
    export EDITOR='program'
    export VISUAL='program'
    """
    if view:
        with open(config.config_file) as f:
            contents = f.read()
            click.echo_via_pager(contents)
    else:
        click.edit(filename=config.config_file)

@sink.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server-names', nargs=-1)
@click.option('--required', '-r', is_flag=True)
def check(required, server_names):
    """Test server settings in config."""
    if server_names:
        server_names = [i.lower() for i in server_names]
    tc = TestConfig()
    if required:
        tc.test_requirements()
    else:
        tc.test_servers(server_names)

# ------------------------------- Deploy ------------------------------

DEPLOYTYPE = 'rename'
# DEPLOYTYPE = 'symlink'
@sink.group(context_settings=CONTEXT_SETTINGS)
def deploy():
    """Deploy site to server with rollback.

    Each deploy after init will be hard-linked to the previous deploy.
    Each deploy's dir will be have the format YY-MM-DD-HH-MM-SS."""

@deploy.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.argument('dirs', nargs=-1)
def init(server, dirs):
    """Initialize and setup a deploy.

    Create a dir to hold the uploaded versions, and create a symlink
    to it.

    This command only outputs commands to be copied and pasted.
    """

    if DEPLOYTYPE == 'rename':
        deploy = DeployViaRename(server, real=True)
        deploy.init_deploy(*dirs)
    elif DEPLOYTYPE == 'symlink':
        deploy = DeployViaSymlink(server, real=True)
        deploy.init_deploy()
    else:
        ui.error('deploy type wrong')

@deploy.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.option('--real', '-r', is_flag=True)
@click.option('--quiet', '-q', is_flag=True,
              help='No itemized output from rsync.')
@click.option('-d', '--dump-db', is_flag=True,
              help='Take a snapshot of the db.')
def new(server, real, quiet, dump_db):
    """Upload a new version of the site.

    Upload a new version to the deploy root.  Also a snapshot of the
    db is put in the root dir."""

    if DEPLOYTYPE == 'rename':
        deploy = DeployViaRename(server, real=real)
        deploy.new()
    elif DEPLOYTYPE == 'symlink':
        deploy = DeployViaSymlink(server, real=real)
        deploy.new(dump_db=dump_db)
    else:
        ui.error('deploy type wrong')

@deploy.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.option('--real', '-r', is_flag=True)
@click.option('-l', '--load-db', is_flag=True,
              help='Take a snapshot of the db.')
def switch(server, real, load_db):
    """Change the symlink to point to a different dir in the deploy root."""

    if DEPLOYTYPE == 'rename':
        deploy = DeployViaRename(server, real=real)
    elif DEPLOYTYPE == 'symlink':
        deploy = DeployViaSymlink(server, real=real)
        deploy.change_current(load_db=load_db)
    else:
        ui.error('deploy type wrong')


# ------------------------------- Actions -------------------------------
@sink.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.argument('action_name', required=False)
@click.option('--real', '-r', is_flag=True)
def action(server, action_name, real):
    '''Run a pre defined command on the server.

    If a section named 'actions' is in sink.yaml, run the requested
    action or list the available actions for that server.

    For example, add the following to one of the servers.  It will
    list all files ending in .cache on the requested server.

    \b
    actions:
      find-cache: find -iname '*.cache'

    Instead of using one of the servers, you can use the special name
    'local' for a server.  This will use the commands in the project
    section.

    '''
    actions = Actions(server, real)
    if action_name:
        actions.run(action_name)
    else:
        actions.list_actions()

# ------------------------------- Misc --------------------------------

@sink.group(context_settings=CONTEXT_SETTINGS)
def misc():
    """Misc stuff."""


@misc.command(context_settings=CONTEXT_SETTINGS)
@click.argument('keys', nargs=-1, required=True)
def api(keys):
    '''Retrieve information from the config file.

    The data will be output as json.

    Some examples:

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
        except IndexError as e:
            ui.error(str(e))
    import json
    click.echo(json.dumps(data))


@misc.command(context_settings=CONTEXT_SETTINGS)
def pack():
    """Display a command to gzip uncommited files."""
    now = datetime.datetime.now()
    now = now.strftime('%y-%m-%d-%H-%M-%S')

    tarname = f'changed-{config.project().name}-{now}.tar.gz'
    cmd = f'git ls-files -mz | xargs -0 tar -czvf {tarname}'
    cmd = click.style(cmd, bold=True)
    title = click.style('Run:', fg=Color.YELLOW.value)
    click.echo(f'{title} {cmd}')


@misc.command('init', context_settings=CONTEXT_SETTINGS)
@click.argument('servers', nargs=-1)
def init_config(servers):
    """Create a blank config.

    The servers arg will create an entry for each server name given.

    \b
    To write the config to a file use:
    `sink misc init > sink.yaml`
    `sink misc init dev stag prod > sink.yaml`
    """
    init = Init()
    init.servers(servers)
    click.echo(init.create())


@misc.command(context_settings=CONTEXT_SETTINGS)
@click.argument('application', required=False)
def settings(application):
    """Output settings values for the requested application.

    For the requested application, output settings in a format thats
    easy to copy & paste.
    """

    app = Applications()
    if not app.name(application):
        click.echo(f'Unknown application: {application}')
        click.echo(f'Known are: {app.known()}')
    else:
        click.echo(app.app_settings())

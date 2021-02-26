#!/usr/bin/env python3
import os
# noinspection PyUnresolvedReferences
from pprint import pprint as pp
from pathlib import Path
import datetime
from collections import OrderedDict
import yaml
from enum import Enum
import click

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
from sink.deploy import DeployViaLocal
from sink.actions import Actions


# from IPython import embed
# embed()

def get_servers(ctx, args, incomplete):
    config.load_config()
    servers = [i.name for i in config.servers() if i.name.startswith(incomplete)]
    # if not servers:
    #     ui.error('no servers defined (you are probably not in a project)')
    return servers


# def get_server_choices():
#     try:
#         config.load_config(raise_err=True)
#     except FileNotFoundError:
#         return ["SERVER"]
#     return [i.name for i in config.servers()]


class NaturalOrderGroup(click.Group):
    """Display commands sorted by order in file

    When using -h, display the commands in the order
    they are in the file where they are defined.

    https://github.com/pallets/click/issues/513
    """
    def list_commands(self, ctx):
        return self.commands.keys()


__version__ = '0.1.0'

CONTEXT_SETTINGS = {
    'help_option_names': ['-h', '--help'],
    # 'token_normalize_func': lambda x: x.lower(),
}


@click.group(context_settings=CONTEXT_SETTINGS, cls=NaturalOrderGroup)
@click.option('-s', '--suppress-commands', is_flag=True,
              help="Don't display the bash commands used.")
def sink(suppress_commands):
    """🐙 Tools to manage projects.

    Use `sink COMMAND -h` for help on specific commands.
    """
    config.suppress_commands = suppress_commands


# --------------------------------- DB ---------------------------------
@sink.command('db', context_settings=CONTEXT_SETTINGS)
@click.argument('db-action', type=click.Choice([i.value for i in Action]))
# @click.argument('server', type=click.Choice(get_server_choices()), autocompletion=get_servers)
@click.argument('server', type=click.STRING, autocompletion=get_servers)
@click.argument('sql-gz', type=click.Path(exists=True), required=False)
@click.option('--tag', '-t', type=click.STRING,
              help="Add a tag to the generated filename when pulling.")
@click.option('--real', '-r', is_flag=True)
@click.option('--quiet', '-q', is_flag=True,
              help='Return only the filename')
def database(db_action, sql_gz, server, real, quiet, tag):
    """Overwrite a db with a gzipped sql file.

    \b
    ACTION: pull or put.
    SERVER: server name (defined in util.yaml).
    SQL-GZ: gzipped sql file to upload.  Required if action is "put".

    When pulling, a gzipped file name is created using the project
    name, the server name, the date and time.  It is created in the
    pulls_dir.  eg:

    \b
    pulls_dir/projectname-servername-20-01-01_01-01-01.sql.gz
    """
    config.load_config()
    db = DB(real=real, quiet=quiet)
    if db_action == Action.PULL.value:
        db.pull(server, tag=tag)
    elif db_action == Action.PUT.value:
        if not sql_gz:
            ui.error('When action is "put", SQL-GZ is required.')
        db.put(server, sql_gz)


# ------------------------------- Files -------------------------------
@sink.command('file', context_settings=CONTEXT_SETTINGS)
@click.argument('action', type=click.Choice([i.value for i in Action]))
@click.argument('server', autocompletion=get_servers)
@click.argument('filename', type=click.Path(), required=False)
@click.option('--real', '-r', is_flag=True)
@click.option('--silent', '-s', is_flag=True,
              help='Reduced output, for use in Emacs.')
@click.option('--extra-flags',
              help='extra flags to pass to rsync.')
def files(action, filename, server, real, silent, extra_flags):
    """Send files to and fro.

    Push or pull a single file or directory from a remote server.

    \b
    ACTION: pull or put
    SERVER: server name, if not specified sink will use the default server.
    FILENAME: file/dir to be transfered."""

    if filename and action == Action.PUT.value and not os.path.exists(filename):
        ui.error(f'Path does not exist: {filename}')

    config.load_config()
    if filename:
        f = Path(os.path.abspath(filename))
    else:
        prj = config.project()
        f = Path(prj.root)

    xfer = Transfer(real, silent=silent)
    extra_flags = '' if not extra_flags else extra_flags

    if action == Action.PULL.value:
        xfer.pull(f, server, extra_flags)
    elif action == Action.PUT.value:
        xfer.put(f, server, extra_flags)


@sink.command('single', context_settings=CONTEXT_SETTINGS)
@click.argument('filename', type=click.Path(), required=True)
@click.option('--real', '-r', is_flag=True)
@click.option('--silent', '-s', is_flag=True,
              help='Reduced output, for use in Emacs.')
def automatic(filename, real, silent):
    """Send a single file to any server marked as automatic.

    Send a single file to any server that has been designated as
    automatic.  This is primarily designed for scripting from a text
    editor."""

    config.load_config()
    f = Path(os.path.abspath(filename))
    xfer = Transfer(real, silent=silent)
    xfer.single(f)


@sink.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.option('--dry-run', '-d', is_flag=True,
              help='Do nothing, show the command only.')
def ssh(server, dry_run):
    """SSH into a server."""
    config.load_config()
    ssh = SSH()
    ssh.ssh(server=server, dry_run=dry_run)


@sink.command('diff', context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.argument('filename', type=click.Path(exists=True), required=False)
@click.option('--ignore-whitespace', '-i', is_flag=True,
              help='Ignore whitespace in diff.')
@click.option('--difftool', '-d', is_flag=True,
              help='Use meld instead of "git diff".')
@click.option('--word-diff', '-w', type=click.Choice(['word', 'letter']),
              help='Refine diffs to word or letter differences.')
def diff_files(filename, server, ignore_whitespace, word_diff, difftool):
    """Diff a local and remote file.

    \b
    FILENAME: file to be transferred
    SERVER: server name (defined in sink.yaml)."""

    config.load_config()

    if not filename:
        prj = config.project()
        filename = Path(prj.root)
    fx = Path(os.path.abspath(filename))
    xfer = Transfer(True)
    xfer.diff(fx, server, ignore=ignore_whitespace,
              word_diff=word_diff, difftool=difftool)


def edit_config():
    click.edit(filename=config.config_file)
    try:
        with open(config.config_file) as f:
            yaml.safe_load(f)
    except yaml.YAMLError as e:
        if hasattr(e, 'problem_mark'):
            msg = 'There was an error while parsing the config file'
            if e.context is not None:
                ui.error(
                    f'{msg}:\n{e.problem_mark}\n{e.problem} {e.context}.',
                    exit=False)
            else:
                ui.error(
                    f'{msg}:\n{e.problem_mark} {e.problem}.', exit=False)
        else:
            ui.error(
                "Something went wrong while parsing the yaml file.",
                exit=False)

        re_edit = click.confirm(
            '\nDo you want to edit the file again?', default=True)

        if re_edit:
            edit_config()


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
    config.load_config()
    if view:
        with open(config.config_file) as f:
            contents = f.read()
            click.echo_via_pager(contents)
    else:
        edit_config()


@sink.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server-names', nargs=-1)
@click.option('--required', '-r', is_flag=True)
def check(required, server_names):
    """Test server settings in config."""
    config.load_config()
    if server_names:
        server_names = [i.lower() for i in server_names]
    tc = TestConfig()
    if required:
        tc.test_requirements()
    else:
        tc.test_servers(server_names)


# ------------------------------- Actions -------------------------------
@sink.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.argument('action_name', required=False)
@click.option('--real', '-r', is_flag=True)
def action(server, action_name, real):
    """Run a pre defined command on the server.

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

    If no action is specified, all actions available to that server
    will be listed.
    """
    config.load_config()
    actions = Actions(server, real)
    if action_name:
        actions.run(action_name)
    else:
        actions.list_actions()


# ------------------------------- Deploy ------------------------------

class DeployType(Enum):
    RENAME = 'rename'
    SYMLINK = 'symlink'
    LOCAL = 'local'


@sink.group(context_settings=CONTEXT_SETTINGS, cls=NaturalOrderGroup)
@click.option('-m', '--method', default=DeployType.LOCAL.value,
              type=click.Choice([i.value for i in DeployType]),
              help=f"Deploy method, default {DeployType.LOCAL.value}")
@click.pass_context
def deploy(ctx, method):
    """[Group] Deploy site to server with rollback."""
    ctx.obj = DeployType(method)


@deploy.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.argument('dirs', nargs=-1)
@click.pass_context
def init(ctx, server, dirs):
    """Initialize and setup a deploy.

    Create a dir localy or on the remote server to hold the versions.
    The exact method depends of the deploy method used."""

    deploytype = DeployType(ctx.obj)

    config.load_config()
    if deploytype == DeployType.RENAME:
        init_deploy = DeployViaRename(server, real=True)
        init_deploy.init_deploy(*dirs)
    elif deploytype == DeployType.SYMLINK:
        init_deploy = DeployViaSymlink(server, real=True)
        init_deploy.init_deploy()
    elif deploytype == DeployType.LOCAL:
        deploy = DeployViaLocal()
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
@click.option('-n', '--note', help="Add a note to DEPLOY_INFO.yaml.")
@click.pass_context
def new(ctx, server, real, quiet, dump_db, note):
    """Upload a new version of the site.

    Upload a new version to the deploy root."""

    deploytype = DeployType(ctx.obj)

    config.load_config()
    if deploytype == DeployType.RENAME:
        new_deploy = DeployViaRename(server, real=real)
        new_deploy.new()
    elif deploytype == DeployType.SYMLINK:
        new_deploy = DeployViaSymlink(server, real=real)
        new_deploy.new(dump_db=dump_db)
    elif deploytype == DeployType.LOCAL:
        deploy = DeployViaLocal()
        deploy.new(server, real=real, note=note)
    else:
        ui.error('deploy type wrong')


@deploy.command(context_settings=CONTEXT_SETTINGS)
@click.argument('server', autocompletion=get_servers)
@click.option('--real', '-r', is_flag=True)
@click.option('-l', '--load-db', is_flag=True,
              help='Take a snapshot of the db.')
@click.option('--delete', is_flag=True,
              help='Delete any files on remote server that are not part of the upload.')
@click.pass_context
def switch(ctx, server, real, load_db, delete):
    """Change the symlink to point to a different dir in the deploy root."""

    deploytype = DeployType(ctx.obj)

    config.load_config()
    if deploytype == DeployType.RENAME:
        deploy = DeployViaRename(server, real=real)
    elif deploytype == DeployType.SYMLINK:
        deploy = DeployViaSymlink(server, real=real)
        deploy.change_current(load_db=load_db)
    elif deploytype == DeployType.LOCAL:
        deploy = DeployViaLocal()
        deploy.change_current(server, real=real, delete=delete)
    else:
        ui.error('deploy type wrong')


# ------------------------------- Misc --------------------------------

@sink.group(context_settings=CONTEXT_SETTINGS, cls=NaturalOrderGroup)
def misc():
    """[Group] Misc stuff."""


@misc.command(context_settings=CONTEXT_SETTINGS)
@click.argument('keys', nargs=-1, required=True)
@click.option('--json/--no-json', '-j/-n', default=True,
              help='Return the data as JSON instead of the default python output.')
def api(keys, json):
    """Retrieve information from the config file.

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
    """
    config.load_config()
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
    if json:
        import json
        click.echo(json.dumps(data))
    else:
        click.echo(data)


@misc.command(context_settings=CONTEXT_SETTINGS)
def pack():
    """Display a command to gzip uncommitted files."""
    config.load_config()
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
    init_file = Init()
    init_file.servers(servers)
    click.echo(init_file.create())


@misc.command(context_settings=CONTEXT_SETTINGS)
@click.argument('application', required=False)
def settings(application):
    """Output settings values for the requested application.

    For the requested application, output settings in a format thats
    easy to copy & paste.
    """
    config.load_config()
    app = Applications()
    if not app.name(application):
        click.echo(f'Unknown application: {application}')
        click.echo(f'Known are: {app.known()}')
    else:
        click.echo(app.app_settings())

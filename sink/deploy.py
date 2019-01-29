import os
import sys
import re
import subprocess
import datetime
import click
import string
from pathlib import Path
from pprint import pprint as pp

from sink.config import config
from sink.config import Action
from sink.ui import Color
from sink.ui import ui
from sink.rsync import Transfer
from sink.ssh import SSH
from sink.db import DB


# https://gist.github.com/datagrok/3807742
# rsync --link-dest

class Deploy:
    def __init__(self, servername, real=False, quiet=False, suppress_command=False):
        self.p = config.project()
        self.s = config.server(servername)
        if not self.s.deploy_root:
            ui.error(f'deploy_root not set in sink.yaml for {self.s.name}')
        self.real = real
        self.rsync = Transfer(real)
        self.stamp = self.server_time(self.s)
        self.quiet = quiet

    def init_deploy(self):
        """Display bash commands to set up for deploy

        Write to the console two bash commands to be run on the remote
        server to set up the directories for using hardlinks.

        The first command renames the <root> directory to
        <root>.<timestamp>

        The second creates a symlink with the original <root> directory
        name that points to the new <root>.<timestamp>.original dir.
        """
        click.secho(f'\nOn remote server ({self.s.name}) run:', bold=True)
        ui.display_cmd(f'mkdir {self.s.deploy_root}')
        ui.display_cmd(f'sudo mv {self.s.root} {self.s.deploy_root}/{self.stamp}')
        ui.display_cmd(f'sudo ln -s {self.s.deploy_root}/{self.stamp} {self.s.root}')

    def new(self, dump_db=False):
        """Create a new dir for a future deploy

        It will be created in the server's deploy_root config location.
        """
        dry_run = True if not self.real else False

        deploy_dest = os.path.join(self.s.deploy_root, self.stamp)
        if not deploy_dest.startswith('/'):
            ui.error('Deploy root must be an absolute path.')
        ssh = SSH()
        cmd = f"'mkdir {deploy_dest}'"
        ssh.run(cmd, dry_run=dry_run, server=self.s.name.lower())
        deploy_dest_pretty = click.style(deploy_dest, fg='green')
        click.secho(f'\nNew dir created: {deploy_dest_pretty}')

        xfer = Transfer(self.real, quiet=self.quiet)
        xfer.multiple = True
        local_root = f'{self.p.root}/'
        xfer._rsync(local_root, deploy_dest, self.s.name.lower(), Action.PUT)

        if dump_db:
            db = DB(real=self.real)
            dump_file = os.path.join(deploy_dest, 'DB-DUMP.sql.gz')
            db.dump_remote(dump_file, self.s.name.lower())


    def change_current(self):
        """Change the symlink destination"""
        ssh = SSH()
        dry_run = True if not self.real else False
        deploy_base = Path(self.s.root).parts[-1]
        cmd = f"'find {self.s.deploy_root}/{deploy_base}* -maxdepth 0'"
        result = ssh.run(cmd, server=self.s.name.lower()).strip()

        active_cmd = f'readlink --verbose {self.s.root}'
        active = ssh.run(active_cmd, server=self.s.name.lower())
        active = active.strip()
        active = Path(active).parts[-1].strip()

        data = {}
        for letter, full_filename in zip(string.ascii_lowercase, result.split('\n')):
            data[letter] = full_filename

        click.echo()
        # pointer = '->'
        pointer = '▶'
        pointer_pretty = click.style(pointer, fg='green', bold=True)
        click.echo(f'Select a letter to change the symlink to.  The {pointer_pretty} indicates')
        click.echo('the dir that the symlink currently points to.')
        click.echo()
        for letter, full_filename in data.items():
            filename = Path(full_filename).parts[-1]
            indicator = ' ' * len(pointer)
            if filename == active:
                indicator = pointer_pretty
            pretty_date = datetime.datetime.strptime(filename, 'www.%y-%m-%d_%H%M%S_%Z')
            pretty_date = pretty_date.strftime('%b %d/%Y, %I:%M%p %Z').strip()
            pretty_date = click.style(f'({pretty_date})', dim=True, fg='green')
            full_filename = click.style(full_filename, bold=True)
            indicator = click.style(indicator, fg='red', bold=True)
            letter = click.style(f'{letter})', fg='green', bold=True)
            click.echo(f'{indicator} {letter} {full_filename} {pretty_date}')

        msg = click.style('Select a dir to link to (ctrl-c to abort)', fg='white')
        choice = click.prompt(msg)
        link_cmd = f"'sudo test -h {self.s.root} && sudo ln -sfn {data[choice]} {self.s.root}'"
        r = ssh.run(link_cmd, dry_run=dry_run, server=self.s.name.lower())

        click.echo()
        ui.display_success(self.real)




    def server_time(self, server):
        """Retrieve the remote server time"""
        dry_run = True if not self.real else False
        ssh = SSH()
        s_time = ssh.run('date "+%y-%m-%d_%H%M%S_%Z"', dry_run=False,
                         server=self.s.name.lower())
        s_time = s_time.strip()
        deploy_name = Path(self.s.root).parts[-1]
        stamp = f"{deploy_name}.{s_time}"
        return stamp

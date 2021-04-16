import os
import sys
import re
import subprocess
import datetime
import click
import string
import uuid
from pathlib import Path
from pprint import pprint as pp
import yaml
import tempfile
import coolname
import glob

from sink.config import config
from sink.config import Action
from sink.ui import Color
from sink.ui import ui
from sink.rsync import Transfer
from sink.ssh import SSH
from sink.db import DB
from sink.rsync import Transfer


class DeployViaRename:
    def __init__(self, servername, real=False, quiet=False):
        self.ssh = SSH()
        self.p = config.project()
        self.s = config.server(servername)
        if not self.s.deploy_root:
            ui.error(f'deploy_root not set in sink.yaml for {self.s.servername}')
        self.real = real
        self.rsync = Transfer(real)
        self.stamp = self._server_time(self.s)
        self.date_file = f'SINK-DATE:{self.stamp}'
        self.quiet = quiet

    def init_deploy(self, *dirs):
        click.secho(f'\nOn remote server ({self.s.servername}) run:', bold=True)
        deploy_dir = Path(self.s.deploy_root, self.stamp)
        date_file = deploy_dir / self.date_file
        if not dirs:
            dirs = ['{{DIR}}']
        cmds = [
            f'mkdir -p {date_file.parent}',
            f'touch {date_file}',
        ]
        for d in dirs:
            d = Path(d)
            deploy_sub_dir = deploy_dir / d.name
            cmds += [
                '',
                f'cp -r {d} {deploy_sub_dir}',
                f'mv {d} {d}.orig',
                f'ln -s {deploy_sub_dir} {d}',
            ]
        for cmd in cmds:
            ui.display_cmd(cmd)

    def new(self):
        """Create a new deploy dir and upload the project

        It will be created in the server's deploy_root config location.
        """
        dry_run = True if not self.real else False

        deploy_dest = os.path.join(self.s.deploy_root, self.stamp)
        if not deploy_dest.startswith('/'):
            ui.error('Deploy root must be an absolute path.')

        ssh = self.ssh
        # cmd = f"'mkdir {deploy_dest} && chown :{self.s.group} {deploy_dest}'"
        cmd = f"'mkdir {deploy_dest}'"
        ssh.run(cmd, dry_run=dry_run, server=self.s.servername)
        click.echo('\nNew dir created: {}'.format(click.style(deploy_dest, fg='green')))

        ssh.run(f'touch {self.s.deploy_root}/{self.stamp}/{self.date_file}', dry_run=dry_run, server=self.s.servername)

        xfer = Transfer(self.real, quiet=self.quiet)
        xfer.multiple = True
        local_root = f'{self.p.root}/'
        xfer._rsync(local_root, deploy_dest, self.s.servername, Action.PUT)

    def change_current(self, load_db=False):
        pass

    def _server_time(self, server):
        """Retrieve the remote server time"""
        dry_run = True if not self.real else False
        ssh = self.ssh
        s_time = ssh.run('date "+%y-%m-%d_%H%M%S_%Z"', dry_run=False,
                         server=self.s.servername)
        s_time = s_time.strip()
        # deploy_name = Path(self.s.root).parts[-1]
        # stamp = f"{deploy_name}.{s_time}"
        stamp = f"{s_time}"
        return stamp


class DeployViaSymlink:
    def __init__(self, servername, real=False, quiet=False):
        self.ssh = SSH()
        self.p = config.project()
        self.s = config.server(servername)
        if not self.s.deploy_root:
            ui.error(f'deploy_root not set in sink.yaml for {self.s.servername}')
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
        click.secho(f'\nOn remote server ({self.s.servername}) run:', bold=True)
        ui.display_cmd(f'mkdir {self.s.deploy_root}')
        ui.display_cmd(f'sudo mv {self.s.root} {self.s.deploy_root}/{self.stamp}')
        ui.display_cmd(f'sudo ln -s {self.s.deploy_root}/{self.stamp} {self.s.root}')

    def _get_active(self):
        active_cmd = f'readlink --verbose {self.s.root}'
        active = self.ssh.run(active_cmd, server=self.s.servername).strip()
        active = Path(active)
        return active

    def new(self, dump_db=False):
        """Create a new dir for a future deploy

        It will be created in the server's deploy_root config location.
        """
        dry_run = True if not self.real else False

        deploy_dest = os.path.join(self.s.deploy_root, self.stamp)
        if not deploy_dest.startswith('/'):
            ui.error('Deploy root must be an absolute path.')
        ssh = self.ssh
        # cmd = f"'mkdir {deploy_dest} && sudo chown {self.s.group}: {deploy_dest}'"
        cmd = f"'mkdir {deploy_dest} && chown :{self.s.group} {deploy_dest}'"
        ssh.run(cmd, dry_run=dry_run, server=self.s.servername)
        click.echo('\nNew dir created: {}'.format(click.style(deploy_dest, fg='green')))

        previous_dest = self._get_active()
        if dump_db:
            db = DB(real=self.real)
            dump_file = os.path.join(previous_dest, f'DB-DUMP-{self.stamp}.sql.gz')
            db.dump_remote(dump_file, self.s.servername)

        xfer = Transfer(self.real, quiet=self.quiet)
        xfer.multiple = True
        local_root = f'{self.p.root}/'
        compare_dir = f'--link-dest="{previous_dest}"'
        xfer._rsync(local_root, deploy_dest, self.s.servername, Action.PUT, extra_flags=compare_dir)

    def change_current(self, load_db=False):
        """Change the symlink destination"""
        ssh = self.ssh
        dry_run = True if not self.real else False
        deploy_base = Path(self.s.root).parts[-1]
        cmd = f"'find {self.s.deploy_root}/{deploy_base}* -maxdepth 0'"
        result = ssh.run(cmd, server=self.s.servername).strip()
        active = self._get_active()

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
            if filename == active.parts[-1]:
                indicator = pointer_pretty

            date_tail = filename.split('.')[-1]
            pretty_date = datetime.datetime.strptime(date_tail, '%y-%m-%d_%H%M%S_%Z')
            pretty_date = pretty_date.strftime('%b %d/%Y, %I:%M%p %Z').strip()
            pretty_date = click.style(f'({pretty_date})', dim=True, fg='green')
            full_filename = click.style(full_filename, bold=True)
            indicator = click.style(indicator, fg='red', bold=True)
            letter = click.style(f'{letter})', fg='green', bold=True)
            click.echo(f'{indicator} {letter} {full_filename} {pretty_date}')

        msg = click.style('Select a dir to link to (ctrl-c to abort)', fg='white')
        choice = click.prompt(msg)

        if load_db:
            db = DB(real=self.real)
            dump_file = os.path.join(data[choice], 'DB-DUMP.sql.gz')
            db.load_remote(dump_file, self.s.servername)

        temp_symname = str(uuid.uuid1())
        # link_cmd = f"'sudo test -h {self.s.root} && sudo ln -sfn {data[choice]} {self.s.root}'"

        # create a temporary symlink first then rename the temp one to
        # the real symlink, this overwrites the previous one.  The
        # rename causes the symlink to be changed with on step, as
        # opposed to `ln -sfn ...` which deletes the symlink and then
        # creates a new one with a brief period of time with no symlink.
        link_cmd = f"""'test -h {self.s.root} &&
                        ln -s {data[choice]} {temp_symname} &&
                        mv -Tf {temp_symname} {self.s.root}'"""
        link_cmd = ' '.join(link_cmd.split())
        r = ssh.run(link_cmd, dry_run=dry_run, server=self.s.servername)

        click.echo()
        ui.display_success(self.real)

    def server_time(self, server):
        """Retrieve the remote server time"""
        dry_run = True if not self.real else False
        ssh = self.ssh
        s_time = ssh.run('date "+%y-%m-%d_%H%M%S_%Z"', dry_run=False,
                         server=self.s.servername)
        s_time = s_time.strip()
        deploy_name = Path(self.s.root).parts[-1]
        stamp = f"{deploy_name}.{s_time}"
        return stamp


class DeployViaLocal:
    """
    sink deploy init
    sink deploy new
    sink deploy switch
    """

    DIST_HOME = 'dist'
    DIST_DIR_BASENAME = 'deploy'
    INFO_FILE = 'DEPLOY-INFO.yaml'
    header = '\n'.join(
        ('# Fields should not be removed from this file, they are',
         '# used to determine which deploy this is, but, fields can',
         '# be added if you want to store extra information here.',
         '#',
         '# server:       the name of the server this deploy is for',
         '# created date: the date the deploy was created localy',
         '# deploy date:  the date this deploy was pushed to the server',
         '# deploy name:  the fancypants name',
         '# note:         a short note that will display when selecting a deploy',
         ))

    def __init__(self):
        pass

    def get_dist(self) -> Path:
        project_home = config.project_root
        dist = Path(project_home, self.DIST_HOME)
        return dist

    def init_deploy(self):
        """Build dist dir

        If dist doesn't exist, build it.
        Entry for `sink deploy init`"""

        dist = self.get_dist()
        if not dist.exists():
            ui.warn(f'DIST ({dist}) dir does not exist, creating it.')
            try:
                dist.mkdir()
            except FileNotFoundError:
                ui.error(f'Cannot create {dist}')
        else:
            ui.warn(f'"{dist}" already exists')

    def new(self, server, real=False, note=None):
        """Create a new deploy

        Create a new dir in the dist dir of all the files that should
        be on the server.  These are ready to be pushed to the server
        with change_current().

        Entry for `sink deploy new`"""

        now = datetime.datetime.now().isoformat(timespec='seconds')
        fancy = coolname.generate_slug(2)
        deploy = f'{server}--{now}--{fancy}'
        deploy = self.get_dist() / deploy
        source = config.project().root

        xfer = Transfer(real)
        xfer.local(server, source, deploy)

        if real:
            info_file = deploy / self.INFO_FILE
            yaml_content = yaml.dump({
                'server': server,
                'created date': now,
                'deploy date': None,
                'deploy name': fancy,
                'note': note,
            })
            with info_file.open(mode='w') as f:
                f.write(self.header)
                f.write('\n\n')
                f.write(yaml_content)
                print()
                ui.notice(f'{info_file} created')

    def update_deploy_date(self, yaml_file):
        with yaml_file.open() as f:
            data = yaml.load(f.read(), Loader=yaml.SafeLoader)
        now = datetime.datetime.now().isoformat(timespec='seconds')
        data['deploy date'] = now
        with yaml_file.open('w') as f:
            f.write(self.header)
            f.write('\n\n')
            f.write(yaml.dump(data))

    def change_current(self, server, real=False, delete=False):
        """Change the current deploy to another

        Entry for `sink deploy switch`
        """
        s = config.server(server)
        current = self.get_current_deploy(server, real)
        dist = self.get_dist()
        available = os.listdir(dist.absolute())
        deploy = self.display_choices(available, current, server)

        yaml_file = Path(deploy['deploy dir'], self.INFO_FILE)
        if real:
            self.update_deploy_date(yaml_file)
        xfer = Transfer(real=real, silent=False)

        extra_flags = ''
        if delete:
            msg = 'This will delete files on the remote server, continue? [y/n]'
            msg = click.style(msg, fg='red', bold=True)
            choice = click.prompt(f'\n{msg}')
            if choice.lower() == 'y':
                extra_flags = '--delete'
                click.echo()
            else:
                return

        source = Path(deploy['deploy dir'])
        xfer.put(source, server, extra_flags, dest_override=s.root)

    def get_current_deploy(self, server_name, real):
        s = config.server(server_name)
        ssh = SSH()
        remote_path = Path(s.root, self.INFO_FILE)
        data = {}
        with tempfile.TemporaryDirectory() as yaml_dir:
            ssh.scp_pull(remote_path, yaml_dir, server_name, dry_run=False)
            yaml_file = Path(yaml_dir, self.INFO_FILE)
            # from IPython import embed; embed()
            try:
                with yaml_file.open('r') as f:
                    data = yaml.load(f.read(), Loader=yaml.SafeLoader)
            except FileNotFoundError:
                data = {}
        return data

    def display_choices(self, dirs, current, server_name):
        pointer = '->'
        # pointer = '▶ '
        pointer_pretty = click.style(pointer, fg='green', bold=True)

        try:
            deployed_date = current['created date']
        except KeyError:
            deployed_date = ''

        dirs = sorted(dirs)
        choices = {}
        counter = 0
        for d in dirs:
            d = Path(self.DIST_HOME, d)
            deploy_yaml = d / self.INFO_FILE
            data = None
            try:
                with open(deploy_yaml) as y:
                    data = yaml.load(y.read(), Loader=yaml.SafeLoader)
            except FileNotFoundError:
                data = None
            if not data:
                continue
            if data['server'] != server_name:
                continue
            data['deploy dir'] = str(d.absolute())
            letter = string.ascii_lowercase[counter]
            counter += 1
            choices[letter] = data

        if not choices:
            ui.error(f'No valid deploys created yet for this server ({server_name}). Run `sink deploy new server`')
        if not current:
            ui.warn(f'No deploys on the server ({server_name}). This is OK if it\'s the first deploy.')

        click.echo()
        click.echo(f'The {pointer_pretty} indicates the currently deployed version.')
        click.echo()

        for letter, data in choices.items():
            try:
                current_date = data['created date']
            except KeyError:
                ui.warn(f'Incorrect yaml file for {d}')
                continue
            active = '  '
            if current_date == deployed_date:
                active = pointer_pretty

            name = data.get('deploy name', '')
            name = click.style(name, fg='bright_blue')

            current_date = current_date.split('T')
            current_date = click.style(current_date[0], fg='green') + ' ' + click.style(current_date[1], fg='green')
            line = f"{active} {letter}) {current_date} {name}"
            click.echo(line)
            note = data.get('note', None)
            if note:
                click.secho(f'      {note}', fg='yellow')

        click.echo()
        return self.choose_letter(choices)

    def choose_letter(self, choices):
        msg = click.style(
            'Select a deploy to upload (ctrl-c to abort)',
            fg='white')
        choice = click.prompt(msg)
        try:
            selected = choices[choice]
        except KeyError:
            click.echo()
            ui.warn('Invaid choice')
            selected = self.choose_letter(choices)
        return selected

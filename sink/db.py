import os
import click
import subprocess
from pprint import pprint as pp
from pathlib import Path
import datetime
import tempfile
import gzip

from sink.config import config
from sink.config import dict2obj
from sink.ui import Color
from sink.ui import ui

class DB:
    def __init__(self, real, verbose=False):
        self.verbose = True if verbose else False
        self.real = real
        self.config = config

    def pull(self, server):
        p = self.config.project()
        s = self.config.server(server)
        db = dict2obj(**s.mysql[0])

        if not p.pulls_dir.exists():
            ui.error(f'Pulls dir not found: {p.pulls_dir}')

        if s.ssh.key:
            identity = f'-i "{s.ssh.key}"'
            # click.echo(f'Using identity: "{s.ssh.key}"')
        else:
            identity = ''

        hostname = ''
        try:
            if db.hostname:
                hostname = f'--host={db.hostname}'
        except AttributeError:
            hostname = ''

        sqlfile = self._dest(p.name, p.pulls_dir, s.name)
        cmd = f'''ssh -T {identity} {s.ssh.username}@{s.ssh.server} \
            mysqldump {hostname} --user={db.username} --password={db.password} \
            --single-transaction --triggers --events --routines {db.db} \
            | gzip -c > "{sqlfile}"'''
        cmd = ' '.join(cmd.split())

        if self.real:
            result = subprocess.run(cmd, shell=True)
            if sqlfile.exists():
                filename = str(sqlfile.absolute())
                click.secho(filename, fg=Color.GREEN.value)
                ui.display_cmd(cmd)
                ui.display_success(self.real)
            else:
                ui.display_cmd(cmd)
                click.secho('Command failed', fg=Color.RED.value)
        else:
            ui.display_cmd(cmd)
            ui.display_success(self.real)

    def put(self, server, sqlfile):
        s = self.config.server(server)
        db = dict2obj(**s.mysql[0])
        sql = Path(sqlfile)
        if not sql.exists():
            ui.error(f'{sql} does not exist')

        t = tempfile.NamedTemporaryFile()
        with gzip.open(str(sql), 'r') as gz:
            sql = gz.read()
            t.write(sql)

        if s.ssh.key:
            identity = f'-i "{s.ssh.key}"'
            # click.echo(f'Using identity: "{s.ssh.key}"')
        else:
            identity = ''

        cmd = f'''ssh -T {identity} {s.ssh.username}@{s.ssh.server} mysql --user={db.username} \
            --password={db.password} {db.db} < "{t.name}"'''
        cmd = ' '.join(cmd.split())
        print('>>>', cmd)
        if self.real:
            doit = True
            if s.warn:
                doit = False
                warn = click.style(
                    ' WARNING: ', bg=Color.YELLOW.value, fg=Color.RED.value,
                    bold=True, dim=True)
                msg = click.style(
                    f': You are about to overwrite the {s.name} database, continue?',
                    fg=Color.YELLOW.value)
                msg = warn + msg
                if click.confirm(msg):
                    doit = True

            if doit:
                result = subprocess.run(cmd, shell=True)
                if result.returncode:
                    ui.display_cmd(cmd)
                    click.secho('Command failed', fg='red')
                else:
                    ui.display_cmd(cmd)
                    ui.display_success(self.real)
        else:
            ui.display_cmd(cmd)
            ui.display_success(self.real)

    def _dest(self, project_name, dirname, id):
        now = datetime.datetime.now()
        now = now.strftime('%y-%m-%d_%H-%M-%S')
        name = f'{project_name}-{id}-{now}.sql.gz'
        p = Path(dirname, name).absolute().resolve()
        return p

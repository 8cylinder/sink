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

        if p.pulls_dir is None or not p.pulls_dir.exists():
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

        skip_secure = ''
        try:
            if db.skip_secure_auth:
                skip_secure = '--skip-secure-auth'
        except AttributeError:
            skip_secure = ''

        sqlfile = self._dest(p.name, db.db, p.pulls_dir, s.name)
        cmd = f'''ssh -T {identity} {s.ssh.username}@{s.ssh.server} \
            mysqldump {hostname} {skip_secure} --user={db.username} --password={db.password} \
            --single-transaction --triggers --events --routines {db.db} \
            | gzip -c > "{sqlfile}"'''
        cmd = ' '.join(cmd.split())

        if self.real:
            result = subprocess.run(cmd, shell=True, stderr=subprocess.PIPE)
            ui.display_cmd(cmd)
            error_msg = result.stderr.decode("utf-8").replace('Warning: Using a password on the command line interface can be insecure.\n', '')
            if error_msg:
                click.secho('\nEmpty file created:', fg=Color.YELLOW.value, bold=True)
                click.secho(str(sqlfile.absolute()), fg=Color.YELLOW.value)
                ui.error(f'\n{error_msg}')
            elif sqlfile.exists():
                filename = str(sqlfile.absolute())
                click.secho(filename, fg=Color.GREEN.value)
                ui.display_success(self.real)
            else:
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

        skip_secure = ''
        try:
            if db.skip_secure_auth:
                skip_secure = '--skip-secure-auth'
        except AttributeError:
            skip_secure = ''

        cmd = f'''ssh -T {identity} {s.ssh.username}@{s.ssh.server} mysql {self.dryrun} {skip_secure} --user={db.username} \
            --password={db.password} {db.db} < "{t.name}"'''
        cmd = ' '.join(cmd.split())

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
                result = subprocess.run(cmd, shell=True, stderr=subprocess.PIPE)
                ui.display_cmd(cmd)
                error_msg = result.stderr.decode("utf-8").replace(
                    'Warning: Using a password on the command line interface can be insecure.\n', '').replace(
                        'mysql: [Warning] Using a password on the command line interface can be insecure.\n', '')
                if error_msg:
                    ui.error(f'\n{error_msg}')
                else:
                    ui.display_success(self.real)
        else:
            ui.display_cmd(cmd)
            ui.display_success(self.real)

    def _dest(self, project_name, dbname, dirname, id):
        now = datetime.datetime.now()
        now = now.strftime('%y-%m-%d_%H-%M-%S')
        name = f'{dbname}-{id}-{now}.sql.gz'
        p = Path(dirname, name).absolute().resolve()
        return p

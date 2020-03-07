import os
import click
import subprocess
from pprint import pprint as pp
from pathlib import Path
import datetime
import tempfile
import gzip
import io
import sys

from sink.config import config
from sink.config import dict2obj
from sink.ui import Color
from sink.ui import ui

class DB:
    def __init__(self, real, verbose=False, quiet=False):
        self.verbose = True if verbose else False
        self.real = real
        self.dryrun = '' if real else '--dry-run'
        self.config = config
        self.quiet = quiet

    def dump_remote(self, dest, server):
        dest = Path(dest)
        self._pull(dest, server, local=False)

    def pull(self, server, tag=None):
        p = self.config.project()
        s = self.config.server(server)
        db = dict2obj(**s.mysql[0])
        sqlfile = self._dest(p.name, db.db, p.pulls_dir, s.name, tag=tag)
        self._pull(sqlfile, server, local=True)

    def _pull(self, sqlfile, server, local=True):
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

        mysqldump = 'mysqldump'
        try:
            mamp_path = s.mamp
            mysqldump = os.path.join(mamp_path, mysqldump)
        except AttributeError:
            mamp_path = ''

        port = ''
        if s.ssh.port:
            port = f'-p {s.ssh.port}'

        cmd = [
            f'''ssh {port} -C -T {identity} {s.ssh.username}@{s.ssh.server}''',
            f'''export MYSQL_PWD={db.password}; {mysqldump} {self.dryrun} {hostname} {skip_secure} --user={db.username} --single-transaction --triggers --events --routines {db.db}''',
            f'''| gzip -c > "{sqlfile}"'''
        ]

        if mamp_path:
            cmd = f"""{cmd[1]} {cmd[2]}"""
        elif local:
            cmd = f"""{cmd[0]} '{cmd[1]}' {cmd[2]}"""
        else:
            cmd = f"""{cmd[0]} '{cmd[1]} | gzip -c | sudo tee "{sqlfile}" >/dev/null'"""
        cmd = ' '.join(cmd.split())

        sink_db_pull = 'SINK_DB_PULL'
        os.environ[sink_db_pull] = ''
        if not self.quiet:
            ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
        if self.real:
            result = subprocess.run(cmd, shell=True, stderr=subprocess.PIPE)

            error_msg = result.stderr.decode("utf-8")
            if error_msg:
                click.secho(str(sqlfile.absolute()), fg=Color.YELLOW.value)
                ui.error(f'\n{error_msg}')
            elif local and sqlfile.exists():
                filename = str(sqlfile.absolute())
                click.secho(filename, fg=Color.GREEN.value)
                if not self.quiet:
                    ui.display_success(self.real)
                os.environ[sink_db_pull] = str(sqlfile.absolute())
            elif local:
                click.secho('Command failed', fg=Color.RED.value)
        else:
            if not self.quiet:
                ui.display_success(self.real)

    def load_remote(self, source, server):
        source = Path(source)
        self._put(source, server, local=True)

    def put(self, server, sqlfile):
        s = self.config.server(server)
        db = dict2obj(**s.mysql[0])
        sql = Path(sqlfile)
        self._put(server, sql)

    def _put(self, server, sqlfile, local=True):
        s = self.config.server(server)
        db = dict2obj(**s.mysql[0])
        if local:
            if not sqlfile.exists():
                ui.error(f'{sqlfile} does not exist')
        else:
            cmd = f'''ssh -C -T {identity} {s.ssh.username}@{s.ssh.server} "test -f {sqlfile}"'''
            result = subprocess.run(cmd, shell=True, stderr=subprocess.PIPE)
            ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
            if result.returncode:
                error(f'{sqlfile} does not exist')

        if s.ssh.key:
            identity = f'-i "{s.ssh.key}"'
        else:
            identity = ''

        skip_secure = ''
        try:
            if db.skip_secure_auth:
                skip_secure = '--skip-secure-auth'
        except AttributeError:
            skip_secure = ''

        port = ''
        if s.ssh.port:
            port = f'-p {s.ssh.port}'

        mysql = 'mysql'
        try:
            mamp_path = s.mamp  # mamp: '/Applications/MAMP/Library/bin'
            mysql = os.path.join(mamp_path, mysql)
        except AttributeError:
            mamp_path = ''

        if mamp_path:
            cmd = [
                f'''export MYSQL_PWD={db.password};''',
                f'''pv --numeric {sqlfile}''',
                # f'''cat {sqlfile}''',
                f'''| gunzip -c | {mysql} {skip_secure} --user={db.username} --password=root {db.db}''',
            ]
            cmd = f"""{cmd[0]} {cmd[1]} {cmd[2]}"""
        elif local:
            cmd = [
                f'''pv --numeric {sqlfile}''',
                # f'''cat {sqlfile}''',
                f'''| ssh {port} {identity} {s.ssh.username}@{s.ssh.server}''',
                f'''export MYSQL_PWD={db.password}; gunzip -c | {mysql} {skip_secure} --user={db.username} {db.db}''',
            ]
            cmd = f"""{cmd[0]} {cmd[1]} '{cmd[2]}'"""
        else:
            cmd = f'''ssh {port} -T {identity} {s.ssh.username}@{s.ssh.server}
                      "export MYSQL_PWD={db.password}; zcat {sqlfile} | mysql --user={db.username} {db.db}"'''
        cmd = ' '.join(cmd.split())

        if self.real:
            doit = True
            if s.warn:
                doit = False
                warn = click.style(
                    ' WARNING: ', bg=Color.YELLOW.value, fg=Color.RED.value,
                    bold=True, dim=True)
                msg = click.style(
                    f': You are about to overwrite the {s.servername} database, continue?',
                    fg=Color.YELLOW.value)
                msg = warn + msg
                if click.confirm(msg):
                    doit = True

            if doit:
                ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
                p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                error_msgs = []
                char = '\u25A0'
                chard = click.style('|', fg='red')
                with click.progressbar(
                    length=100,
                    width=0,
                    show_eta=True,
                    info_sep=click.style(' | ', fg='blue'),
                    empty_char=click.style(char, fg='black'),
                    fill_char=click.style(char, fg='blue'),
                    bar_template=f'%(bar)s %(info)s',
                ) as bar:
                    last = 0
                    for line in io.TextIOWrapper(p.stderr, encoding="utf-8"):
                        try:
                            percent = int(line)
                        except ValueError:
                            error_msgs.append(line.rstrip())
                            continue
                        step = percent - last
                        bar.update(step)
                        last = percent

                [ui.error(i, exit=False) for i in error_msgs]
                if error_msgs:
                    sys.exit(1)
                else:
                    ui.display_success(self.real)

        else:
            ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
            ui.display_success(self.real)

    def _dest(self, project_name, dbname, dirname, id, tag):
        now = datetime.datetime.now()
        now = now.strftime('%y-%m-%d_%H-%M-%S')
        tag = f'-{tag}' if tag else ''
        name = f'{dbname}-{id}-{now}{tag}.sql.gz'
        p = Path(dirname, name).absolute().resolve()
        return p

# import os
# import sys
# import re
import subprocess
# import datetime
import click
import urllib.request, urllib.error
import socket
import ssl

from sink.config import config
from sink.config import Spinner
from sink.ui import Color
from sink.ui import ui


class TestConfig:
    good = click.style('[\u2713]', fg=Color.GREEN.value)
    bad = click.style('[X]', fg=Color.RED.value)
    timeout = 5

    def __init__(self):
        self.config = config

    def test_project(self):
        click.echo()
        click.secho('Local dirs', fg=Color.GREEN.value, bold=True)

        INDENT = 2
        for local_dir in ['pulls_dir', 'log_dir', 'cache_dir']:
            try:
                d = Path(self.config.data['project'][local_dir])
            except KeyError:
                self.out(f'{self.bad} "{local_dir}" setting in {self.config.config_file} does not exist.', INDENT)
                continue
            if d.exists():
                self.out(f'{self.good} {d}', INDENT)
            else:
                self.out(f'{self.bad} {d}', INDENT)

    def test_requirements(self):
        required = ['ssh -V', 'git --version', 'rsync --version']
        required = [f"'{i}'" for i in required]
        req = ' '.join(required)
        spliter = '==='
        cmd = f'''for prg in {req}; do echo '{spliter}'; $prg; done'''
        click.echo()
        click.echo('Run the following bash command:')
        click.echo(cmd)

    def test_servers(self, server_names=None):
        click.echo()
        INDENT = 2
        for s in self.config.servers():
            if server_names:
                if s.name.lower() not in server_names:
                    continue
            try:
                click.secho(f'{s.name}', fg=Color.GREEN.value)
            except AttributeError:
                pass

            user = s.ssh.username
            url = s.ssh.server

            key = ''
            if s.ssh.key:
                key = f' -i "{s.ssh.key}"'

            # ssh login
            try:
                s.ssh.username
                # s.ssh.password
                s.ssh.server
            except AttributeError:
                ui.error(f'ssh values are wrong in {s.name}')
            if not s.ssh.username or not s.ssh.server:
                ui.error('missing values for ssh.')
            cmd = 'exit'
            good = 'ssh login good.'
            bad = f'ssh login failed for "{user}@{url}".'

            if self.run_cmd_on_server(user, url, cmd, good, bad, key=key):
                # root
                cmd = f'cd "{s.root}"'
                good = f'root dir exists.'
                bad = f'root dir does not exist on server: {s.root}.'
                self.run_cmd_on_server(user, url, cmd, good, bad, key=key)

                dbs = self.config.dbs(s.mysql)
                for db in dbs:
                    host = ''
                    if db.hostname:
                        host = f'--host={db.hostname}'
                    cmd = f'mysql --user={db.username} --password={db.password} {host} {db.db} --execute="exit";'
                    good = f'DB({db.db}): mysql username, password and db are good.'
                    bad = f'DB({db.db}): mysql error.'
                    self.run_cmd_on_server(user, url, cmd, good, bad, key=key)

            urls = self.config.urls(s.urls)
            for u in urls:
                if not u.url:
                    # if there is a url section in the yaml file, but no values for it, continue.
                    continue
                spinner = Spinner(indent=2, delay=0.1)
                spinner.start()
                try:
                    # urllib checks the cert and if it's self signed,
                    # it errors with a ValueError.  This will ignore that.
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    result = urllib.request.urlopen(u.url, timeout=self.timeout, context=ctx)
                except urllib.error.HTTPError as e:
                    # Return code error (e.g. 404, 501, ...)
                    msg = f'{self.bad} URL({u.url}): HTTPError: {e.code}.'
                except urllib.error.URLError as e:
                    # Not an HTTP-specific error (e.g. connection refused)
                    msg = f'{self.bad} URL({u.url}): URLError: {e.reason}.'
                except ValueError as e:
                    msg = f'{self.bad} URL({u.url}): Not a valid URL.'
                except AttributeError as e:
                    msg = f'AttributeError? {u.url} {e}'
                except socket.timeout:
                    msg = f'{self.bad} URL({u.url}) Timeout.'
                # except:  # socket.timeout:
                    # msg = f'{self.bad} some error {u.url}.'
                else:
                    # 200
                    msg = f'{self.good} URL({u.url})'
                spinner.stop()
                self.out(msg, 2)

    def out(self, msg, spaces):
        indent = ' ' * spaces
        click.echo(f'{indent}{msg}')

    def run_cmd_on_server(self, user, url, cmd, good, bad, key=''):

        cmd = f'''ssh -o 'ConnectTimeout {self.timeout}'{key} {user}@{url} {cmd}'''
        result = self.run_cmd(cmd, good, bad)
        return result

    def run_cmd(self, cmd, good, bad):

        spinner = Spinner(indent=2, delay=0.1)
        spinner.start()
        result = subprocess.run(cmd, shell=True,
                                stderr=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL)
        spinner.stop()
        if result.returncode:
            # click.echo(f'    {self.bad} {bad} (error: {result.returncode})')
            self.out(f'{self.bad} {bad} (error: {result.returncode})', 2)
            ui.display_cmd(cmd, indent=8)
            return False
        else:
            # click.echo(f'    {self.good} {good}')
            self.out(f'{self.good} {good}', 2)
            ui.display_cmd(cmd, indent=6)
            return True
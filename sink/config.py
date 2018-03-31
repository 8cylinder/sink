import os
import sys
import time
import threading
import click
import subprocess
from pprint import pprint as pp
import yaml
from pathlib import Path
from collections import namedtuple
import tempfile
from enum import Enum
import itertools

from sink.ui import ui
from sink.ui import Color

class Action(Enum):
    PUT = 'put'
    PULL = 'pull'


class Spinner:
    busy = False
    delay = 0.1

    @staticmethod
    def spinning_cursor(indent):
        # cursors = '|/-\\'
        # cursors = '.oO|/-\\|Oo.'
        cursors = '_.oO||Oo._'
        while True:
            for cursor in cursors:
                yield click.style(f'{indent}[{cursor}]',
                                  # bold=True,
                                  fg=Color.YELLOW.value)

    def __init__(self, delay=None, indent=0):
        self.indent = indent
        indent_char = ' ' * indent
        self.spinner_generator = self.spinning_cursor(indent_char)
        if delay and float(delay):
            self.delay = delay

    def spinner_task(self):
        while self.busy:
            sys.stdout.write(next(self.spinner_generator))
            sys.stdout.flush()
            time.sleep(self.delay)
            sys.stdout.write('\b' * (self.indent + 3))
            sys.stdout.flush()

    def start(self):
        self.busy = True
        threading.Thread(target=self.spinner_task).start()

    def stop(self):
        self.busy = False
        time.sleep(self.delay)


class dict2obj:
    def __init__(self, **level):
        for k, v in level.items():
            if isinstance(v, dict):
                self.__dict__[k] = dict2obj(**v)
            else:
                self.__dict__[k] = v

class Config:
    config_file = 'sink.yaml'

    def __init__(self, suppress_config_location=False):
        self.suppress = suppress_config_location
        try:
            self.find_config()
        except RecursionError:
            ui.error('You are not in a project.', True)

        with open(self.config) as f:
            data = yaml.safe_load(f)
        self.data = data
        self.o = dict2obj(**data)
        # pp(data['xsync points'])
        # xx = dict2obj(**data['xsync points'])
        # print('>>>', xx.pm_old.extra_flags)
        # exit()

    def find_config(self):
        if self.config_file in os.listdir():
            cwd = click.style(os.path.abspath(os.path.curdir), underline=True)
            if not self.suppress:
                click.secho(f'Using {self.config_file} in {cwd}', dim=True)
            self.config = Path(self.config_file)
        else:
            os.chdir('..')
            self.find_config()

    def project(self):
        try:
            p = self.data['project']
        except KeyError:
            ui.error(f'project section in {self.config_file} does not exist')

        # convert the path to absolute paths
        for d in ['pulls_dir', 'log_dir', 'cache_dir', 'root']:
            try:
                p[d] = Path(os.path.abspath(p[d]))
            except KeyError:
                continue

        p = namedtuple('project', p.keys())(**self.data['project'])
        return p

    def server(self, name):
        # if not name, then try to find the default server
        if not name:
            default = False
            for server_name in self.data['servers']:
                try:
                    name = self.data['servers'][server_name]['default']
                    break
                except KeyError:
                    continue
            if not name:
                ui.error('No default server found')
        try:
            s = self.data['servers'][name]
        except KeyError:
            ui.error(f'Server: "{name}" does not exist in {self.config_file}',
                     exit=False)
            click.echo('\nExisting servers:')
            options = {}
            for key in self.data['servers']:
                options[key] = '{}@{}'.format(
                    self.data['servers'][key]['user'],
                    self.data['servers'][key]['server'],
                )
            ui.display_options(options)
            exit()

        s['root'] = Path(s['root'])
        s = namedtuple('server', s.keys())(**self.data['servers'][name])
        return s

    def servers(self):
        all_servers = {}
        for k, s in self.data['servers'].items():
            all_servers[k] = dict2obj(**s)
        return all_servers

    def syncpoint(self):
        s = namedtuple('syncpoint', self.data['sync points'].keys())(
            **self.data['sync points'])
        return s

    # def syncpoints(self)

    def excluded(self):
        ex = self.data['project']['exclude']
        ex = ' '.join([f'--exclude="{i}"' for i in ex])
        return ex


class TestConfig:
    good = click.style('[\u2713]', fg=Color.GREEN.value)
    bad = click.style('[X]', fg=Color.RED.value)

    def __init__(self):
        self.config = Config()

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

    def test_servers(self):
        click.echo()
        click.secho('Servers', fg=Color.GREEN.value, bold=True)
        INDENT = 4
        for s in self.config.servers():
            click.secho(f'  {s.name}', fg=Color.GREEN.value)
            try:
                user = s.ssh.username
                url = s.ssh.server
            except AttributeError:
                self.out('No ssh info', INDENT)
                continue
            try:
                key = f' -i "{s.ssh.key}"'
            except AttributeError:
                key = ''

            # ssh login
            try:
                s.ssh.username
                # s.ssh.password
                s.ssh.server
            except AttributeError:
                ui.error(f'ssh values are wrong in {s.name}')
            cmd = 'exit'
            good = 'ssh login good.'
            bad = f'ssh login failed for "{user}@{url}".'

            if self.run_cmd(user, url, cmd, good, bad, key=key):

                # root
                cmd = f'cd "{s.root}"'
                good = f'root dir exists.'
                bad = f'root dir does not exist on server: {s.root}.'
                self.run_cmd(user, url, cmd, good, bad, key=key)

                # mysql
                try:
                    s.mysql.username
                    s.mysql.password
                    s.mysql.db
                except AttributeError:
                    ui.error(f'Mysql names are wrong in {s.name}')
                    continue
                cmd = f'mysql --user={s.mysql.username} --password={s.mysql.password} {s.mysql.db} --execute="exit";'
                good = f'mysql username, password and db are good.'
                bad = f'mysql error.'
                self.run_cmd(user, url, cmd, good, bad, key=key)

    def out(self, msg, spaces):
        indent = ' ' * spaces
        click.echo(f'{indent}{msg}')

    def test_syncpoints(self):
        ...

    def run_cmd(self, user, url, cmd, good, bad, key=''):

        timeout = 10
        cmd = f'''ssh -o 'ConnectTimeout {timeout}'{key} {user}@{url} {cmd}'''

        spinner = Spinner(indent=4, delay=0.1)
        spinner.start()
        result = subprocess.run(cmd, shell=True,
                                stderr=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL)
        spinner.stop()
        if result.returncode:
            click.echo(f'    {self.bad} {bad} (error: {result.returncode})')
            ui.display_cmd(cmd, indent=8)
            return False
        else:
            click.echo(f'    {self.good} {good}')
            ui.display_cmd(cmd, indent=8)
            return True

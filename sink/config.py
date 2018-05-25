import os
import sys
import time
import threading
import click
import subprocess
from pprint import pprint as pp
import yaml
import json
import csv
from pathlib import Path
from collections import namedtuple
import tempfile
from enum import Enum
import itertools
import urllib.request, urllib.error
import ssl
import socket
import random

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
        cursors = [
            '|/-\\',
            '_.oO||Oo._',
            '⎺⎻⎼⎽__⎽⎼⎻⎺',
            # '█▉▊▋▌▍▎▏▏▎▍▌▋▊▉█',
            # ' ░▒▓██▓▒░ ',
        ]
        cursors = random.choice(cursors)
        while True:
            for cursor in cursors:
                yield click.style(
                    f'{indent}[{cursor}]',
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


class GlobalProjects:
    def __init__(self):
        projectf = Path('~/.sink-projects')
        projectf = Path(projectf.expanduser())
        if not projectf.exists():
            click.echo(f'Creating {projectf}')
            projectf.touch()

        self.projects = {}
        self.projectf = projectf

        self.read_tsv()

        comments = '''
        # The format for this file should be tab seperated fields in this order:
        # [project name] [project] [color]
        # color can be one of: red, green, yellow, blue, magenta, cyan
        '''
        self.comments = '\n'.join([i.strip() for i in comments.split('\n')])

    def first_match(self, root):
        for k, p in self.projects.items():
            if root in k:
                return p

    def add(self, project_name, project_root):
        if project_name not in self.projects:
            color = random.choice(list(Color)).value
            self.projects[project_name] = [
                project_name,
                str(Path(project_root).absolute()),
                color,
            ]

    def save_tsv(self):
        """Write a tab seperated file"""
        with self.projectf.open('w') as f:
            f.write(self.comments)
            writer = csv.writer(f, delimiter='\t', lineterminator='\n')
            for name, row in self.projects.items():
                writer.writerow(row)

    def read_tsv(self):
        """Read a tab sepertated file"""
        with self.projectf.open() as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                if row:
                    if not row[0].startswith('#'):
                        self.projects[row[0]] = row


class Config:
    config_file = 'sink.yaml'
    default_project = {
        'name': None,
        'root': None,
        'rsync_flags': None,
        'pulls_dir': None,
        'cache_dir': None,
        'log_dir': None,
        'note': None,
        'exclude': [],
    }
    default_server = {
        'name': None,
        'note': None,
        'root': None,
        'warn': False,
        'default': False,
        'control_panel': {
            'url': None,
            'usename': None,
            'password': None,
            'note': None,
        },
        'hosting': {
            'name': None,
            'note': None,
            'url': None,
            'username': None
        },
        'ssh': {
            'key': '',
            'note': None,
            'password': None,
            'server': None,
            'username': None
        },
        'mysql': [],
        'urls': []
    }
    default_mysql = {
        'db': None,
        'note': None,
        'password': None,
        'username': None,
        'hostname': None,
        'port': 3306,
    }
    default_url = {
        'admin_url': None,
        'note': None,
        'password': None,
        'url': None,
        'username': None
    }

    def __init__(self, suppress_config_location=False):
        self.suppress = suppress_config_location
        try:
            self.find_config()
        except RecursionError:
            ui.error('You are not in a project.', True)

        try:
            with open(self.config) as f:
                data = yaml.safe_load(f)

        except yaml.YAMLError as e:
            if hasattr(e, 'problem_mark'):
                msg = 'There was an error while parsing the config file'
                if e.context is not None:
                    click.echo(f'{msg}:\n{e.problem_mark}\n{e.problem} {e.context}.')
                else:
                    click.echo(f'{msg}:\n{e.problem_mark} {e.problem}.')
            else:
                print ("Something went wrong while parsing the yaml file.")
            exit()

        self.data = data
        self.o = dict2obj(**data)
        # self.project_root
        self.save_project_name(data['project']['name'], os.path.curdir)

    def save_project_name(self, name, path):
        p = GlobalProjects()
        p.add(name, path)
        p.save_tsv()

    def find_config(self):
        """Walk up the dir tree to find a config file"""
        if self.config_file in os.listdir():
            cwd = click.style(os.path.abspath(os.path.curdir), underline=True)
            if not self.suppress:
                click.secho(f'Using {self.config_file} in {cwd}', dim=True)
            self.config = Path(self.config_file)
        else:
            os.chdir('..')
            self.find_config()

    def project(self):
        """Return the project info as a namedtupple

        Convert the project dict to a namedtuple and convert the paths
        to pathlib paths."""
        try:
            project = self.data['project']
        except KeyError:
            ui.error(f'project section in {self.config_file} does not exist')

        p = self.default_project
        p.update(project)

        # convert paths to absolute paths
        for d in ['root', 'pulls_dir']:
            try:
                fixed = os.path.expanduser(p[d])
                fixed = os.path.abspath(fixed)
                p[d] = Path(fixed)
            except KeyError:
                # this field is blank
                continue
            except TypeError:
                # this fields does not exist
                continue
        p = dict2obj(**p)
        return p

    def server(self, name):
        """Return the requested server as an object

        If the server name is None, return the default server"""

        # if not name, then try to find the default server
        if not name:
            default_count = 0
            for server_name in self.data['servers']:
                try:
                    if self.data['servers'][server_name]['default'] is True:
                        name = server_name
                        default_count += 1
                except KeyError:
                    continue
            if default_count > 1:
                ui.error('Only one server can be set to default.')
            elif not name:
                ui.error('No server was specified and no server is set to default.')

        try:
            server = self.data['servers'][name]
        except KeyError:
            ui.error(f'Server: "{name}" does not exist in {self.config_file}',
                     exit=False)
            click.echo('\nExisting servers:')
            options = {}
            for server in self.servers():
                options[server.name] = '{}@{}'.format(
                    server.ssh.username,
                    server.ssh.server
                )
            ui.display_options(options)
            exit()

        s = self._server(server)
        return s

    def _server(self, server):
        """Convert a server dict to obj"""
        for k, v in server.items():
            if k == 'hosting':
                hosting = self.default_server['hosting'].copy()
                hosting.update(v)
                server['hosting'] = hosting
            elif k == 'control_panel':
                cp = self.default_server['control_panel'].copy()
                cp.update(v)
                server['control_panel'] = cp
            elif k == 'ssh':
                ssh = self.default_server['ssh'].copy()
                ssh.update(v)
                server['ssh'] = ssh
                ssh_key = server['ssh']['key']
                if ssh_key:
                    ssh_key = os.path.abspath(ssh_key)
                    server['ssh']['key'] = ssh_key

        s = self.default_server.copy()
        s.update(server)
        return dict2obj(**s)

    def servers(self):
        all_servers = []
        try:
            servers = self.data['servers']
        except KeyError:
            return all_servers

        for server_name, server in servers.items():
            all_servers.append(self._server(server))

        return all_servers

    def dbs(self, dbs):
        """Convert a list of dicts to a list of objects"""
        all_dbs = []
        for database in dbs:
            db = self.default_mysql.copy()
            db.update(database)
            all_dbs.append(dict2obj(**db))
        return all_dbs

    def urls(self, urls):
        """Convert a list of dicts to a list of objects"""
        all_urls = []
        try:
            for url in urls:
                u = self.default_url.copy()
                u.update(url)
                all_urls.append(dict2obj(**u))
        except AttributeError:
            return False
        return all_urls

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
    timeout = 5

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

            # try:
            #     user = s.ssh.username
            #     url = s.ssh.server
            # except AttributeError:
            #     self.out('No ssh info', INDENT)
            #     continue
            user = s.ssh.username
            url = s.ssh.server

            key = ''
            # pp(dir(s.ssh))
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



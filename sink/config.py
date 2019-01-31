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
import traceback

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


class Configuration:
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
        'deploy_root': None,
        'warn': False,
        'default': False,
        'group': None,
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
            'key': None,
            'note': None,
            'password': None,
            'server': None,
            'username': None,
            'port': None,
        },
        'mysql': [],
        'urls': [],
        'actions': [],
    }
    default_mysql = {
        'db': None,
        'note': None,
        'password': None,
        'username': None,
        'hostname': None,
        'skip_secure_auth': None,
        'port': 3306,
    }
    default_url = {
        'admin_url': None,
        'note': None,
        'password': None,
        'url': None,
        'username': None
    }

    def __init__(self, suppress_config_location=True):
        self.suppress = suppress_config_location
        try:
            self.find_config(os.curdir)
        except RecursionError:
            ui.error('You are not in a project.', True)

        try:
            with open(self.config_file) as f:
                data = yaml.safe_load(f)

        except yaml.YAMLError as e:
            if hasattr(e, 'problem_mark'):
                msg = 'There was an error while parsing the config file'
                if e.context is not None:
                    click.echo(f'{msg}:\n{e.problem_mark}\n{e.problem} {e.context}.')
                else:
                    click.echo(f'{msg}:\n{e.problem_mark} {e.problem}.')
            else:
                print("Something went wrong while parsing the yaml file.")
            exit()

        # take the name of the server and add it to the server data
        # structure for easier extraction.
        try:
            for servername in data['servers']:
                data['servers'][servername]['servername'] = servername
        except KeyError:
            pass  # no servers defined

        self.data = data
        self.o = dict2obj(**data)
        self.save_project_name(data['project']['name'], os.path.curdir)

    def save_project_name(self, name, path):
        p = GlobalProjects()
        p.add(name, path)
        p.save_tsv()

    # def find_config(self):
    #     """Walk up the dir tree to find a config file"""
    #     if self.config_file in os.listdir():
    #         cwd = click.style(os.path.abspath(os.path.curdir), underline=True)
    #         if not self.suppress:
    #             click.secho(f'Using {self.config_file} in {cwd}', dim=True)
    #         self.config = Path(self.config_file)
    #     else:
    #         os.chdir('..')
    #         self.find_config()

    def find_config(self, cur):
        """Walk up the dir tree to find a config file"""
        if self.config_file in os.listdir(cur):
            cwd = click.style(os.path.abspath(os.path.curdir), underline=True)
            if not self.suppress:
                click.secho(f'Using {self.config_file} in {cwd}', dim=True)
            self.config_file = Path(cur, self.config_file)
            self.project_root = Path(cur)
        else:
            cur = os.path.abspath(os.path.join(cur, '..'))
            self.find_config(cur)

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

        # root is required
        try:
            p['root'] = os.path.expanduser(p['root'])
            root_d = Path(self.project_root, p['root'])
            root_d = root_d.expanduser().absolute()
            if not root_d.exists():
                ui.error(f'Root dir does not exist: {root_d}')
            p['root'] = root_d
        except TypeError:
            # this fields does not exist
            ui.error('Root is a required setting in project')

        # db pulls dir
        pulls_dir = p['pulls_dir']
        if pulls_dir:
            pulls_dir = Path(self.project_root, pulls_dir)
            pulls_dir = pulls_dir.expanduser().absolute().resolve()
            # pulls_dir = pulls_dir
            if not pulls_dir.exists():
                ui.error(f'DB pull dir does not exist: {pulls_dir}')
        p['pulls_dir'] = pulls_dir

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
                    ssh_key = os.path.abspath(os.path.expanduser(ssh_key))
                    if not os.path.exists(ssh_key):
                        ui.warn(f'ssh key does not exist: {ssh_key}')
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

    def excluded(self):
        ex = self.data['project']['exclude']
        ex = ' '.join([f'--exclude="{i}"' for i in ex])
        return ex


config = Configuration()

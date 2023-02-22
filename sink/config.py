import os
import sys
import time
import threading
import click
from pprint import pprint as pp
import yaml
import csv
from pathlib import Path
from collections import namedtuple
from enum import Enum
import random
import traceback

from sink.ui import ui
from sink.ui import Color
# from sink.command import Command
from sink.init import Init


class Action(Enum):
    PUT = 'put'
    PULL = 'pull'
    DIFF = 'diff'


class Spinner:
    busy = False
    delay = 0.1

    @staticmethod
    def spinning_cursor(indent):
        cursors = [
            '|/-\\',
            '_.oO||Oo._',
            '⎺⎻⎼⎽__⎽⎼⎻⎺',
            '█▉▊▋▌▍▎▏▏▎▍▌▋▊▉█',
            ' ░▒▓██▓▒░ ',
        ]
        cursors = random.choice(cursors)
        while True:
            for cursor in cursors:
                yield click.style(
                    f'{indent}[{cursor}]',
                    fg=str(Color.YELLOW.value))

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


class Dict2obj:
    """
    test = {
        'cow':{
            'sound': 'moo',
            'size': 'lg',
            'color': {
                'fg': 'white',
                'bg': 'black'
            }
        }
    }
    test = Dict2obj(**test)
    print(test.cow.color.bg) # black
    """
    def __init__(self, **level):
        self.raw = level
        for k, v in level.items():
            if isinstance(v, dict):
                self.__dict__[k] = Dict2obj(**v)
            else:
                self.__dict__[k] = v

    def __iter__(self):
        for k, v in self.__dict__.items():
            if not k.startswith("__"):
                yield k, v

    def __repr__(self):
        return f'{self.__class__.__name__}()'

    # def __str__(self):
        # print(self.raw)

        # from pprint import pformat
        # name = self.__repr__()
        # name = click.style(name, fg='cyan', bold=True)
        #
        # data = pformat(self.raw)
        # data = click.style(data, fg='cyan')
        #
        # return f'{name}\n{data}'

    def to_dict(self):
        pass
        # return self.raw


class Configuration:
    config_file = 'sink.yaml'
    RSYNC = 'rsync'
    default_project = {
        'name': None,
        'root': None,
        'rsync_flags': None,
        'pulls_dir': None,
        'cache_dir': None,
        'log_dir': None,
        'rsync_binary': None,
        'note': None,
        'difftool': None,
        'exclude': [],
    }
    default_server = {
        'type': None,
        'name': None,
        'note': None,
        'root': None,
        'deploy_root': None,
        'warn': False,
        'default': False,
        'group': None,
        'user': None,
        'automatic': False,
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
        # 'ssh': {
        #     'key': None,
        #     'note': None,
        #     'password': None,
        #     'server': None,
        #     'username': None,
        #     'port': None,
        # },
        'ssh': [],
        'mysql': [],
        'urls': [],
        'actions': [],
    }
    default_ssh = {
        'key': None,
        'name': None,
        'note': None,
        'password': None,
        'server': None,
        'username': None,
        'port': None,
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
        self.suppress_commands = False

    def load_config(self, raise_err=False):
        config_exists = self.find_config(os.curdir)
        if not config_exists:
            if raise_err:
                # throw an error instead so that it can be trapped elsewhere.
                raise FileNotFoundError()
            else:
                ui.error('You are not in a project', exit=False)
                click.echo('A sink.yaml file was not found in this or '
                           'any directory above.')
                sys.exit(1)

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
            ui.warn(f'Server not found: {servername}')
            # pass  # no servers defined
        except TypeError:
            ui.warn('No servers defined in sink.yaml')

        self.data = data
        if data:
            self.o = Dict2obj(**data)
        else:
            ui.error('sink.yaml appears to have no data')

    def find_config(self, cur):
        """Walk up the dir tree to find a config file"""
        if cur == '/':
            return False
        elif str(self.config_file) in os.listdir(cur):
            self.config_file = Path(cur, self.config_file)
            self.project_root = Path(cur)
            return True
        else:
            cur = os.path.abspath(os.path.join(cur, '..'))
            return self.find_config(cur)

    def project(self):
        """Return the project info as a namedtupple

        Convert the project dict to a namedtuple and convert the paths
        to pathlib paths."""

        project = None
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
        p['pulls_dir_original'] = p['pulls_dir']
        pulls_dir = p['pulls_dir']
        if pulls_dir:
            pulls_dir = Path(self.project_root, pulls_dir)
            pulls_dir = pulls_dir.expanduser().absolute().resolve()
            # pulls_dir = pulls_dir
            if not pulls_dir.exists():
                ui.error(f'DB pull dir does not exist: {pulls_dir}')
        # else:
        #     ui.warn('pulls dir not set')
        p['pulls_dir'] = pulls_dir

        # rsync binary
        try:
            rsync_bin = self.get_rsync_name(p['rsync_binary'][sys.platform])
        except TypeError:
            rsync_bin = self.get_rsync_name(p['rsync_binary'])
        except KeyError:
            rsync_bin = self.RSYNC
        p['rsync_binary'] = rsync_bin

        p = Dict2obj(**p)
        return p

    def get_rsync_name(self, rsync_bin: str) -> str:
        if not rsync_bin:
            return self.RSYNC
        elif rsync_bin == self.RSYNC:
            return self.RSYNC
        elif rsync_bin and os.path.exists(rsync_bin):
            return rsync_bin
        elif rsync_bin and not os.path.exists(rsync_bin):
            raise FileNotFoundError(f'rsync binary does not exist: {rsync_bin}')
        else:
            return self.RSYNC

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

        server = None
        try:
            server = self.data['servers'][name]
        except KeyError:
            click.echo('\nExisting servers:')
            options = {}
            for server in self.servers():
                options[server.name] = '{}@{}'.format(
                    server.ssh.username,
                    server.ssh.server
                )
            ui.display_options(options)
            ui.error(f'Server: "{name}" does not exist in {self.config_file}')

        server_data = self._server(server, name)
        return server_data

    def _server(self, server, name):
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
            elif k == 'mysql':
                mysql_holder = []
                for mysql_db in v:
                    mysql_template = self.default_mysql.copy()
                    mysql_template.update(mysql_db)
                    mysql_holder.append(Dict2obj(**mysql_template))
                server['mysql'] = mysql_holder
            elif k == 'ssh':
                ssh_holder = []
                for ssh_user in v:
                    ssh_template = self.default_ssh.copy()
                    try:
                        ssh_template.update(ssh_user)
                    except ValueError:
                        ui.error(f'SSH settings are not an array, update sink.yaml to new format.')

                    ssh_key = None
                    try:
                        ssh_key = ssh_user['key']
                    except TypeError:
                        pass
                    if ssh_key:
                        abs_ssh_key = os.path.abspath(os.path.expanduser(ssh_key))
                        prj_ssh_key = os.path.join(self.project_root, ssh_key)
                        # try a relative or absolute path
                        if os.path.exists(abs_ssh_key):
                            ssh_template['key'] = abs_ssh_key
                        # try one relative to the project root
                        elif os.path.exists(prj_ssh_key):
                            ssh_template['key'] = prj_ssh_key
                        else:
                            ui.warn(f'ssh key does not exist: {ssh_key}')

                    ssh_holder.append(Dict2obj(**ssh_template))

                server['ssh'] = ssh_holder

        # add the server name to a 'name' field
        server['name'] = name

        s = self.default_server.copy()
        s.update(server)
        server_obj = Dict2obj(**s)
        return server_obj

    def servers(self):
        all_servers = []
        try:
            servers = self.data['servers']
        except KeyError:
            return all_servers

        for server_name, server in servers.items():
            all_servers.append(self._server(server, server_name))

        return all_servers

    def dbs(self, dbs):
        """Convert a list of dicts to a list of objects"""
        all_dbs = []
        for database in dbs:
            db = self.default_mysql.copy()
            db.update(database)
            all_dbs.append(Dict2obj(**db))
        return all_dbs

    def urls(self, urls):
        """Convert a list of dicts to a list of objects"""
        all_urls = []
        try:
            for url in urls:
                u = self.default_url.copy()
                u.update(url)
                all_urls.append(Dict2obj(**u))
        except AttributeError:
            return False
        return all_urls

    def sshs(self, sshs):
        """Convert a list of dicts to a list of objects"""
        all_sshs = []
        try:
            for ssh in sshs:
                s = self.default_ssh.copy()
                s.update(ssh)
                all_sshs.append(Dict2obj(**s))
        except AttributeError:
            return False
        return all_sshs

    def syncpoint(self):
        s = namedtuple('syncpoint', self.data['sync points'].keys())(
            **self.data['sync points'])
        return s

    def excluded(self, server):
        project_ex = []
        try:
            project_ex = self.data['project']['exclude']
            project_ex = [i for i in project_ex if i] if project_ex else []
        except KeyError:
            pass

        server_ex = []
        try:
            server_ex = self.data['servers'][server]['exclude']
            server_ex = [i for i in server_ex if i] if server_ex else []
        except KeyError:
            pass

        all = project_ex + server_ex
        all = set(all)
        all = sorted(all)
        all = ' '.join([f'--exclude="{i}"' for i in all])
        # all = ','.join([f"'{i}'" for i in all])
        # all = f'--exclude={{{all}}}'
        return all


config = Configuration()

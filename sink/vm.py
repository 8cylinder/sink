import os
import shutil
from pprint import pprint as pp
from pathlib import Path
import sys

from sink.config import config
from sink.ui import ui


class Vagrant:

    def __init__(self):
        self.config = config
        self.project = config.project()

    def create(self, server, hostname, ip):
        server = self.config.server(server)

        os.chdir(config.project_root)

        if not os.path.exists('boss'):
            ui.error('boss not found')
        else:
            ui.notice('boss found')

        if not os.path.exists('Vagrantfile'):
            self.vagrantfile(server, hostname, ip)
        else:
            ui.error('Vangrantfile already exists, quitting.')

        ui.msg(f'''
          Things to do:
          1. configure .env, .htaccess
          2. vagrant up
          3. sink db put {server.name} <path/to/file.sql.gz>
          4. npm install, grunt, webpack etc...
        ''')

    def vagrantfile(self, server, hostname, ip):
        sink_dir = os.path.dirname(__file__)
        template = f'{sink_dir}/resources/Vagrantfile'
        dest: str = os.path.join(os.path.abspath(os.path.curdir), 'Vagrantfile')

        try:
            with open(template, 'r') as f:
                vagrantfile = f.read()
        except FileNotFoundError:
            ui.error(f'Vagrantfile template not found: {template}')

        if not self.project.name:
            ui.error('Project has no name')

        try:
            dbuser = server.mysql[0]['username']
            dbpass = server.mysql[0]['password']
            dbname = server.mysql[0]['db']
        except IndexError:
            ui.error('Mysql settings do not exist')
        except KeyError:
            ui.error('Mysql username or password key does not exist')

        if not dbuser or not dbpass:
            ui.error('Site db username or password is not set')

        vagrantfile = vagrantfile.format(
            project_title=self.project.name,
            project_ip=ip,
            project_hostname=hostname,
            project_mountpoint=self.project.root,
            project_dbname=dbname,
            project_dbpass=dbpass,
        )

        try:
            with open(dest, 'w') as f:
                f.write(vagrantfile)
        except AttributeError:
            ui.error(f'could not write Vagrantfile')

        ui.notice(f'Vagrantfile created: {dest}')

    def build_boss(self):
        """
        1. make temp dir
        2. checkout boss there
        3. run build
        4. copy boss to project root
        """
        pass

    def run_init_setup(self, file):
        """
        1. find script
        2. run it
        """
        pass

import os
# noinspection PyUnresolvedReferences
from pprint import pprint as pp

from sink.config import config
from sink.ui import ui
from sink.command import Command
from sink.config import config
import click


class Vagrant:

    def __init__(self):
        self.messages = []
        self.config = config
        # self.project = config.project()
        self.cmd = Command()
        self.config = config

    def create(self, server, hostname, ip):
        self.config.load_config()
        self.project = self.config.project()

        server = self.config.server(server)

        os.chdir(config.project_root)

        if not os.path.exists('boss'):
            ui.error('boss not found')

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

        if not self.check_sink_yaml(server.name):
            ui.error('There are problems with sink.yaml.  Run sink vm check for details.')

        try:
            with open(template, 'r') as f:
                vagrantfile = f.read()
        except FileNotFoundError:
            ui.error(f'Vagrantfile template not found: {template}')

        if not self.project.name:
            ui.error('Project has no name')

        dbuser = dbpass = dbname = None
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

    def check(self, servername, hostname, ip):

        # look for ip in /etc/hosts
        self.check_hosts(hostname, ip)

        # vagrantfile
        self.check_vagrant_file(servername, hostname, ip)

        # look for boss
        self.find_boss()

        # # look for .env .htaccess
        # self.find_configs()

        # look for ssh, db info
        self.check_sink_yaml(servername)

        self.render_messages(self.messages)

    @staticmethod
    def render_messages(messages):
        print()
        for message in messages:
            msg = message['msg']
            success = message['success']
            note = message['note'] if 'note' in message else None
            indent = message.get('indent', '')
            if success:
                print(
                    click.style(f'{indent}[✓]', bold=True, fg='green'),
                    click.style(msg, fg='green'),
                )
            else:
                print(
                    click.style(f'{indent}[x]', bold=True, fg='red'),
                    click.style(msg, fg='red'),
                )
                if note:
                    click.secho(f'    {note}', fg='blue')

    def check_hosts(self, hostname, ip):
        hostsfile = '/etc/hosts'
        line = f'^{hostname} *{ip}'
        cmd = f'grep "{line}" {hostsfile}'
        success = self.cmd.runp(cmd)

        if not success:
            self.messages.append({
                'msg': f'"{hostname} {ip}" not found in {hostsfile}',
                'note': f'echo "{hostname} {ip}" | sudo tee -a {hostsfile}',
                'success': False,
            })
        else:
            self.messages.append({
                'msg': f'"{ip} {hostname}" found in {hostsfile}',
                'success': True,
            })

    def find_boss(self):
        cmd = 'find -iname boss'
        url = 'https://api.github.com/repos/8cylinder/boss/releases/latest'

        success = self.cmd.runp(cmd)
        if success:
            self.messages.append({
                'msg': 'boss found',
                'success': True,
            })
        else:
            self.messages.append({
                'msg': 'boss not found',
                'success': False,
                'note': f'curl -s {url} | jq ".assets[0].browser_download_url" | xargs curl -L --output boss && chmod +x boss',
            })
        return success

    def find_configs(self):
        pass

    def check_sink_yaml(self, servername):
        sink_yaml = self.config.find_config(os.curdir)
        success = True
        if not sink_yaml:
            self.messages.append({
                'msg': 'sink.yaml does not exist',
                'success': False,
                'note': f'sink misc init {servername} > sink.yaml',
            })
            success = False
        else:
            self.messages.append({
                'msg': 'sink.yaml exists',
                'success': True,
            })
            self.config.load_config()
            server = self.config.server(servername)
            db = server.mysql[0]
            fields = ['username', 'password', 'db']
            for field in fields:
                if db[field]:
                    self.messages.append({
                        'msg': f'mysql {field} found',
                        'success': True,
                        'indent': '    ',
                    })
                else:
                    success = False
                    self.messages.append({
                        'msg': f'mysql {field} not found',
                        'success': False,
                        'indent': '    ',
                    })
        return success

    def check_vagrant_file(self, servername, hostname, ip):
        cmd = 'find -iname Vagrantfile'
        success = self.cmd.runp(cmd)
        if success:
            self.messages.append({
                'msg': 'Vagrantfile found',
                'success': True,
            })
        else:
            self.messages.append({
                'msg': 'Vagrantfile not found',
                'note': f'sink vm build {servername} {hostname} {ip}',
                'success': False,
            })
        return success


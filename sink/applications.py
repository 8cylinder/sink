
import click
from sink.config import config
from pprint import pprint as pp

class Applications:
    def __init__(self):
        self.config = config
        self.apps = {
            'mysql': self._mysql,
            'filezilla': self._filezilla,
            'nautilus': self._nautilus,
        }
        self.app = None

    def name(self, app_name):
        if app_name in self.apps:
            self.app = self.apps[app_name]
            return True
        else:
            return False

    def app_settings(self):
        return self.app()

    def known(self):
        return ', '.join(list(self.apps))

    def pretify(self, data):
        pretty = ''
        for s in data:
            pretty += '\n'
            pretty += click.style(f'{s[0][1]}\n', fg='blue', bold=True)
            for field_name, field_value in s:
                if not field_value:
                    field_value = ''
                field_value = str(field_value)
                field_name = click.style(field_name.ljust(18), dim=True)
                field_value = click.style(field_value, fg='white')
                pretty += f'{field_name} - {field_value}\n'
        return pretty

    def _mysql(self):
        out = []
        p = self.config.project()
        for s in self.config.servers():
            for db in self.config.dbs(s.mysql):
                connection = []
                title = '--'.join([i for i in [p.name, s.servername, db.db] if i])
                connection.append(['Connection Name', f'{title}'])
                connection.append(['SSH Hostname', s.ssh.server])
                connection.append(['SSH Username', s.ssh.username])
                connection.append(['SSH Password', s.ssh.password])
                connection.append(['SSH Key File', s.ssh.key])
                connection.append(['MySQL Hostname', db.hostname])
                connection.append(['MySQL Server Port', db.port])
                connection.append(['Username', db.username])
                connection.append(['Password', db.password])
                connection.append(['Default Schema', db.db])
                out.append(connection)
        return self.pretify(out)

    def _filezilla(self):
        out = []
        p = self.config.project()
        for s in self.config.servers():
            connection = []
            title = '--'.join([i for i in [p.name, s.servername] if i])
            connection.append(['Site name', f'{title}'])
            connection.append(['Host', s.ssh.server])
            connection.append(['Port', s.ssh.port])
            connection.append(['Protocol', 'SFTP - SSH File Transfer Protocol'])
            connection.append(['Logon Type', 'Key file'])
            connection.append(['User', s.ssh.username])
            connection.append(['Key File', s.ssh.key])
            connection.append(['Default local directory', p.root])
            connection.append(['Default remote directory', s.root])
            connection.append(['SSH Password', s.ssh.password])
            out.append(connection)
        return self.pretify(out)

    def _nautilus(self):
        out = []
        p = self.config.project()
        for s in self.config.servers():
            connection = f'sftp://{s.ssh.username}@{s.ssh.server}/{s.root}'
            out.append(connection)
        return '\n'.join(out)

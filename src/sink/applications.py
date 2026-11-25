from sink.config.models import Config, Server, SSHConfig


class Applications:
    def __init__(self, config: Config):
        self.config = config
        self.apps = {
            "mysql": self._mysql,
            "filezilla": self._filezilla,
            "nautilus": self._nautilus,
            "dbeaver": self._dbeaver,
        }
        self.app = None

    def name(self, app_name):
        if app_name in self.apps:
            self.app = self.apps[app_name]
            return True
        return False

    def app_settings(self):
        return self.app()

    def known(self):
        return ", ".join(list(self.apps))

    def pretify(self, data):
        pretty = ""
        for section in data:
            pretty += "\n"
            pretty += f"{section[0][1]}\n"
            for field_name, field_value in section:
                if not field_value:
                    field_value = ""
                field_value = str(field_value)
                pretty += f"{field_name.ljust(18)} - {field_value}\n"
        return pretty

    @staticmethod
    def _ssh(server: Server) -> SSHConfig:
        return server.ssh[0] if server.ssh else SSHConfig()

    def _mysql(self):
        out = []
        p = self.config.project
        for s in self.config.servers.values():
            ssh = self._ssh(s)
            for db in s.databases:
                connection = []
                title = "--".join([i for i in [p.name, s.name, db.db] if i])
                connection.append(["Connection Name", f"{title}"])
                connection.append(["SSH Hostname", ssh.server])
                connection.append(["SSH Username", ssh.username])
                connection.append(["SSH Password", ssh.password])
                connection.append(["SSH Key File", ssh.key])
                connection.append(["MySQL Hostname", db.hostname])
                connection.append(["MySQL Server Port", db.port])
                connection.append(["Username", db.username])
                connection.append(["Password", db.password])
                connection.append(["Default Schema", db.db])
                out.append(connection)
        return self.pretify(out)

    def _filezilla(self):
        out = []
        p = self.config.project
        for s in self.config.servers.values():
            ssh = self._ssh(s)
            connection = []
            title = "--".join([i for i in [p.name, s.name] if i])
            connection.append(["Site name", f"{title}"])
            connection.append(["Host", ssh.server])
            connection.append(["Port", ssh.port])
            connection.append(["Protocol", "SFTP - SSH File Transfer Protocol"])
            connection.append(["Logon Type", "Key file"])
            connection.append(["User", ssh.username])
            connection.append(["Key File", ssh.key])
            connection.append(["Default local directory", p.root])
            connection.append(["Default remote directory", s.root])
            connection.append(["SSH Password", ssh.password])
            out.append(connection)
        return self.pretify(out)

    def _nautilus(self):
        out = []
        for s in self.config.servers.values():
            ssh = self._ssh(s)
            connection = f"sftp://{ssh.username}@{ssh.server}/{s.root}"
            out.append(connection)
        return "\n".join(out)

    def _dbeaver(self):
        out = []
        p = self.config.project
        for s in self.config.servers.values():
            ssh = self._ssh(s)
            for db in s.databases:
                connection = []
                title = "--".join([i for i in [p.name, s.name, db.db] if i])
                connection.append(["Connection Name", f"{title}"])
                connection.append(["Main tab", ""])
                connection.append(["Server Host", db.hostname])
                connection.append(["Port", db.port])
                connection.append(["Database", db.db])
                connection.append(["Username", db.username])
                connection.append(["Password", db.password])
                connection.append(["SSH tab", ""])
                connection.append(["Host/IP", ssh.server])
                connection.append(["User Name", ssh.username])
                connection.append(["Password", ssh.password])
                connection.append(["Private Key", ssh.key])
                out.append(connection)
        return self.pretify(out)

"""Render copy-paste connection settings for common clients."""

from collections.abc import Callable, Iterable, Sequence

from sink.config.models import Config, Server, SSHConfig


class Applications:
    """Generate connection settings for known applications."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.apps = {
            "mysql": self._mysql,
            "filezilla": self._filezilla,
            "nautilus": self._nautilus,
            "dbeaver": self._dbeaver,
        }
        self.app: Callable[[], str] | None = None

    def name(self, app_name: str | None) -> bool:
        """Select an application by name."""
        if app_name in self.apps:
            self.app = self.apps[app_name]
            return True
        return False

    def app_settings(self) -> str:
        """Render the selected application's settings."""
        if self.app is None:
            raise ValueError("No application selected")
        return self.app()

    def known(self) -> str:
        """Return the comma-separated application names."""
        return ", ".join(list(self.apps))

    def pretify(self, data: Iterable[Sequence[Sequence[object]]]) -> str:
        """Format labelled connection fields for display."""
        pretty = ""
        for section in data:
            pretty += "\n"
            pretty += f"{section[0][1]}\n"
            for field_name, field_value in section:
                if not field_value:
                    field_value = ""
                pretty += f"{str(field_name).ljust(18)} - {field_value}\n"
        return pretty

    @staticmethod
    def _ssh(server: Server) -> SSHConfig:
        """Return the first ssh config or an empty one."""
        return server.ssh[0] if server.ssh else SSHConfig()

    def _mysql(self) -> str:
        """Render MySQL client connection settings."""
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

    def _filezilla(self) -> str:
        """Render FileZilla site settings."""
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

    def _nautilus(self) -> str:
        """Render Nautilus sftp URIs."""
        out = []
        for s in self.config.servers.values():
            ssh = self._ssh(s)
            connection = f"sftp://{ssh.username}@{ssh.server}/{s.root}"
            out.append(connection)
        return "\n".join(out)

    def _dbeaver(self) -> str:
        """Render DBeaver connection settings."""
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

"""Generate a starter ``sink.yaml`` document."""

import json
import re

from sink.errors import CommandError

_SERVER_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def _validate_name(name: str) -> None:
    """Reject a server name that is not a safe YAML key."""
    if name in {".", ".."} or _SERVER_NAME.fullmatch(name) is None:
        raise CommandError(
            f"Invalid server name {name!r}: use letters, digits, dot, dash, "
            "or underscore, starting with a letter, digit, or underscore"
        )


def _yaml_key(name: str) -> str:
    """Return a server name as a safe YAML key."""
    if _SERVER_NAME.fullmatch(name) is not None:
        return name
    return json.dumps(name)


class Init:
    """Build the starter YAML template."""

    def __init__(self) -> None:
        self.server_names = None

    def servers(self, names: tuple[str, ...]) -> None:
        """Validate and set the server names to include."""
        seen: set[str] = set()
        for name in names:
            _validate_name(name)
            if name in seen:
                raise CommandError(f"Duplicate server name: {name}")
            seen.add(name)
        self.server_names = names

    def create(self) -> str:
        """Return the rendered template."""
        blank_config = """
          # -*- make-backup-files: nil; -*-

          project:
            # used for db pull file name (as well as the server id).
            name: 'project-name-here'
            # dir to put pulled db's in.  Keep this outside root and create
            # it before the first db pull.
            pulls_dir: .sink/pulls
            # dir to the common root.  Everything below this point must be
            # the same structure on all the servers.  This can be an
            # absolute path or a relative path.  A relative path will be
            # relative to the location of this file.  Create it before the
            # first transfer, and keep only deployable content here;
            # sink.yaml, pulls/, env files, and keys belong above it.
            root: public
            # specify the rsync binary for each platform.  If not specified it
            # will use the default rsync.
            rsync_binary:
              osx:
              linux:
            # specify a gui diff tool to use.  Use {local} and {remote} for the arguments.
            # eg: meld {local} {remote}
            difftool: meld {local} {remote}
            # Secret material is excluded from directory transfers by
            # default: sink.yaml, pulls/, *.sql.gz, .env*, *.pem, *.key,
            # id_*, .ssh/, .git/, and cloud credential files.  Use
            # --allow-secret-files only for an intentional exception.
            # these files will also be excluded from any dir syncing:
            exclude:
              - .git
              - '.#*'
              - .DS_Store
              - .well-known
              - '*.sass'
              - '*.scss'
              - '.sass-cache'
              - '*.pyc'
              - storage/runtime
              - storage/logs
              - storage/config-backups
              - storage/composer-backups
              - cpresources
              - __pycache__
              - .env

          servers:"""
        if not self.server_names:
            self.server_names = ("example_server",)
        names = tuple(self.server_names)
        for name in names:
            _validate_name(name)
        for server in names:
            key = _yaml_key(server)
            blank_config = (
                blank_config
                + f"""
            {key}:
              # Everything below this point should match
              # everything below the project root.
              root:
              # This will warn you when putting files or a db to this server.
              warn: no
              # If you want the group and user to be changed when uploading
              # set group and user to the desired names.  This assumes you have
              # permission to run chown.
              group:
              user:
              # server level exclude.  These will be combined with the
              # project excludes.
              exclude:
              note: |
                Notes are written like this and can be on multiple lines.
                They cannot start on the same line as the vertical bar.
              control_panel:
                url:
                username:
                password:
                note: |
              ssh:
                # Multiple ssh configs can be defined and given a name.  These
                # can be specified when sshing into a server, but rsync
                # commands will only use the first one.
                - name:
                  username:
                  password:
                  server:
                  key:
                  port:
                  note: |
              hosting:
                name:
                url:
                username:
                password:
                note: |
              # Each db listed here will be checked with 'sink check'
              # but only the first one can be used with the db command.
              mysql:
                - username:
                  password:
                  db:
                  hostname:
                  # If getting 'Error: Connection using old (pre-4.1.1)
                  # authentication protocol refused (client option
                  # 'secure_auth' enabled)' errors, set skip_secure_auth to 'yes';
                  # https://serverfault.com/a/573816
                  skip_secure_auth:
                  note: |
              urls:
                - url:
                  admin_url:
                  username:
                  password:
                  htusername:
                  htpassword:
                  note: |
                - url:
                  admin_url:
                  username:
                  password:
                  htusername:
                  htpassword:
                  note: |
              # Actions are any command that can be run on the server. Each command
              # must start with the command name and the command itself.
              actions:
                clearcache: 'sudo -u www-data php /var/www/craft/craft clear-caches/all'
                restartapache: sudo service apache2 restart
                files: ls -al
            """
            )

        # remove the leading spaces
        return "\n".join([i[10:] for i in blank_config.split("\n")])

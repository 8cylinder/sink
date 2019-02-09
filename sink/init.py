import click
from sink.config import config
from pprint import pprint as pp


class Init:
    def __init__(self):
        pass

    def servers(self, names):
        self.server_names = names

    def create(self):
        blank_config = '''
          # -*- make-backup-files: nil; -*-

          project:
            # used for db pull file name (as well as the server id).
            name:
            # dir to put pulled db's in.
            pulls_dir:
            # dir to the common root.  Everything below this point must be
            # the same structure on all the servers.  This can be an
            # absolute path or a relative path.  A relative path will be
            # relative to the location of this file.
            root:
            # these files will be excluded from any dir syncing:
            exclude:
              - .well-known
              - '*.sass'
              - '*.scss'
              - '*.pyc'
              - '.sass-cache'
              - .git
              - storage/runtime
              - __pycache__

          servers:'''
        if not self.server_names:
            self.server_names = ['example_server']
        for server in self.server_names:
            blank_config = blank_config + f'''
            {server}:
              # Everything below this point should match
              # everything below the project root.
              root:
              # deploy root must be an absolute path.
              deploy_root:
              # This will warn you when puting files or a db to this server.
              warn: yes
              # If this is set to yes, then this server will
              # be used if no server is specified on the command line.
              default: no
              # If you want the group and user to be changed when uploading
              # set group and user to the desired names.
              group:
              user:
              note: |
                Notes are written like this and can be
                on multiple lines.  They cannot start on the same
                line as the vertical bar.
              control_panel:
                url:
                username:
                password:
                note: |
              ssh:
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
                  note: |
                - url:
                  admin_url:
                  username:
                  password:
                  note: |
              # Actions are any command that can be run on the server. Each command
              # must start with a dash, the command name, and the command itself.
              actions:
                clearcache: 'sudo -u www-data php /var/www/craft/craft clear-caches/all'
                restartapache: sudo service apache2 restart
                files: ls -al
            '''

        # remove the leading spaces
        blank_config = blank_config.split('\n')
        blank_config = '\n'.join([i[10:] for i in blank_config])
        return blank_config

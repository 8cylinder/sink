import click
from sink.config import Config
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
              # This is used for the pulled filename.
              # It can be changed to anything.
              name: {server.upper()}
              # Everything below this point should match
              # everything below the project root.
              root:
              # This will warn you when puting files or a db to this server.
              warn: yes
              # If this is set to yes, then this server will
              # be used if no server is specified on the command line.
              default: no
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
            '''

        # remove the leading spaces
        blank_config = blank_config.split('\n')
        blank_config = '\n'.join([i[10:] for i in blank_config])
        return blank_config

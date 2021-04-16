import subprocess
import click
from pprint import pprint as pp
from pathlib import Path
import tempfile
import os
import glob
import re

from sink.config import config
from sink.ui import Color
from sink.config import Action
from sink.ui import ui


# Rsync ignore owner, group, time, and perms:
# https://unix.stackexchange.com/q/102211
class Transfer:
    def __init__(self, real, verbose=False, silent=False, quiet=False):
        """Transfer files to and from a server with rsync

        verbose: adds --verbose to rsync
        silent: adds --quiet to rsync & does not display command output
        quiet: adds --quiet to rsync
        suppress:
        """
        self.verbose = True if verbose else False
        self.real = real
        self.dryrun = '' if real else '--dry-run'
        # self.config = Config(suppress_config_location=quiet)  # fixme
        self.config = config
        self.prj = config.project()
        self.quiet = quiet
        self.silent = silent
        self.multiple = False

    def single(self, filename):
        for server in self.config.servers():
            locations = self.locations(server.name, filename)
            local = locations['local']
            remote = locations['remote']
            if server.automatic:
                # print(local, remote, server.name, Action.PUT)
                server.warn = False
                self._rsync(local, remote, server.name, Action.PUT, single=True)

    def put(self, filename, server, extra_flags, dest_override=None):
        locations = self.locations(server, filename)
        local = locations['local']
        # append a / to the remote path if its a dir so rsync will
        # sync two dirs with the same name
        if local.is_dir():
            local = '{}/'.format(local)
            self.multiple = True
        remote = locations['remote']
        if dest_override:
            remote = dest_override
        self._rsync(local, remote, server, Action.PUT, extra_flags)

    def pull(self, filename, server, extra_flags):
        locations = self.locations(server, filename)
        local = locations['local']
        remote = locations['remote']
        # append a / to the remote path if its a dir so rsync will
        # sync two dirs with the same name
        if local.is_dir():
            remote = '{}/'.format(remote)
            self.multiple = True
        self._rsync(local, remote, server, Action.PULL, extra_flags)

    def hard_link_flag(self, dest, server_name):
        parent = dest.parent
        # dirs = os.listdir(parent)
        # from IPython import embed; embed()
        dirs = glob.glob(f'{parent.absolute()}/{server_name}*')
        flag = ''
        if dirs:
            last = list(reversed(sorted(dirs)))[0]
            last = parent / last
            flag = f'--link-dest={last.absolute()}'
        return flag

    def find(self, name, path):
        for root, dirs, files in os.walk(path):
            if name in files:
                return Path(root, name)
                # return os.path.join(root, name)

    def local(self, server_name, source, dest):
        p = self.config.project()
        server = self.config.server(server_name)
        rsyncb = p.rsync_binary
        excluded = self.config.excluded(server_name)

        included_list = [
            f'.env.{server.name}',
            f'robots.txt.{server.name}',
            f'.htaccess.{server.name}',
        ]
        included = ' '.join([f'--include="{i}"' for i in included_list])

        hard_link_flag = self.hard_link_flag(dest, server_name)

        cmd = f'{rsyncb} --archive --verbose {hard_link_flag} {self.dryrun} {included} {excluded} {source}/ {dest}'

        self.run(cmd, single=False, action=Action.PUT, server=server, remotef=dest, localf=source)

        # make symlinks to included files or rename them by droping the .server
        if not self.dryrun:
            for f in included_list:
                conf_file = self.find(f, dest)
                base_name = re.sub(f'\.{server.name}$', '', str(conf_file))
                base_name = Path(base_name)
                base_name.symlink_to(conf_file.name)
                print(f'Symlink created to {conf_file.name} from {base_name}')


    def diff_multiple_servers(self, local_file, servers):
        # for server in servers:
        #   create a dir
        #   download file
        # vimdiff all
        # remove temp dirs
        ...

    def diff(self, local_file, server, ignore=False, word_diff=None, difftool=False):
        local_file = Path(local_file)
        if local_file.is_dir():
            self.multiple = True
            # difftool = True
        with tempfile.TemporaryDirectory(suffix=f' [{server}]') as diffdir:
            tmp_file = f'{diffdir}/{local_file.name}'
            locations = self.locations(server, local_file)
            remotef = locations['remote']

            self._rsync(diffdir, remotef, server, Action.DIFF, compare_to=local_file)

            tmp_file_fixed = tmp_file
            if self.multiple:
                tmp_file_fixed = diffdir

            if difftool:
                gui = self.prj.difftool
                if gui:
                    cmd = gui.format(remote=f'"{tmp_file_fixed}"', local=f'"{local_file}"')
                else:
                    ui.error('No difftool program defined in sink.yaml')
            else:
                flags = []
                if ignore:
                    flags.append('--ignore-all-space')  # --ignore-space-change
                if word_diff == 'word':
                    flags.append('--word-diff=color')
                elif word_diff == 'letter':
                    flags.append('--word-diff=color --word-diff-regex=.')
                flags = ' '.join(flags)

                cmd = f'''git --no-pager diff --color=always {flags} --diff-algorithm=minimal --ignore-all-space\
                          '{tmp_file_fixed}' '{local_file}' | less'''

            # cmd = f'vimdiff -R {tmp_file_fixed} {local_file}'
            # cmd = ' '.join(cmd.split())

            ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
            result = subprocess.run(cmd, shell=True)
            if not difftool and result.returncode == 0:
                click.echo('Files are the same.')

    def locations(self, server, filename, ignore=False, difftool=False):
        p = self.config.project()
        s = self.config.server(server)
        local = filename
        remote = str(local)
        # remove the local project root from the file
        remote = remote.replace(str(p.root.absolute()), '.')
        # add the server root
        try:
            remote = Path(s.root, remote)
        except TypeError:
            ui.error(f'Server has no root ({s.servername}).')
        file_locations = {
            'local': local,
            'remote': remote,
        }
        return file_locations

    def _rsync(self, localf, remotef, server, action, extra_flags='', single=False, compare_to=None):
        s = self.config.server(server)
        identity = ''
        if s.ssh.key:
            identity = f'--rsh="ssh -i {s.ssh.key}"'

        included = [
            f'.env.{s.name}',
            f'robots.txt.{s.name}',
            f'.htaccess.{s.name}',
        ]
        included = ' '.join([f'--include="{i}"' for i in included])

        excluded = ''
        recursive = ''
        if self.multiple:
            excluded = self.config.excluded(server)
            recursive = '--recursive'

        group = ''
        if action == Action.PUT and (s.group or s.user):
            # To have rsync change owner or group, sudo will probably
            # have to be used.  The '--rsync-path' needs to be set to
            # "sudo rsync".  Also the '--group' and '--owner' flags
            # have to be used as well, otherwise '--chown' will be
            # ignored.
            group_flag = '--group' if s.group else ''
            user_flag = '--owner' if s.user else ''
            group = f'{group_flag} {user_flag} --rsync-path="sudo rsync" --chown={s.group or ""}:{s.user or ""}'

        if self.silent or self.quiet:
            extra_flags += ' --quiet '

        verbose_flag = ''
        if self.verbose:
            verbose_flag = '--verbose'

        port = ''
        if s.ssh.port:
            # https://stackoverflow.com/a/4630407
            port = f'-e "ssh -p {s.ssh.port}"'

        rsyncb = self.config.project().rsync_binary

        # --no-perms --no-owner --no-group --no-times --ignore-times
        # flags = ['--verbose', '--compress', '--checksum', '--recursive']
        cmd = f'''{rsyncb} {self.dryrun} {port} {identity} {group} {extra_flags} {verbose_flag} --itemize-changes
                  --links --compress --checksum {recursive} {included} {excluded}'''

        if action == Action.PUT:
            cmd = f'''{cmd} '{localf}' {s.ssh.username}@{s.ssh.server}:{remotef}'''
        elif action == Action.PULL:
            cmd = f'''{cmd} '{s.ssh.username}@{s.ssh.server}:{remotef}' '{localf}' '''
        elif action == Action.DIFF:
            if self.multiple:
                remotef = str(remotef) + '/'
            cmd = f'''{cmd} --compare-dest='{compare_to}' '{s.ssh.username}@{s.ssh.server}:{remotef}' '{localf}' '''

        cmd = ' '.join(cmd.split())  # remove extra spaces
        # print(cmd);exit()
        self.run(cmd, single, action, s, remotef, localf)

    def run(self, cmd, single, action, server, remotef, localf):
        doit = True
        # if the server has warn = True, then pause here to query the user.
        if not single:
            if action == Action.PUT and server.warn and self.real:
                doit = False
                warn = click.style(
                    ' WARNING: ', bg=Color.YELLOW.value, fg=Color.RED.value,
                    bold=True, dim=True)
                msg = click.style(
                    f': You are about to overwrite the {server.servername} "{remotef}" files, continue?',
                    fg=Color.YELLOW.value)
                msg = warn + msg
                if click.confirm(msg):
                    doit = True

        if doit:
            result = subprocess.run(cmd, shell=True, stderr=subprocess.PIPE)
            if result.returncode:
                if not self.silent:
                    ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
                ui.error(f'\n{result.stderr.decode("utf-8")}')
            else:
                if not self.silent:
                    ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
                if single:
                    ui.display_success(self.real, f'[{server.servername}] {localf}')
                else:
                    ui.display_success(self.real)

    def error_code(self, code):
        code = str(code)
        codes = {
            '1': 'Syntax or usage error',
            '2': 'Protocol incompatibility',
            '3': 'Errors selecting input/output files, dirs',
            '4': 'Requested  action  not  supported:  an attempt was made to manipulate 64-bit files on a platform that cannot support them; or an option was specified that is supported by the client and not by the server.',
            '5': 'Error starting client-server protocol',
            '6': 'Daemon unable to append to log-file',
            '10': 'Error in socket I/O',
            '11': 'Error in file I/O',
            '12': 'Error in rsync protocol data stream',
            '13': 'Errors with program diagnostics',
            '14': 'Error in IPC code',
            '20': 'Received SIGUSR1 or SIGINT',
            '21': 'Some error returned by waitpid()',
            '22': 'Error allocating core memory buffers',
            '23': 'Partial transfer due to error',
            '24': 'Partial transfer due to vanished source files',
            '25': 'The --max-delete limit stopped deletions',
            '30': 'Timeout in data send/receive',
            '35': 'Timeout waiting for daemon connection',
        }
        return codes[code]

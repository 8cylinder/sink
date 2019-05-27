import os
import sys
import re
import subprocess
import click
from pprint import pprint as pp
import yaml
from pathlib import Path
import datetime
from collections import namedtuple
import tempfile
import gzip
from enum import Enum
import tempfile

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
        self.quiet = quiet
        self.silent = silent
        self.multiple = False

    def put(self, filename, server, extra_flags):
        locations = self.locations(server, filename)
        local = locations['local']
        # append a / to the remote path if its a dir so rsync will
        # sync two dirs with the same name
        if local.is_dir():
            local = '{}/'.format(local)
            self.multiple = True
        remote = locations['remote']
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

    def diff(self, local_file, server, ignore=False, word_diff=None, difftool=False):
        with tempfile.TemporaryDirectory() as diffdir:
            tmp_file = f'{diffdir}/{local_file.name}'
            locations = self.locations(server, local_file)
            remotef = locations['remote']

            self._rsync(tmp_file, remotef, server, Action.PULL)

            if difftool:
                cmd = f'''meld {tmp_file} {local_file}'''
            else:
                flags = []
                if ignore:
                    flags.append('--ignore-all-space')  # --ignore-space-change
                if word_diff == 'word':
                    flags.append('--word-diff=color')
                elif word_diff == 'letter':
                    flags.append('--word-diff=color --word-diff-regex=.')
                flags = ' '.join(flags)

                cmd = f'''git --no-pager diff {flags} --diff-algorithm=minimal --ignore-all-space\
                          {tmp_file} {local_file}'''
            cmd = ' '.join(cmd.split())

            ui.display_cmd(cmd, suppress_commands=config.suppress_commands)
            result = subprocess.run(cmd, shell=True)
            if result.returncode == 0:
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

    def _rsync(self, localf, remotef, server, action, extra_flags=''):
        s = self.config.server(server)
        identity = ''
        if s.ssh.key:
            identity = f'--rsh="ssh -i {s.ssh.key}"'

        excluded = ''
        recursive = ''
        if self.multiple:
            excluded = self.config.excluded()
            recursive = '--recursive'

        group = ''
        if action == Action.PUT and s.group:
            # --group needs to be used along with --chown to change group on the server
            group = f'--group --chown=:{s.group}'

        if self.silent or self.quiet:
            extra_flags += ' --quiet '

        verbose_flag = ''
        if self.verbose:
            verbose_flag = '--verbose'

        # --no-perms --no-owner --no-group --no-times --ignore-times
        # flags = ['--verbose', '--compress', '--checksum', '--recursive']
        cmd = f'''rsync {self.dryrun} {identity} {group} {extra_flags} {verbose_flag} --itemize-changes
                  --links --compress --checksum {recursive} {excluded}'''

        if action == Action.PUT:
            cmd = f'''{cmd} '{localf}' {s.ssh.username}@{s.ssh.server}:{remotef}'''
        elif action == Action.PULL:
            cmd = f'''{cmd} '{s.ssh.username}@{s.ssh.server}:{remotef}' '{localf}' '''
        cmd = ' '.join(cmd.split())  # remove extra spaces

        doit = True
        # if the server has warn = True, then pause here to query the user.
        if action == Action.PUT and s.warn and self.real:
            doit = False
            warn = click.style(
                ' WARNING: ', bg=Color.YELLOW.value, fg=Color.RED.value,
                bold=True, dim=True)
            msg = click.style(
                f': You are about to overwrite the {s.servername} "{remotef}" files, continue?',
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

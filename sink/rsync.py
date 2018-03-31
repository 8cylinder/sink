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

from sink.config import Config
from sink.ui import Color
from sink.config import Action
from sink.ui import ui


# Rsync ignore owner, group, time, and perms:
# https://unix.stackexchange.com/q/102211
class Transfer:
    def __init__(self, real, verbose=False):
        self.verbose = True if verbose else False
        self.real = real
        self.dryrun = '' if real else '--dry-run'
        self.config = Config()

    def put(self, sync_point, server):
        locations = self.locations(server, sync_point=sync_point)
        local = locations['local']
        remote = locations['remote']
        self._build_cmd(sync_point, server, Action.PUT)

    def pull(self, sync_point, server):
        locations = self.locations(server, sync_point=sync_point)
        local = locations['local']
        remote = locations['remote']
        self._build_cmd(local, remote, server, Action.PULL)

    def single_put(self, filename, server):
        locations = self.locations(server, filename=filename)
        local = locations['local']
        remote = locations['remote']
        self._build_cmd(local, remote, server, Action.PUT)

    def single_pull(self, filename, server):
        locations = self.locations(server, filename=filename)
        local = locations['local']
        remote = locations['remote']
        self._build_cmd(local, remote, server, Action.PULL)

    def locations(self, server, sync_point=None, filename=None):
        p = self.config.project()
        s = self.config.server(server)

        if(sync_point):
            sp = self.config.data['sync points'][sync_point]
            local = p.root / sp
            remote = s.root / sp
        elif(filename):
            local = filename
            remote = str(local)
            # remove the local project root from the file
            remote = remote.replace(str(p.root), '.')
            # add the server root
            remote = Path(s.root, remote)

        file_locations = {
            'local': local,
            'remote': remote,
        }
        return file_locations

    def _build_cmd(self, localf, remotef, server, action):
        # s = self.config.servers()[server]
        s = self.config.server(server)

        try:
            identity = f'--rsh="ssh -i {s.ssh.key}"'
        except AttributeError:
            identity = ''
        excluded = self.config.excluded()

        #     --no-perms --no-owner --no-group --no-times --ignore-times \
        cmd = f'''rsync {self.dryrun} {identity} --verbose --compress --checksum
            --recursive {excluded}'''

        if action == Action.PUT:
            cmd = f'''{cmd} '{localf}/' {s.ssh.username}@{s.ssh.server}:{remotef}'''
        elif action == Action.PULL:
            cmd = f'''{cmd} '{s.ssh.username}@{s.ssh.server}:{remotef}/' '{localf}' '''
        cmd = ' '.join(cmd.split())  # remove extra spaces

        doit = True
        if action == Action.PUT and s.warn and self.real:
            doit = False
            warn = click.style(
                ' WARNING: ', bg=Color.YELLOW.value, fg=Color.RED.value,
                bold=True, dim=True)
            msg = click.style(
                f': You are about to overwrite the {s.ssh.id} "{remotef}" files, continue?',
                fg=Color.YELLOW.value)
            msg = warn + msg
            if click.confirm(msg):
                doit = True

        if doit:
            result = subprocess.run(cmd, shell=True)
            if result.returncode:
                ui.display_cmd(cmd)
                click.secho('Command failed', fg=Color.RED.value)
            else:
                ui.display_cmd(cmd)
                ui.display_success(self.real)

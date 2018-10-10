import os
import sys
import subprocess
from pprint import pprint as pp


class Command:
    def execute(self, cmd):
        result = self.run(cmd)
        return result

    def run(self, cmd):
        result = subprocess.check_output(
            cmd, shell=True,
            stderr=subprocess.PIPE)
        return result.decode('utf-8')


class SSHCommand(Command):
    def __init__(self, server):
        self.s = server

    def execute(self, cmd):
        ssh_cmd = self.ssh(cmd)
        result = self.run(ssh_cmd)

    def ssh(self, cmd):
        return f'ssh x@x.com {cmd}'

import shlex
import subprocess

# noinspection PyUnresolvedReferences
import plumbum
from plumbum import local


class Command:
    def execute(self, cmd):
        result = self.run(cmd)
        return result

    def run(self, cmd):
        result = subprocess.check_output(
            cmd, shell=True, stderr=subprocess.PIPE
        )
        return result.decode("utf-8")

    def runp(self, cmd):
        cmd = shlex.split(cmd)
        command = local[cmd[0]][cmd[1:]]
        success = True
        results = None

        try:
            results = command.run()
        except plumbum.ProcessExecutionError:
            success = False

        try:
            if not results[1]:
                success = False
        except TypeError:
            success = False

        return success


class SSHCommand(Command):
    def __init__(self, server):
        self.s = server

    def execute(self, cmd):
        ssh_cmd = self.ssh(cmd)
        self.run(ssh_cmd)

    def ssh(self, cmd):
        return f"ssh x@x.com {cmd}"

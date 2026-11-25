import glob
import os
import re
import shlex
import tempfile
from pathlib import Path

import click

from sink.config import Action, config
from sink.shell import Argv, Pipeline, run
from sink.ui import Color, ui


# Rsync ignore owner, group, time, and perms:
# https://unix.stackexchange.com/q/102211
class Transfer:
    def __init__(
        self, real, verbose=False, silent=False, quiet=False, server_name=None
    ):
        """Transfer files to and from a server with rsync

        verbose: adds --verbose to rsync
        silent: adds --quiet to rsync & does not display command output
        quiet: adds --quiet to rsync
        suppress:
        """
        self.verbose = bool(verbose)
        self.real = real
        self.config = config
        self.prj = config.project()
        self.server = config.server(server_name)
        self.server_name = server_name
        self.quiet = quiet
        self.silent = silent
        self.multiple = False

    def single(self, filename):
        for server in self.config.servers():
            locations = self._locations(filename)
            local = locations["local"]
            remote = locations["remote"]
            if server.automatic:
                server.warn = False
                self._rsync(
                    local,
                    remote,
                    Action.PUT,
                    single=True,
                    server=server.name,
                )

    def put(self, filename, extra_flags, dest_override=None):
        locations = self._locations(filename)
        local = locations["local"]
        # append a / to the remote path if its a dir so rsync will
        # sync two dirs with the same name
        if local.is_dir():
            local = f"{local}/"
            self.multiple = True
        remote = locations["remote"]
        if dest_override:
            remote = dest_override
        self._rsync(local, remote, Action.PUT, self._flags(extra_flags))

    def pull(self, filename, extra_flags):
        locations = self._locations(filename)
        local = locations["local"]
        remote = locations["remote"]
        # append a / to the remote path if its a dir so rsync will
        # sync two dirs with the same name
        if local.is_dir():
            remote = f"{remote}/"
            self.multiple = True
        self._rsync(local, remote, Action.PULL, self._flags(extra_flags))

    @staticmethod
    def _flags(extra_flags):
        if not extra_flags:
            return ()
        if isinstance(extra_flags, str):
            return tuple(shlex.split(extra_flags))
        return tuple(extra_flags)

    def _hard_link_flag(self, dest, server_name):
        parent = dest.parent
        dirs = glob.glob(f"{parent.absolute()}/{server_name}*")
        if not dirs:
            return None
        last = Path(next(sorted(dirs, reverse=True)))
        return last.absolute()

    def _find(self, name, path):
        for root, _dirs, files in os.walk(path):
            if name in files:
                return Path(root, name)
        return None

    def local(self, server_name, source, dest):
        p = self.config.project()
        server = self.config.server(server_name)
        rsyncb = p.rsync_binary
        excluded = self.config.excluded(server_name)

        included_list = [
            f".env.{server.name}",
            f"robots.txt.{server.name}",
            f".htaccess.{server.name}",
        ]

        hard_link_flag = self._hard_link_flag(dest, server_name)

        argv = [rsyncb, "--archive", "--verbose"]
        if hard_link_flag:
            argv.extend(["--link-dest", str(hard_link_flag)])
        for include in included_list:
            argv.extend(["--include", include])
        for exclude in excluded:
            argv.extend(["--exclude", exclude])
        argv.extend([f"{source}/", str(dest)])

        command = Argv(tuple(argv), dry_run_flag="--dry-run")
        self.run(
            command,
            single=False,
            action=Action.PUT,
            server=server,
            remotef=dest,
            localf=source,
        )

        # make symlinks to included files or rename them by dropping the
        # .server suffix
        if self.real:
            for name in included_list:
                conf_file = self._find(name, dest)
                if conf_file:
                    base_name = re.sub(rf"\.{server.name}$", "", str(conf_file))
                    base_name = Path(base_name)
                    base_name.symlink_to(conf_file.name)
                    print(
                        f"Symlink created to {conf_file.name} from {base_name}"
                    )

    def diff_multiple_servers(self, local_file, servers):
        # for server in servers:
        #   create a dir
        #   download file
        # vimdiff all
        # remove temp dirs
        ...

    def diff(self, local_file, ignore=False, word_diff=None, difftool=False):
        server_name = self.server.name
        local_file = Path(local_file)
        if local_file.is_dir():
            self.multiple = True
            # difftool = True
        with tempfile.TemporaryDirectory(suffix=f" [{server_name}]") as diffdir:
            tmp_file = f"{diffdir}/{local_file.name}"
            locations = self._locations(local_file)
            remotef = locations["remote"]

            # The downloaded file is required for the diff, so the default
            # mode prints the real transfer instead of rsync's dry run.
            self._rsync(
                diffdir,
                remotef,
                Action.DIFF,
                compare_to=local_file,
                native_dry_run=False,
            )

            tmp_file_fixed = tmp_file
            if self.multiple:
                tmp_file_fixed = diffdir

            if difftool:
                command = self._difftool_command(
                    tmp_file_fixed, local_file, diffdir
                )
                result = run(command, real=self.real, capture=False)
                return

            flags = ["--ignore-all-space"]
            if word_diff == "word":
                flags.append("--word-diff=color")
            elif word_diff == "letter":
                flags.extend(["--word-diff=color", "--word-diff-regex=."])

            argv = [
                "git",
                "--no-pager",
                "diff",
                "--color=always",
                *flags,
                "--diff-algorithm=minimal",
                tmp_file_fixed,
                str(local_file),
            ]
            pipeline = Pipeline((Argv(tuple(argv)), Argv(("less",))))
            result = run(pipeline, real=self.real, capture=False)
            if self.real and result.returncode == 0:
                click.echo("Files are the same.")

    def _difftool_command(self, tmp_file_fixed, local_file, diffdir):
        gui = self.prj.difftool
        if not gui:
            ui.error("No difftool program defined in sink.yaml")
        command = gui.format(
            remote=f'"{tmp_file_fixed}"', local=f'"{local_file}"'
        )
        return Argv(tuple(shlex.split(command)))

    def _locations(self, filename, ignore=False, difftool=False):
        p = self.config.project()
        s = self.server
        local = filename
        remote = str(local)
        # remove the local project root from the file
        remote = remote.replace(str(p.root.absolute()), ".")
        # add the server root
        try:
            remote = Path(s.root, remote)
        except TypeError:
            ui.error(f"Server has no root ({s.servername}).")
        return {
            "local": local,
            "remote": remote,
        }

    def _rsync(
        self,
        localf,
        remotef,
        action,
        extra_flags=(),
        single=False,
        compare_to=None,
        server=None,
        native_dry_run=True,
    ):
        # for single(), the server is not global
        s = self.server
        if server:
            s = self.config.server(server)

        command = self._rsync_command(
            localf,
            remotef,
            action,
            s,
            extra_flags=self._flags(extra_flags),
            compare_to=compare_to,
            native_dry_run=native_dry_run,
        )
        self.run(command, single, action, s, remotef, localf)

    def _rsync_command(
        self,
        localf,
        remotef,
        action,
        server,
        *,
        extra_flags=(),
        compare_to=None,
        native_dry_run=True,
    ):
        ssh = server.ssh[0]  # use the first ssh server defined
        rsyncb = self.config.project().rsync_binary

        argv = [rsyncb]

        rsh = ["ssh"]
        if ssh.port:
            rsh.extend(["-p", str(ssh.port)])
        if ssh.key:
            rsh.extend(["-i", ssh.key])
        if len(rsh) > 1:
            argv.extend(["--rsh", " ".join(rsh)])

        if action == Action.PUT and (server.group or server.user):
            # To have rsync change owner or group, sudo will probably
            # have to be used.  The '--rsync-path' needs to be set to
            # "sudo rsync".  Also the '--group' and '--owner' flags
            # have to be used as well, otherwise '--chown' will be
            # ignored.
            # https://askubuntu.com/a/719440
            if server.group:
                argv.append("--group")
            if server.user:
                argv.append("--owner")
            argv.append(f"--chown={server.user or ''}:{server.group or ''}")

        argv.extend(
            [*extra_flags, "--itemize-changes", "--links", "--compress"]
        )
        argv.append("--checksum")

        if self.silent or self.quiet:
            argv.append("--quiet")
        if self.verbose:
            argv.append("--verbose")
        if self.multiple:
            argv.append("--recursive")

        for include in (
            f".env.{server.name}",
            f"robots.txt.{server.name}",
            f".htaccess.{server.name}",
        ):
            argv.extend(["--include", include])

        excluded = self.config.excluded(server.name) if self.multiple else ()
        for exclude in excluded:
            argv.extend(["--exclude", exclude])

        host = f"{ssh.username}@{ssh.server}"
        if action == Action.PUT:
            argv.extend([str(localf), f"{host}:{remotef}"])
        elif action == Action.PULL:
            argv.extend([f"{host}:{remotef}", str(localf)])
        elif action == Action.DIFF:
            if self.multiple:
                remotef = f"{remotef}/"
            if compare_to is not None:
                argv.append(f"--compare-dest={compare_to}")
            argv.extend([f"{host}:{remotef}", str(localf)])

        return Argv(
            tuple(argv),
            dry_run_flag="--dry-run" if native_dry_run else None,
        )

    def run(self, command, single, action, server, remotef, localf):
        doit = True
        if not single and action == Action.PUT and server.warn and self.real:
            doit = False
            warn = click.style(
                " WARNING: ",
                bg=Color.YELLOW.value,
                fg=Color.RED.value,
                bold=True,
                dim=True,
            )
            msg = click.style(
                f": You are about to overwrite the {server.servername} "
                f'"{remotef}" files, continue?',
                fg=Color.YELLOW.value,
            )
            if click.confirm(warn + msg):
                doit = True

        if not doit:
            return

        result = run(command, real=self.real, capture=True)
        if result.stdout:
            click.echo(result.stdout, nl=False)
        if result.returncode:
            ui.error(f"\n{result.stderr}")
        else:
            if single:
                ui.display_success(self.real, f"[{server.servername}] {localf}")
            else:
                ui.display_success(self.real)

    def error_code(self, code):
        code = str(code)
        codes = {
            "1": "Syntax or usage error",
            "2": "Protocol incompatibility",
            "3": "Errors selecting input/output files, dirs",
            "4": "Requested  action  not  supported:  an attempt was made to manipulate 64-bit files on a platform that cannot support them; or an option was specified that is supported by the client and not by the server.",
            "5": "Error starting client-server protocol",
            "6": "Daemon unable to append to log-file",
            "10": "Error in socket I/O",
            "11": "Error in file I/O",
            "12": "Error in rsync protocol data stream",
            "13": "Errors with program diagnostics",
            "14": "Error in IPC code",
            "20": "Received SIGUSR1 or SIGINT",
            "21": "Some error returned by waitpid()",
            "22": "Error allocating core memory buffers",
            "23": "Partial transfer due to error",
            "24": "Partial transfer due to vanished source files",
            "25": "The --max-delete limit stopped deletions",
            "30": "Timeout in data send/receive",
            "35": "Timeout waiting for daemon connection",
        }
        return codes[code]

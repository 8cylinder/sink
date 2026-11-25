"""Build and run rsync transfers."""

import glob
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

import click

from sink.config.models import Action, Project, Server
from sink.errors import TransferError
from sink.shell import Argv, Pipeline, run
from sink.ui import ui


# Rsync ignore owner, group, time, and perms:
# https://unix.stackexchange.com/q/102211
class Transfer:
    """Build and run rsync transfers for one project and server."""

    def __init__(
        self,
        project: Project,
        server: Server,
        real=False,
        verbose=False,
        silent=False,
        quiet=False,
    ):
        """Transfer files to and from a server with rsync

        verbose: adds --verbose to rsync
        silent: adds --quiet to rsync & does not display command output
        quiet: adds --quiet to rsync
        """
        self.verbose = bool(verbose)
        self.real = real
        self.project = project
        self.server = server
        self.quiet = quiet
        self.silent = silent
        self.multiple = False

    def _excluded(self) -> tuple[str, ...]:
        """Combine project and server exclusions."""
        values = {*self.project.exclude, *self.server.exclude}
        return tuple(sorted(value for value in values if value))

    def single(self, filename):
        """Send a file to this transfer's server."""
        xfer = Transfer(
            self.project,
            self.server,
            real=self.real,
            verbose=self.verbose,
            silent=self.silent,
            quiet=self.quiet,
        )
        locations = xfer._locations(filename)
        xfer._rsync(
            locations["local"],
            locations["remote"],
            Action.PUT,
            single=True,
        )

    def put(self, filename, extra_flags, dest_override=None):
        """Upload a file or directory."""
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
        """Download a file or directory."""
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
        """Normalize extra rsync flags."""
        if not extra_flags:
            return ()
        if isinstance(extra_flags, str):
            return tuple(shlex.split(extra_flags))
        return tuple(extra_flags)

    def _hard_link_flag(self, dest, server_name):
        """Find the newest deploy for ``--link-dest``."""
        parent = dest.parent
        dirs = glob.glob(f"{parent.absolute()}/{server_name}*")
        if not dirs:
            return None
        last = Path(next(sorted(dirs, reverse=True)))
        return last.absolute()

    def _find(self, name, path):
        """Find a file by name under a directory."""
        for root, _dirs, files in os.walk(path):
            if name in files:
                return Path(root, name)
        return None

    def local(self, source, dest):
        """Copy into a local deploy directory."""
        p = self.project
        server = self.server
        rsyncb = p.rsync_binary
        excluded = self._excluded()

        included_list = [
            f".env.{server.name}",
            f"robots.txt.{server.name}",
            f".htaccess.{server.name}",
        ]

        hard_link_flag = self._hard_link_flag(dest, server.name)

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
        """Placeholder for comparing several servers."""
        ...

    def diff(self, local_file, ignore=False, word_diff=None, difftool=False):
        """Download a file and show or print the diff."""
        server_name = self.server.name
        local_file = Path(local_file)
        if local_file.is_dir():
            self.multiple = True
        with tempfile.TemporaryDirectory(suffix=f" [{server_name}]") as diffdir:
            tmp_file = f"{diffdir}/{local_file.name}"
            locations = self._locations(local_file)
            remotef = locations["remote"]

            # The downloaded file is required for the diff, so the default
            # mode prints the real transfer instead of rsync's dry run.
            # compare-dest must be a directory containing the local copy at
            # the same relative path; passing the file itself makes rsync
            # compare against a non-directory.
            compare_to = (
                local_file if local_file.is_dir() else local_file.parent
            )
            self._rsync(
                diffdir,
                remotef,
                Action.DIFF,
                compare_to=compare_to,
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
                if self.real and result.returncode:
                    raise TransferError(
                        f"difftool failed with exit code {result.returncode}"
                    )
                return

            flags = []
            if ignore:
                flags.append("--ignore-all-space")
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
            stages = [Argv(tuple(argv))]
            # A pager is useful interactively but would hide git's status and
            # block a pipe, so only add it when stdout is a terminal.
            if sys.stdout.isatty():
                stages.append(Argv(("less",)))
            pipeline = Pipeline(tuple(stages))
            result = run(pipeline, real=self.real, capture=False)
            if self.real and result.returncode:
                raise TransferError(
                    f"git diff failed with exit code {result.returncode}"
                )
            if self.real:
                ui.echo("Files are the same.")

    def _difftool_command(self, tmp_file_fixed, local_file, diffdir):
        """Build the configured GUI difftool command."""
        gui = self.project.difftool
        if not gui:
            ui.error("No difftool program defined in sink.yaml")
        command = gui.format(
            remote=f'"{tmp_file_fixed}"', local=f'"{local_file}"'
        )
        return Argv(tuple(shlex.split(command)))

    def _locations(self, filename):
        """Map a local path to its remote path."""
        local = Path(filename)
        # A relative remote path is derived from the local path.  Reject a
        # path outside project.root rather than silently turning an absolute
        # local path into a remote one.
        try:
            relative = local.resolve().relative_to(self.project.root.resolve())
        except ValueError:
            raise TransferError(
                f"Path is outside the project root "
                f"({self.project.root}): {local}"
            ) from None
        if self.server.root is None:
            ui.error(f"Server has no root ({self.server.name}).")
        remote = Path(self.server.root, relative)
        return {"local": local, "remote": remote}

    def _rsync(
        self,
        localf,
        remotef,
        action,
        extra_flags=(),
        single=False,
        compare_to=None,
        native_dry_run=True,
    ):
        """Build and run one rsync action."""
        command = self._rsync_command(
            localf,
            remotef,
            action,
            self.server,
            extra_flags=self._flags(extra_flags),
            compare_to=compare_to,
            native_dry_run=native_dry_run,
        )
        self.run(command, single, action, self.server, remotef, localf)

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
        """Build the rsync argv for one action."""
        if not server.ssh:
            ui.error(f"Server has no ssh settings ({server.name}).")
        ssh = server.ssh[0]
        rsyncb = self.project.rsync_binary

        argv = [rsyncb]

        # rsync accepts one remote-shell command.  Keep port and identity in
        # the same --rsh value; passing a separate -e would silently win.
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

        excluded = self._excluded() if self.multiple else ()
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
        """Confirm, execute, and report an rsync command."""
        doit = True
        if not single and action == Action.PUT and server.warn and self.real:
            doit = False
            msg = (
                f" WARNING: You are about to overwrite the {server.name} "
                f'"{remotef}" files, continue?'
            )
            if click.confirm(msg):
                doit = True

        if not doit:
            return

        result = run(command, real=self.real, capture=True)
        if result.stdout:
            ui.output(result.stdout)
        if result.returncode:
            ui.error(f"\n{result.stderr}")
        elif single:
            ui.display_success(
                self.real, server=server.name, message=str(localf)
            )
        else:
            message = (
                "upload complete"
                if action == Action.PUT
                else "download complete"
            )
            ui.display_success(self.real, server=server.name, message=message)

    def error_code(self, code):
        """Return the rsync error description for a code."""
        code = str(code)
        codes = {
            "1": "Syntax or usage error",
            "2": "Protocol incompatibility",
            "3": "Errors selecting input/output files, dirs",
            "4": "Requested  action  not  supported: an attempt was made to manipulate 64-bit files on a platform that cannot support them; or an option was specified that is supported by the client and not by the server.",
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

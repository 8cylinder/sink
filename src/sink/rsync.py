"""Build and run rsync transfers."""

import fnmatch
import os
import shlex
import sys
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

import click

from sink.config.models import Action, Project, Server
from sink.errors import TransferError
from sink.shell import Argv, Pipeline, run
from sink.ui import ui

# Directory transfers must never upload credential or production-data files
# by accident.  These rules are applied before per-server includes so a later
# include cannot re-expose a secret path.  Explicit single-file transfers are
# still allowed; a directory transfer needs --allow-secret-files to override.
SAFE_EXCLUDES = (
    "sink.yaml",
    "sink.yaml.*",
    ".sink/",
    "pulls/",
    "*.sql.gz",
    ".env*",
    "*.pem",
    "*.key",
    "id_*",
    ".ssh/",
    ".git/",
    ".aws/",
    ".config/gcloud/",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "*.kdbx",
    "*.bak",
    "*~",
    ".#*",
)

_SAFE_EXCLUDE_DIRS = frozenset({".sink", "pulls", ".ssh", ".git", ".aws"})
_SAFE_EXCLUDE_FILE_PATTERNS = tuple(
    pattern for pattern in SAFE_EXCLUDES if not pattern.endswith("/")
)


# Rsync ignore owner, group, time, and perms:
# https://unix.stackexchange.com/q/102211
class Transfer:
    """Build and run rsync transfers for one project and server."""

    def __init__(
        self,
        project: Project,
        server: Server,
        real: bool = False,
        verbose: bool = False,
        silent: bool = False,
        quiet: bool = False,
        allow_secret_files: bool = False,
    ) -> None:
        """Transfer files to and from a server with rsync

        verbose: adds --verbose to rsync
        silent: adds --quiet to rsync & does not display command output
        quiet: adds --quiet to rsync
        allow_secret_files: permits secret-looking files in a directory
        transfer after printing their paths
        """
        self.verbose = bool(verbose)
        self.real = real
        self.project = project
        self.server = server
        self.quiet = quiet
        self.silent = silent
        self.allow_secret_files = bool(allow_secret_files)
        self.multiple = False

    def _excluded(self) -> tuple[str, ...]:
        """Combine project and server exclusions."""
        values = {*self.project.exclude, *self.server.exclude}
        return tuple(sorted(value for value in values if value))

    def _pulls_relative(self) -> Path | None:
        """Return the configured pulls directory relative to the root."""
        pulls = self.project.pulls_dir
        if pulls is None:
            return None
        try:
            return pulls.resolve().relative_to(self.project.root.resolve())
        except ValueError:
            return None

    def _pulls_absolute(self) -> Path | None:
        """Return the absolute configured pulls directory."""
        pulls = self.project.pulls_dir
        if pulls is None:
            return None
        return Path(pulls).resolve()

    def _safe_excludes(self) -> tuple[str, ...]:
        """Return built-in exclusions for directory transfers."""
        patterns = list(SAFE_EXCLUDES)
        pulls = self._pulls_relative()
        if pulls is not None and pulls.as_posix() not in {".", ""}:
            pattern = f"{pulls.as_posix()}/"
            if pattern not in patterns:
                patterns.append(pattern)
        return tuple(patterns)

    def _is_secret_path(
        self, path: Path, root: Path, pulls: Path | None
    ) -> bool:
        """Return whether *path* is secret material under *root*."""
        if pulls is not None and (path == pulls or pulls in path.parents):
            return True
        if path.name in _SAFE_EXCLUDE_DIRS:
            return True
        if path.name == "gcloud" and path.parent.name == ".config":
            return True
        relative = path.relative_to(root)
        if any(part in _SAFE_EXCLUDE_DIRS for part in relative.parts):
            return True
        parts = relative.parts
        for index in range(len(parts) - 1):
            if parts[index] == ".config" and parts[index + 1] == "gcloud":
                return True
        return any(
            fnmatch.fnmatch(path.name, pattern)
            for pattern in _SAFE_EXCLUDE_FILE_PATTERNS
        )

    def _secret_paths(self, local: Path) -> list[Path]:
        """Return secret-looking paths under the local transfer root."""
        root = Path(local).resolve()
        pulls = self._pulls_absolute()
        found: set[Path] = set()
        if self._is_secret_path(root, root, pulls):
            found.add(root)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            base = Path(dirpath)
            for name in list(dirnames):
                path = base / name
                if self._is_secret_path(path, root, pulls):
                    found.add(path)
                    # Do not descend into a credential or metadata tree.
                    dirnames.remove(name)
            for name in filenames:
                path = base / name
                if self._is_secret_path(path, root, pulls):
                    found.add(path)
        return sorted(found)

    def _check_secret_material(self, local: Path) -> None:
        """Refuse or warn about secret files in a directory transfer."""
        paths = self._secret_paths(local)
        if not paths:
            return
        rendered = "\n".join(f"  {path}" for path in paths)
        if not self.allow_secret_files:
            raise TransferError(
                "Refusing to transfer secret-looking files:\n"
                f"{rendered}\n"
                "Use --allow-secret-files to override."
            )
        ui.warn(f"Allowing secret-looking files:\n{rendered}")

    def put(
        self,
        filename: str | Path,
        extra_flags: str | Sequence[str] | None,
        dest_override: str | Path | None = None,
    ) -> None:
        """Upload a file or directory."""
        locations = self._locations(filename)
        local = locations["local"]
        # append a / to the remote path if its a dir so rsync will
        # sync two dirs with the same name
        if local.is_dir():
            self.multiple = True
            self._check_secret_material(local)
            local = f"{local}/"
        remote = locations["remote"]
        if dest_override:
            remote = dest_override
        self._rsync(local, remote, Action.PUT, self._flags(extra_flags))

    def pull(
        self, filename: str | Path, extra_flags: str | Sequence[str] | None
    ) -> None:
        """Download a file or directory."""
        locations = self._locations(filename)
        local = locations["local"]
        remote = locations["remote"]
        # append a / to the remote path if its a dir so rsync will
        # sync two dirs with the same name
        if local.is_dir():
            remote = f"{remote}/"
            self.multiple = True
        try:
            self._rsync(local, remote, Action.PULL, self._flags(extra_flags))
        except BaseException:
            # rsync creates .NAME.XXXXXX beside a single-file destination and
            # does not always remove it when the transfer is interrupted or
            # fails.  Clean it before propagating the failure.
            if not self.multiple:
                self._remove_pull_temp(local)
            raise

    @staticmethod
    def _remove_pull_temp(local: Path) -> None:
        """Remove rsync temp files left beside an interrupted file pull."""
        for candidate in local.parent.glob(f".{local.name}.*"):
            with suppress(OSError):
                candidate.unlink()

    @staticmethod
    def _flags(
        extra_flags: str | Sequence[str] | None,
    ) -> tuple[str, ...]:
        """Normalize extra rsync flags."""
        if not extra_flags:
            return ()
        if isinstance(extra_flags, str):
            return tuple(shlex.split(extra_flags))
        return tuple(extra_flags)

    def diff(
        self,
        local_file: str | Path,
        ignore: bool = False,
        word_diff: str | None = None,
        difftool: bool = False,
    ) -> None:
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
            # mode prints the real transfer instead of rsync's dry run.  A
            # single file is always downloaded; using --compare-dest there
            # would skip identical files and leave git with no temp file.
            compare_to = local_file if local_file.is_dir() else None
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
                command = self._difftool_command(tmp_file_fixed, local_file)
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
            if self.real:
                # git diff uses 0 for "same" and 1 for "different"; values
                # above 1 are real failures.  Propagate the difference status
                # so scripts can use it, without calling differences errors.
                if result.returncode == 0:
                    ui.echo("Files are the same.")
                elif result.returncode > 1:
                    raise TransferError(
                        f"git diff failed with exit code {result.returncode}"
                    )
                else:
                    raise SystemExit(1)

    def _difftool_command(self, tmp_file_fixed: str, local_file: Path) -> Argv:
        """Build the configured GUI difftool command."""
        gui = self.project.difftool
        if not gui:
            raise TransferError("No difftool program defined in sink.yaml")
        command = gui.format(
            remote=f'"{tmp_file_fixed}"', local=f'"{local_file}"'
        )
        return Argv(tuple(shlex.split(command)))

    def _locations(self, filename: str | Path) -> dict[str, Path]:
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
        root = self.server.root
        if root is None:
            raise TransferError(f"Server has no root ({self.server.name}).")
        remote = Path(root, relative)
        return {"local": local, "remote": remote}

    def _rsync(
        self,
        localf: str | Path,
        remotef: str | Path,
        action: Action,
        extra_flags: str | Sequence[str] | None = (),
        compare_to: str | Path | None = None,
        native_dry_run: bool = True,
    ) -> None:
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
        self.run(command, action, self.server, remotef)

    def _rsync_command(
        self,
        localf: str | Path,
        remotef: str | Path,
        action: Action,
        server: Server,
        *,
        extra_flags: Sequence[str] = (),
        compare_to: str | Path | None = None,
        native_dry_run: bool = True,
    ) -> Argv:
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

        # Safe excludes must precede includes because rsync applies filter
        # rules in order and the first match wins.  The automatic
        # .env.<server> include was removed: a dotenv file is credential
        # material, so an explicit --allow-secret-files transfer is required.
        # A pull is a write to the local trust anchor, so its exclusions are
        # not overridable.  --allow-secret-files only applies to a put.
        safe_excludes_required = (
            action == Action.PULL or not self.allow_secret_files
        )
        if (
            self.multiple
            and action in (Action.PUT, Action.PULL)
            and safe_excludes_required
        ):
            for exclude in self._safe_excludes():
                argv.extend(["--exclude", exclude])

        for include in (
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

    def run(
        self,
        command: Argv,
        action: Action,
        server: Server,
        remotef: str | Path,
    ) -> None:
        """Confirm, execute, and report an rsync command."""
        doit = True
        if action == Action.PUT and server.warn and self.real:
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
        else:
            message = (
                "upload complete"
                if action == Action.PUT
                else "download complete"
            )
            ui.display_success(self.real, server=server.name, message=message)

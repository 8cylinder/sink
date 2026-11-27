"""Per-invocation runtime: working directory, output flags, lazy config."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sink.config.loader import find_config, find_repo_root, load
from sink.config.models import Config
from sink.errors import NotInProject
from sink.ui import ui


def config_trust(config: Config, cwd: Path) -> tuple[bool, str | None]:
    """Return whether a config is safe to use without explicit consent."""
    path = config.path
    try:
        stat = path.stat()
    except OSError as error:
        return False, f"cannot stat config: {error}"
    if stat.st_uid != os.getuid():
        return False, f"owned by uid {stat.st_uid}"
    if stat.st_mode & 0o002:
        return False, "world-writable"
    repo = find_repo_root(cwd.resolve())
    if repo is not None:
        try:
            path.relative_to(repo)
        except ValueError:
            return False, f"outside repository {repo}"
    return True, None


@dataclass(slots=True)
class Runtime:
    """Per-invocation config, cwd, and output flags."""

    cwd: Path
    quiet: int = 0
    config_file: Path | None = None
    _config: Config | None = None

    @classmethod
    def create(
        cls,
        *,
        cwd: Path | None = None,
        quiet: int = 0,
        config_file: Path | None = None,
    ) -> Runtime:
        """Create a runtime rooted at the current directory."""
        return cls(cwd=cwd or Path.cwd(), quiet=quiet, config_file=config_file)

    @classmethod
    def with_config(
        cls, config: Config, *, cwd: Path | None = None, quiet: int = 0
    ) -> Runtime:
        """Create a runtime around an injected config."""
        return cls(cwd=cwd or Path.cwd(), quiet=quiet, _config=config)

    @staticmethod
    def discover_config(cwd: Path) -> Path | None:
        """Find the nearest config without loading it."""
        return find_config(cwd)

    @property
    def config(self) -> Config:
        """Return the lazily loaded, cached config."""
        # Load on first use so help/version/--config work outside a project.
        # Warnings are emitted only on that first load.
        if self._config is None:
            path = self.config_file or find_config(self.cwd)
            if path is None:
                raise NotInProject(
                    "You are not in a project. A sink.yaml file was not "
                    "found in this or any directory above."
                )
            self._config = load(path)
            for warning in self._config.warnings:
                ui.warn(warning)
            trusted, reason = config_trust(self._config, self.cwd)
            if not trusted:
                ui.warn(
                    f"config {self._config.path} is untrusted ({reason}); "
                    "review it before running commands"
                )
        return self._config

    @property
    def suppress_commands(self) -> bool:
        """Whether rendered commands are hidden."""
        return self.quiet >= 1

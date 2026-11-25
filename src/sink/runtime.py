"""Per-invocation runtime: working directory, output flags, lazy config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sink.config.loader import find_config, load
from sink.config.models import Config
from sink.errors import NotInProject
from sink.ui import ui


@dataclass(slots=True)
class Runtime:
    """Per-invocation config, cwd, and output flags."""

    cwd: Path
    quiet: int = 0
    _config: Config | None = None

    @classmethod
    def create(cls, *, cwd: Path | None = None, quiet: int = 0) -> Runtime:
        """Create a runtime rooted at the current directory."""
        return cls(cwd=cwd or Path.cwd(), quiet=quiet)

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
            path = find_config(self.cwd)
            if path is None:
                raise NotInProject(
                    "You are not in a project. A sink.yaml file was not "
                    "found in this or any directory above."
                )
            self._config = load(path)
            for warning in self._config.warnings:
                ui.warn(warning)
        return self._config

    @property
    def suppress_commands(self) -> bool:
        """Whether rendered commands are hidden."""
        return self.quiet >= 1

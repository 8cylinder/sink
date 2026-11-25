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
    cwd: Path
    quiet: int = 0
    _config: Config | None = None

    @classmethod
    def create(cls, *, cwd: Path | None = None, quiet: int = 0) -> Runtime:
        return cls(cwd=cwd or Path.cwd(), quiet=quiet)

    @classmethod
    def with_config(
        cls, config: Config, *, cwd: Path | None = None, quiet: int = 0
    ) -> Runtime:
        return cls(cwd=cwd or Path.cwd(), quiet=quiet, _config=config)

    @staticmethod
    def discover_config(cwd: Path) -> Path | None:
        return find_config(cwd)

    @property
    def config(self) -> Config:
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
        return self.quiet >= 1

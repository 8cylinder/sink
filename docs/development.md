# Development

Sink uses Python 3.15, uv, Ruff, ty, pytest, pytest-cov, and import-linter.

```console
uv sync --all-groups
make check
make test
```

`make check` runs formatting, linting, type checking, import contracts, and
the full branch-coverage suite. The coverage floor is 90%.

Build documentation:

```console
make docs
make man
```

`make install-man` installs the generated `sink.1` under
`$XDG_DATA_HOME/man/man1` or `~/.local/share/man/man1`.

Source layout:

- `src/sink/cli/` — Click command modules and entry point.
- `src/sink/config/` — typed models and the pure YAML loader.
- `src/sink/` — runtime, shell execution, credentials, transfers, database,
  check, actions, UI, and completions.
- `tests/` — hermetic pytest suite.

Every source file has a module docstring; callables are documented and
non-obvious control flow is commented. `tests/test_docstrings.py` enforces
this.

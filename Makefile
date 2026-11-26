SHELL := bash

.DEFAULT_GOAL := help

UBUNTU_OLDEST ?= 20.04
UBUNTU_LATEST ?= 26.04
UBUNTU_VERSIONS ?= $(UBUNTU_OLDEST) $(UBUNTU_LATEST)
SINK_TEST_UBUNTU ?= $(UBUNTU_LATEST)

.PHONY: help sync hooks fmt fmt-check lint lint-check type arch test integration integration-oldest integration-matrix integration-down secrets docs docs-serve man install-man check ci build install uninstall upgrade clean

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync:  ## Install or update dependencies
	uv sync --all-groups

hooks:  ## Install the git hook that blocks secrets
	git config core.hooksPath .githooks

fmt:  ## Format code
	uv run ruff format .

fmt-check:  ## Check formatting without changing files
	uv run ruff format --check .

lint:  ## Lint and apply safe fixes
	uv run ruff check --fix .

lint-check:  ## Lint without changing files
	uv run ruff check .

type:  ## Type-check the project
	uv run ty check

arch:  ## Check import boundaries
	uv run lint-imports

test:  ## Run tests
	uv run pytest

integration:  ## Run Docker tests on the selected Ubuntu LTS
	SINK_TEST_UBUNTU=$(SINK_TEST_UBUNTU) uv run pytest -m integration tests/integration --no-cov

integration-oldest:  ## Run Docker tests on the oldest Ubuntu LTS
	SINK_TEST_UBUNTU=$(UBUNTU_OLDEST) uv run pytest -m integration tests/integration --no-cov

integration-matrix:  ## Run Docker tests on oldest and latest Ubuntu LTS
	@for version in $(UBUNTU_VERSIONS); do \
		echo "==> Ubuntu $$version"; \
		SINK_TEST_UBUNTU=$$version uv run pytest -m integration tests/integration --no-cov || exit $$?; \
	done

integration-down:  ## Remove leftover integration containers
	docker ps -aq --filter label=sink.integration=true | xargs -r docker rm -f

secrets:  ## Scan the repository history for secrets
	gitleaks git --redact --no-banner

docs:  ## Build HTML documentation
	uv run sphinx-build -W -b html docs docs/_build/html

docs-serve:  ## Serve documentation with live reload
	uv run sphinx-autobuild docs docs/_build/html

MANPAGE := docs/_build/man/sink.1
MANDIR ?= $(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)/man/man1

man:  ## Build the man page
	uv run sphinx-build -W -b man docs docs/_build/man

install-man: man  ## Install the man page
	mkdir -p "$(MANDIR)"
	install -m 644 "$(MANPAGE)" "$(MANDIR)/sink.1"

check: fmt-check lint-check type arch test  ## Run all checks without changing files

ci:  ## Install locked dependencies and run all checks
	uv sync --locked --all-groups
	$(MAKE) check
	$(MAKE) secrets

build:  ## Build the wheel and sdist
	uv build

install:  ## Install the app
	uv tool install --editable --force .

uninstall:  ## Remove the installed tool
	uv tool uninstall sink

upgrade:  ## Upgrade dependencies and the lockfile
	uv sync --upgrade --all-groups

clean:  ## Remove build and test artifacts
	rm -rf build dist docs/_build .pytest_cache .ruff_cache .ty_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

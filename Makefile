SHELL := bash

.DEFAULT_GOAL := help
.PHONY: help sync build clean

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync:  ## Install or update dependencies
	uv sync --all-groups

build:  ## Build the wheel and sdist
	uv build

clean:  ## Remove build and test artifacts
	rm -rf build dist .pytest_cache .ruff_cache .ty_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

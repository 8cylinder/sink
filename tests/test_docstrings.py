"""Enforce module, class, and function docstrings."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "sink"
TESTS = ROOT / "tests"


def callables(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        if node.name.startswith("__") and node.name.endswith("__"):
            continue
        yield node


def test_source_modules_have_docstrings() -> None:
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in SRC.rglob("*.py")
        if ast.get_docstring(ast.parse(path.read_text())) is None
    ]
    assert missing == []


def test_source_callables_have_docstrings() -> None:
    missing = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in callables(tree):
            if ast.get_docstring(node) is None:
                missing.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                )
    assert missing == []


def test_test_modules_have_docstrings() -> None:
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in TESTS.glob("*.py")
        if ast.get_docstring(ast.parse(path.read_text())) is None
    ]
    assert missing == []

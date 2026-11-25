"""Sphinx configuration for Sink's HTML and man-page documentation."""

from __future__ import annotations

from importlib.metadata import version as package_version

project = "Sink"
author = "Sheldon McGrandle"
copyright = "2018-2026 Sheldon McGrandle and contributors"
release = package_version("sink")
version = release

extensions = [
    "myst_parser",
    "sphinx_click",
]
myst_heading_anchors = 3
myst_enable_extensions = ["colon_fence"]
exclude_patterns = ["_build"]

html_theme = "furo"
html_title = f"Sink {release} documentation"
html_short_title = "Sink"
html_static_path: list[str] = []

man_pages = [
    ("cli", "sink", "Sink command line tool", [author], 1),
]
man_show_urls = False

"""Find the pages directories of documentation sites inside a repository.

Docs generators serve pages from a source directory, so links such as ``/guide/intro`` or ``./intro`` resolve
against that directory and may leave out the ``.md`` extension. Detecting the generator's config lets
mdlinkcheck resolve those links without ``--site-root``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .checker import DEFAULT_EXCLUDES

_DOCUSAURUS = ("docusaurus.config.js", "docusaurus.config.ts", "docusaurus.config.mjs", "docusaurus.config.cjs")
_VOCS = ("vocs.config.ts", "vocs.config.tsx", "vocs.config.js", "vocs.config.mjs")
_MKDOCS = ("mkdocs.yml", "mkdocs.yaml")
_STRING_OPTION = r"""\b{}\s*:\s*['"]([^'"]+)['"]"""


def _option(text: str, name: str) -> str | None:
    m = re.search(_STRING_OPTION.format(name), text)
    return m.group(1) if m else None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _docusaurus(config: Path) -> list[Path]:
    base = config.parent
    # Links are either relative to the docs folder (routeBasePath "/") or include the
    # route prefix ("/docs/..."), which resolves against the site folder itself.
    return [base / "docs", base / "src" / "pages", base / "static", base]


def _vocs(config: Path) -> list[Path]:
    base = config.parent
    text = _read(config)
    src = base / (_option(text, "srcDir") or _option(text, "rootDir") or "docs")
    return [src / "pages", src / "public", base / "public"]


def _vitepress(config_dir: Path) -> list[Path]:
    base = config_dir.parent
    config = next((config_dir / n for n in ("config.ts", "config.mts", "config.js", "config.mjs")), None)
    src_dir = _option(_read(config), "srcDir") if config else None
    src = base / src_dir if src_dir else base
    return [src, src / "public"]


def _mkdocs(config: Path) -> list[Path]:
    m = re.search(r"^docs_dir\s*:\s*['\"]?([^'\"\n#]+?)['\"]?\s*(?:#.*)?$", _read(config), re.M)
    return [config.parent / (m.group(1) if m else "docs")]


def detect_site_roots(root: Path) -> list[Path]:
    """Return existing site page directories for every docs site config found under ``root``."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d == ".vitepress" or (d not in DEFAULT_EXCLUDES and not d.startswith("."))
        ]
        here = Path(dirpath)
        names = set(filenames)
        if here.name == ".vitepress":
            found += _vitepress(here)
            dirnames[:] = []
            continue
        for name in _DOCUSAURUS:
            if name in names:
                found += _docusaurus(here / name)
                break
        for name in _VOCS:
            if name in names:
                found += _vocs(here / name)
                break
        for name in _MKDOCS:
            if name in names:
                found += _mkdocs(here / name)
                break
    unique: list[Path] = []
    for path in found:
        path = path.resolve()
        if path.is_dir() and path not in unique:
            unique.append(path)
    return unique

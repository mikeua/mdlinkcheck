"""Resolve each link in a set of Markdown files and report the broken ones."""

from __future__ import annotations

import difflib
import fnmatch
import os
import re
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from re import Pattern
from urllib.parse import unquote

from .markdown import Document, parse

MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdx")
DEFAULT_EXCLUDES = (".git", "node_modules", ".venv", "venv", "__pycache__")

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_TEMPLATE = re.compile(r"\{\{|\{%|\$\{")
_LINE_ANCHOR = re.compile(r"^L\d+(C\d+)?(-L\d+(C\d+)?)?$", re.I)
_FOOTNOTE_DEF = re.compile(r"^ {0,3}\[\^([^\]]+)\]:", re.M)
_IGNORE_MARK = "mdlinkcheck-ignore"
_INDEX_PAGES = ("README.md", "readme.md", "Readme.md", "index.md", "index.mdx")


@dataclass(frozen=True)
class Problem:
    path: Path
    line: int
    column: int
    target: str
    rule: str
    message: str


@dataclass
class Options:
    root: Path
    excludes: tuple[str, ...] = ()
    ignore: tuple[Pattern[str], ...] = ()
    check_absolute: bool = True
    use_git: bool = True
    #: Directories served by a docs site (Docusaurus, VitePress, Vocs, MkDocs...).
    #: Links inside them, and '/...' links, may omit the extension or point at a folder's index page.
    site_roots: tuple[Path, ...] = ()
    #: Route prefixes served from a specific folder, e.g. ("v3.4", versioned_docs/version-v3.4) for an
    #: archived Docusaurus version: "/v3.4/guide" is the page at versioned_docs/version-v3.4/guide.
    site_routes: tuple[tuple[str, Path], ...] = ()


class Checker:
    def __init__(self, options: Options) -> None:
        self.options = options
        self.root = options.root.resolve()
        self._docs: dict[Path, Document] = {}
        self._site_roots = tuple(p.resolve() for p in options.site_roots)

    # -- file discovery -------------------------------------------------

    def collect(self, paths: Iterable[Path]) -> list[Path]:
        files: set[Path] = set()
        for p in paths:
            p = p.resolve()
            if p.is_file():
                files.add(p)
            elif p.is_dir():
                files.update(self._walk(p))
        return sorted(f for f in files if not self._excluded(f))

    def _walk(self, directory: Path) -> Iterator[Path]:
        if self.options.use_git:
            listed = _git_ls_files(directory)
            if listed is not None:
                yield from (f for f in listed if f.suffix.lower() in MARKDOWN_SUFFIXES and f.is_file())
                return
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDES]
            for name in filenames:
                if name.lower().endswith(MARKDOWN_SUFFIXES):
                    yield Path(dirpath, name)

    def _excluded(self, f: Path) -> bool:
        rel = _relpath(f, self.root)
        parts = Path(rel).parts
        if any(part in DEFAULT_EXCLUDES for part in parts[:-1]):
            return True
        for pattern in self.options.excludes:
            pattern = pattern.rstrip("/")
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, pattern + "/*"):
                return True
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
        return False

    # -- checking -------------------------------------------------------

    def document(self, path: Path) -> Document:
        doc = self._docs.get(path)
        if doc is None:
            text = path.read_text(encoding="utf-8", errors="replace")
            doc = parse(text)
            for label in _FOOTNOTE_DEF.findall(text):
                label = label.lower()
                doc.anchors.update({f"fn-{label}", f"fnref-{label}"})
            self._docs[path] = doc
        return doc

    def check_file(self, path: Path) -> list[Problem]:
        text_lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        problems = []
        for link in self.document(path).links:
            if _suppressed(text_lines, link.line):
                continue
            problem = self.check_link(path, link.target, link.line, link.column)
            if problem:
                problems.append(problem)
        return problems

    def check(self, files: Iterable[Path]) -> list[Problem]:
        problems: list[Problem] = []
        for f in files:
            problems.extend(self.check_file(f))
        return problems

    def check_link(self, source: Path, target: str, line: int, column: int) -> Problem | None:
        def problem(rule: str, message: str) -> Problem:
            return Problem(source, line, column, target, rule, message)

        if not target or _SCHEME.match(target) or target.startswith("//") or _TEMPLATE.search(target):
            return None
        if any(p.search(target) for p in self.options.ignore):
            return None

        raw_path, _, raw_anchor = target.partition("#")
        raw_path = raw_path.split("?", 1)[0]
        path_part = unquote(raw_path)
        anchor = unquote(raw_anchor)

        if not path_part:
            dest = source
        elif path_part.startswith("/"):
            if not self.options.check_absolute:
                return None
            route = path_part.strip("/")
            candidates = [
                folder / route[len(prefix) :].lstrip("/")
                for prefix, folder in self.options.site_routes
                if route == prefix or route.startswith(prefix + "/")
            ]
            candidates += [site / path_part.lstrip("/") for site in self._site_roots]
            candidates.append(self.root / path_part.lstrip("/"))
            dest = next((p for p in map(self._resolve_page, candidates) if p), candidates[-1])
        else:
            dest = source.parent / path_part
            if not dest.exists() and self._in_site(source):
                # An index page is served at its folder's URL without a trailing slash
                # (/guide/index.md -> /guide), so its relative links resolve from the parent folder.
                via_url = source.parent.parent / path_part if source.stem.lower() in ("index", "readme") else None
                dest = self._resolve_page(dest) or (via_url and self._resolve_page(via_url)) or dest

        if path_part:
            if not dest.exists():
                return problem("missing-file", f"'{path_part}' does not exist{_suggest_file(dest)}")
            wrong = _case_mismatch(dest)
            if wrong:
                return problem(
                    "case-mismatch",
                    f"'{path_part}' only matches '{wrong}' with different case "
                    "(this works on macOS/Windows but not on GitHub or Linux)",
                )

        if not anchor:
            return None
        if dest.is_dir():
            index = next((dest / n for n in _INDEX_PAGES if (dest / n).is_file()), None)
            if index is None:
                return None
            dest = index
        if dest.suffix.lower() not in MARKDOWN_SUFFIXES or _LINE_ANCHOR.match(anchor):
            return None

        key = anchor.lower()
        if key.startswith("user-content-"):
            key = key[len("user-content-") :]
        anchors = self.document(dest.resolve()).anchors
        if key in anchors:
            return None
        where = "this file" if dest.resolve() == source.resolve() else f"'{_relpath(dest, source.parent)}'"
        hint = difflib.get_close_matches(key, anchors, n=1, cutoff=0.6)
        suffix = f"; did you mean '#{hint[0]}'?" if hint else ""
        return problem("missing-anchor", f"no heading or anchor '#{anchor}' in {where}{suffix}")

    def _in_site(self, path: Path) -> bool:
        return any(site == path or site in path.parents for site in self._site_roots)

    def _resolve_page(self, dest: Path) -> Path | None:
        """Resolve a docs-site route ('/guide/intro', './intro') to the page that serves it."""
        if dest.exists():
            return dest
        if not self._site_roots:
            return None
        for suffix in MARKDOWN_SUFFIXES:
            if dest.with_name(dest.name + suffix).is_file():
                return dest.with_name(dest.name + suffix)
        return None


def _suppressed(lines: list[str], line: int) -> bool:
    current = lines[line - 1] if 0 < line <= len(lines) else ""
    above = lines[line - 2].strip() if line >= 2 else ""
    return _IGNORE_MARK in current or (above.startswith("<!--") and _IGNORE_MARK in above)


def _relpath(path: Path, start: Path) -> str:
    return Path(os.path.relpath(path, start)).as_posix()


def _suggest_file(dest: Path) -> str:
    parent = dest.parent
    if not parent.is_dir():
        return ""
    for suffix in MARKDOWN_SUFFIXES:
        if dest.suffix == "" and (parent / (dest.name + suffix)).exists():
            return f"; did you mean '{dest.name + suffix}'?"
    names = os.listdir(parent)
    hint = difflib.get_close_matches(dest.name, names, n=1, cutoff=0.85)
    return f"; did you mean '{hint[0]}'?" if hint else ""


@cache
def _listdir(directory: str) -> frozenset[str]:
    try:
        return frozenset(os.listdir(directory))
    except OSError:
        return frozenset()


def _case_mismatch(dest: Path) -> str | None:
    """Return the on-disk spelling if ``dest`` only exists case-insensitively."""
    p = Path(os.path.abspath(dest))
    while p.parent != p:
        names = _listdir(str(p.parent))
        if names and p.name not in names and p.name not in (".", ".."):
            match = next((n for n in names if n.lower() == p.name.lower()), None)
            if match:
                return match
        p = p.parent
    return None


def _git_ls_files(directory: Path) -> list[Path] | None:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=directory,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [directory / name for name in out.decode("utf-8", "surrogateescape").split("\0") if name]

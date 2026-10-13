from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from . import __version__
from .checker import Checker, Options, Problem


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mdlinkcheck",
        description="Find broken relative links and #anchors in Markdown files, offline, "
        "using GitHub's heading-anchor rules.",
    )
    p.add_argument("paths", nargs="*", type=Path, default=[Path(".")], help="files or directories (default: .)")
    p.add_argument(
        "--root",
        type=Path,
        help="directory that links starting with '/' are relative to (default: git top level, else cwd)",
    )
    p.add_argument(
        "-e", "--exclude", action="append", default=[], metavar="GLOB", help="skip files matching GLOB (repeatable)"
    )
    p.add_argument(
        "-i",
        "--ignore",
        action="append",
        default=[],
        metavar="REGEX",
        help="don't check link targets matching REGEX (repeatable)",
    )
    p.add_argument(
        "--no-absolute", action="store_true", help="don't check links that start with '/' (e.g. doc-site routes)"
    )
    p.add_argument(
        "-s",
        "--site-root",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help="pages directory of a docs site (Docusaurus, VitePress, Vocs, ...): '/route' links resolve against it and "
        "links inside it may omit '.md' (repeatable)",
    )
    p.add_argument("--no-git", action="store_true", help="walk directories directly instead of using 'git ls-files'")
    p.add_argument(
        "-f",
        "--format",
        choices=("text", "github", "json"),
        default=None,
        help="output format (default: github inside GitHub Actions, else text)",
    )
    p.add_argument("-q", "--quiet", action="store_true", help="only print problems, no summary")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _default_root() -> Path:
    import subprocess

    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout
        return Path(out.strip())
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd()


def _display(path: Path) -> str:
    try:
        return Path(os.path.relpath(path)).as_posix()
    except ValueError:
        return path.as_posix()


def _escape_gh(s: str, prop: bool = False) -> str:
    s = s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if prop:
        s = s.replace(":", "%3A").replace(",", "%2C")
    return s


def report(problems: Sequence[Problem], fmt: str, out: TextIO | None = None) -> None:
    out = out or sys.stdout
    if fmt == "json":
        json.dump(
            [
                {
                    "path": _display(p.path),
                    "line": p.line,
                    "column": p.column,
                    "target": p.target,
                    "rule": p.rule,
                    "message": p.message,
                }
                for p in problems
            ],
            out,
            indent=2,
        )
        out.write("\n")
        return
    for p in problems:
        if fmt == "github":
            out.write(
                f"::error file={_escape_gh(_display(p.path), True)},line={p.line},col={p.column},"
                f"title={_escape_gh('mdlinkcheck ' + p.rule, True)}::{_escape_gh(p.message)}\n"
            )
        else:
            out.write(f"{_display(p.path)}:{p.line}:{p.column}: {p.target}: {p.message} [{p.rule}]\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = args.format or ("github" if os.environ.get("GITHUB_ACTIONS") == "true" else "text")
    try:
        ignore = tuple(re.compile(r) for r in args.ignore)
    except re.error as e:
        print(f"mdlinkcheck: invalid --ignore pattern: {e}", file=sys.stderr)
        return 2
    for path in [*args.paths, *args.site_root]:
        if not path.exists():
            print(f"mdlinkcheck: {path}: no such file or directory", file=sys.stderr)
            return 2

    options = Options(
        root=args.root or _default_root(),
        excludes=tuple(args.exclude),
        ignore=ignore,
        check_absolute=not args.no_absolute,
        use_git=not args.no_git,
        site_roots=tuple(args.site_root),
    )
    checker = Checker(options)
    files = checker.collect(args.paths)
    problems = checker.check(files)
    try:
        report(problems, fmt)
    except BrokenPipeError:  # e.g. `mdlinkcheck | head`
        sys.stderr.close()
        return 1
    if not args.quiet and fmt != "json":
        links = sum(len(checker.document(f).links) for f in files)
        status = f"{len(problems)} broken" if problems else "no broken links"
        print(f"mdlinkcheck: {len(files)} files, {links} links, {status}", file=sys.stderr)
        absolute = sum(1 for p in problems if p.rule == "missing-file" and p.target.startswith("/"))
        if absolute >= 5 and not args.site_root:
            print(
                f"mdlinkcheck: {absolute} of these are '/...' links; if they are docs-site routes, "
                "pass --site-root <pages dir> or --no-absolute",
                file=sys.stderr,
            )
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

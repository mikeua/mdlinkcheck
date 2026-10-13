# mdlinkcheck

[![CI](https://github.com/mikeua/mdlinkcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/mikeua/mdlinkcheck/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mdlinkcheck.svg)](https://pypi.org/project/mdlinkcheck/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)

Find broken **relative links** and **`#anchors`** in Markdown files: offline, fast, with no dependencies, and using
the same heading-anchor rules as GitHub.

```console
$ mdlinkcheck src/engine
src/engine/prague.md:72:38: #BlobsBundleV1: no heading or anchor '#BlobsBundleV1' in this file [missing-anchor]
src/engine/refactor-ssz.md:23:23: #max-constants: no heading or anchor '#max-constants' in this file; did you mean '#max_-constants'? [missing-anchor]
src/engine/refactor-ssz.md:524:26: #get-forkpayloadspayloadid: no heading or anchor '#get-forkpayloadspayloadid' in this file; did you mean '#get-payloadspayloadid'? [missing-anchor]
src/engine/refactor.md:447:39: ./refactor-ssz.md#max-constants: no heading or anchor '#max-constants' in 'refactor-ssz.md'; did you mean '#max_-constants'? [missing-anchor]
mdlinkcheck: 13 files, 460 links, 4 broken
```

## Why

External-URL checkers ([lychee](https://github.com/lycheeverse/lychee),
[markdown-link-check](https://github.com/tcort/markdown-link-check)) are great at telling you a website is down. They
are much less good at the links that break *inside* a repository:

- a section gets renamed and every `other-doc.md#old-title` link silently stops scrolling anywhere;
- a heading contains code, punctuation or underscores, so its real anchor isn't what you'd guess
  (`` ## `MAX_*` constants `` is `#max_-constants`, `` ## Definition of `channel_id` `` is `#definition-of-channel_id`);
- a file moves and `../dump.md` becomes `./dump.md` in one place but not another;
- a link works on your Mac but not on GitHub, because the file name differs only in case.

GitHub doesn't warn about any of these. mdlinkcheck does, without touching the network, so it is fast enough for a
pre-commit hook and deterministic enough for CI.

## Install

```sh
pipx install mdlinkcheck
# or
pip install mdlinkcheck
```

Python 3.9 or newer; no third-party dependencies.

## Usage

```sh
mdlinkcheck                 # every Markdown file in the repository
mdlinkcheck docs README.md  # specific files and directories
```

It exits with `1` if any link is broken, `0` otherwise, and `2` on usage errors.

| Option | Description |
|---|---|
| `-e, --exclude GLOB` | Skip files matching `GLOB` (repeatable), e.g. `-e 'vendor/*' -e CHANGELOG.md`. |
| `-i, --ignore REGEX` | Don't check link targets matching `REGEX` (repeatable), e.g. `-i '^generated/'`. |
| `-s, --site-root DIR` | Pages directory of a docs site (Docusaurus, VitePress, Vocs, ...). `/route` links resolve against it, and links inside it may leave out `.md`. Repeatable, e.g. for a `public/` assets folder. |
| `--no-absolute` | Don't check links that start with `/`. |
| `--root DIR` | Directory that `/` links are relative to (default: the git top level). |
| `--no-git` | Walk directories directly instead of using `git ls-files` (which skips ignored files). |
| `-f, --format` | `text`, `github` (workflow annotations; the default inside GitHub Actions) or `json`. |
| `-q, --quiet` | Don't print the summary line. |

To skip a single link, put `<!-- mdlinkcheck-ignore -->` on the same line or on the line above it.

### GitHub Actions

```yaml
- uses: actions/checkout@v4
- uses: mikeua/mdlinkcheck@v0.1.0
  with:
    args: --exclude CHANGELOG.md .
```

Broken links show up as annotations on the pull request diff.

### pre-commit

```yaml
repos:
  - repo: https://github.com/mikeua/mdlinkcheck
    rev: v0.1.0
    hooks:
      - id: mdlinkcheck
```

## What it checks

| Rule | Example |
|---|---|
| `missing-file` | `[guide](docs/guid.md)` when there is no `docs/guid.md` (suggests close matches, such as a missing `.md`) |
| `missing-anchor` | `[x](#instal)` or `[x](api.md#old-name)` when no heading, `{#custom-id}`, `<a name>`/`id=` or footnote produces that anchor (suggests the closest one) |
| `case-mismatch` | `[x](Guide.md)` when the file is `guide.md`: fine on macOS and Windows, broken on GitHub and Linux |

Links are found in inline links and images, reference definitions (`[x]: target`) and HTML `href`/`src`
attributes. Code blocks, code spans and HTML comments are skipped, as are external URLs (`https:`, `mailto:` and other
schemes), GitHub line anchors (`#L10-L20`) and anything that looks like a template placeholder.

Anchors follow GitHub's rules: the heading is rendered to plain text, lowercased, stripped of everything except
letters, digits, `-`, `_` and spaces, and each space becomes `-`. Repeated headings get `-1`, `-2`, ... suffixes, and
links may use the `user-content-` prefix and percent-encoding. Headings inside list items and block quotes count too.

## Bugs found with it

- [graphprotocol/graph-node#6740](https://github.com/graphprotocol/graph-node/pull/6740): renamed section, missing
  file, wrong relative path
- [ethereum/execution-apis#943](https://github.com/ethereum/execution-apis/pull/943): anchors in the Engine API spec
- [lightning/bolts#1364](https://github.com/lightning/bolts/pull/1364): links between Lightning BOLT specs

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e . pytest ruff
pytest
ruff check . && ruff format --check .
```

## License

[MIT](LICENSE)

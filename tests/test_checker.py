import json
import re
from pathlib import Path

import pytest

from mdlinkcheck.checker import Checker, Options
from mdlinkcheck.cli import main


def write(root: Path, files: dict) -> None:
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def run(root: Path, **kw):
    checker = Checker(Options(root=root, use_git=False, **kw))
    return [
        (p.path.relative_to(root.resolve()).as_posix(), p.line, p.rule) for p in checker.check(checker.collect([root]))
    ]


@pytest.fixture
def repo(tmp_path):
    write(
        tmp_path,
        {
            "README.md": "# Project\n\n## Install\n\n[ok](#install) [bad](#instal)\n"
            "[guide](docs/guide.md#usage) [gone](docs/gone.md) [dir](docs/)\n"
            "[ext](https://example.com/x.md#nope) [mail](mailto:a@b.c)\n",
            "docs/guide.md": "# Guide\n\n## Usage\n\n[back](../README.md#project) [wrong](../README.md#projects)\n"
            "[img](../img/logo.png) [line](../src/main.py#L10) [root](/README.md#install)\n",
            "img/logo.png": "",
            "src/main.py": "",
        },
    )
    return tmp_path


def test_reports_only_broken_links(repo):
    assert run(repo) == [
        ("README.md", 5, "missing-anchor"),
        ("README.md", 6, "missing-file"),
        ("docs/guide.md", 5, "missing-anchor"),
    ]


def test_suggestions(repo):
    checker = Checker(Options(root=repo, use_git=False))
    messages = [p.message for p in checker.check(checker.collect([repo]))]
    assert "did you mean '#install'?" in messages[0]
    assert "did you mean '#project'?" in messages[2]


def test_absolute_links_can_be_skipped(tmp_path):
    write(tmp_path, {"a.md": "[x](/docs/route) [y](/a.md)\n"})
    assert run(tmp_path) == [("a.md", 1, "missing-file")]
    assert run(tmp_path, check_absolute=False) == []


def test_ignore_patterns(tmp_path):
    write(tmp_path, {"a.md": "[x](generated/api.md) [y](missing.md)\n"})
    assert run(tmp_path, ignore=(re.compile(r"^generated/"),)) == [("a.md", 1, "missing-file")]


def test_inline_suppression(tmp_path):
    write(
        tmp_path,
        {
            "a.md": "[x](nope.md) <!-- mdlinkcheck-ignore -->\n\n"
            "<!-- mdlinkcheck-ignore -->\n[y](nope.md)\n[z](nope.md)\n"
        },
    )
    assert run(tmp_path) == [("a.md", 5, "missing-file")]


def test_excludes(tmp_path):
    write(tmp_path, {"a.md": "[x](nope.md)\n", "vendor/b.md": "[x](nope.md)\n", "node_modules/c.md": "[x](nope.md)\n"})
    assert run(tmp_path, excludes=("vendor",)) == [("a.md", 1, "missing-file")]


def test_directory_anchor_uses_readme(tmp_path):
    write(tmp_path, {"a.md": "[x](sub/#intro) [y](sub/#outro)\n", "sub/README.md": "# Intro\n"})
    assert run(tmp_path) == [("a.md", 1, "missing-anchor")]


def test_percent_encoded_and_user_content_anchors(tmp_path):
    write(
        tmp_path,
        {
            "a.md": "# Über uns\n\n[x](#%C3%BCber-uns) [y](#user-content-%C3%BCber-uns) [z](my%20file.md)\n",
            "my file.md": "",
        },
    )
    assert run(tmp_path) == []


def test_footnotes(tmp_path):
    write(tmp_path, {"a.md": "Text[^1] and [back](#fn-1)\n\n[^1]: note\n"})
    assert run(tmp_path) == []


def test_extensionless_suggestion(tmp_path):
    write(tmp_path, {"a.md": "[x](guide)\n", "guide.md": ""})
    checker = Checker(Options(root=tmp_path, use_git=False))
    [problem] = checker.check(checker.collect([tmp_path]))
    assert "did you mean 'guide.md'?" in problem.message


def test_cli_exit_codes_and_formats(repo, capsys, monkeypatch):
    monkeypatch.chdir(repo)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert main(["--no-git", "--root", str(repo), "."]) == 1
    out = capsys.readouterr()
    assert "README.md:5:" in out.out and "missing-anchor" in out.out
    assert "3 broken" in out.err

    assert main(["--no-git", "--root", str(repo), "-f", "json", "."]) == 1
    data = json.loads(capsys.readouterr().out)
    assert {d["rule"] for d in data} == {"missing-anchor", "missing-file"}

    assert main(["--no-git", "--root", str(repo), "-f", "github", "docs"]) == 1
    assert capsys.readouterr().out.startswith("::error file=docs/guide.md,line=5,")

    (repo / "clean.md").write_text("# Clean\n[x](#clean)\n")
    assert main(["--no-git", "clean.md"]) == 0


def test_cli_missing_path(capsys):
    assert main(["definitely/not/here"]) == 2


def test_site_root_routes(tmp_path):
    write(
        tmp_path,
        {
            "docs/pages/index.mdx": "# Home\n[a](/guide/intro#setup) [b](./guide/intro)\n"
            "[c](/guide/) [d](/guide/nope)\n",
            "docs/pages/guide/intro.md": "# Intro\n## Setup\n",
            "docs/pages/guide/index.md": "# Guide\n",
            "README.md": "[e](docs/pages/guide/intro)\n",
        },
    )
    assert run(tmp_path, site_roots=(tmp_path / "docs/pages",)) == [
        ("README.md", 1, "missing-file"),  # outside the site, GitHub needs the extension
        ("docs/pages/index.mdx", 3, "missing-file"),
    ]


def test_headings_inside_lists_and_quotes(tmp_path):
    write(tmp_path, {"a.md": "* #### *Peers*:\n  text\n\n> ## Note\n\n[x](#peers) [y](#note)\n"})
    assert run(tmp_path) == []


def _case_insensitive_fs(path: Path) -> bool:
    probe = path / "CaseProbe"
    probe.write_text("")
    return (path / "caseprobe").exists()


def test_case_mismatch(tmp_path):
    write(tmp_path, {"a.md": "[x](docs/Guide.md)\n", "docs/guide.md": "# Guide\n"})
    expected = "case-mismatch" if _case_insensitive_fs(tmp_path) else "missing-file"
    assert run(tmp_path) == [("a.md", 1, expected)]

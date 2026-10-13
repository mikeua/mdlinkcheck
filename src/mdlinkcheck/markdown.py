"""Just enough Markdown parsing to find headings, anchors and link targets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .slug import Slugger, custom_id

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
# Block-quote and list-item markers that can precede a heading: "> ## Note", "* #### *Term*:"
_CONTAINERS = re.compile(r"^(?:[ \t]*(?:>|[-*+]|\d{1,9}[.)])(?=[ \t]|$))+[ \t]?")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_FRONT_MATTER = re.compile(r"\A(?:\ufeff)?---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?=\n|\Z)", re.S)
_CODE_SPAN = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)", re.S)
_HTML_ID = re.compile(r"""<[A-Za-z][^>]*?\s(?:id|name)\s*=\s*["']([^"']+)["']""")

# [text](target "title")  /  ![alt](target)
_INLINE_LINK = re.compile(r"\]\(\s*(<[^>\n]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)")
# [label]: target
_REF_DEF = re.compile(r"^ {0,3}\[([^\]^][^\]]*)\]:[ \t]*(<[^>\n]*>|\S+)", re.M)
# <a href="...">, <img src="...">
_HTML_LINK = re.compile(r"""<(?:a|img|source)\b[^>]*?\s(?:href|src)\s*=\s*["']([^"']*)["']""", re.I)


@dataclass
class Link:
    target: str
    line: int
    column: int


@dataclass
class Document:
    anchors: set[str] = field(default_factory=set)
    links: list[Link] = field(default_factory=list)


def _blank(m: re.Match[str]) -> str:
    """Replace a match with spaces, keeping newlines so offsets stay valid."""
    return re.sub(r"[^\n]", " ", m.group(0))


def mask_code(text: str) -> tuple[str, list[bool]]:
    """Blank out fenced code blocks and HTML comments.

    Returns the masked text and, per line, whether it was inside a fence.
    """
    text = _FRONT_MATTER.sub(_blank, _HTML_COMMENT.sub(_blank, text))
    lines = text.split("\n")
    in_fence: list[bool] = []
    fence: str | None = None
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                in_fence.append(True)
                lines[i] = ""
                continue
            in_fence.append(False)
        else:
            in_fence.append(True)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not line[m.end() :].strip():
                fence = None
            lines[i] = ""
    return "\n".join(lines), in_fence


def parse(text: str) -> Document:
    doc = Document()
    masked, in_fence = mask_code(text)
    lines = masked.split("\n")
    slugger = Slugger()

    prev = ""
    for i, line in enumerate(lines):
        heading = None
        m = _ATX.match(_CONTAINERS.sub("", line, count=1))
        if m and not in_fence[i]:
            heading = m.group(2) or ""
        elif (
            _SETEXT.match(line)
            and prev.strip()
            and not in_fence[i - 1]
            and not _ATX.match(prev)
            and not (line.strip().startswith("-") and _looks_like_list_or_rule(prev))
        ):
            heading = prev.strip()
        if heading is not None:
            cid = custom_id(heading)
            if cid:
                doc.anchors.add(cid.lower())
            doc.anchors.add(slugger.slug(heading).lower())
        prev = line if not in_fence[i] else ""

    no_code = _CODE_SPAN.sub(_blank, masked)
    doc.anchors.update(a.lower() for a in _HTML_ID.findall(no_code))

    def add(m: re.Match[str], group: int) -> None:
        start = m.start(group)
        line = no_code.count("\n", 0, start) + 1
        col = start - (no_code.rfind("\n", 0, start) + 1) + 1
        target = m.group(group)
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        doc.links.append(Link(target, line, col))

    for m in _INLINE_LINK.finditer(no_code):
        add(m, 1)
    for m in _REF_DEF.finditer(no_code):
        add(m, 2)
    for m in _HTML_LINK.finditer(no_code):
        add(m, 1)
    doc.links.sort(key=lambda link: (link.line, link.column))
    return doc


def _looks_like_list_or_rule(prev: str) -> bool:
    # "foo\n---" is a heading, but "- item\n---" or a table row is not.
    s = prev.strip()
    return s.startswith(("-", "*", "+", "|", ">")) or bool(re.match(r"\d+[.)]\s", s))

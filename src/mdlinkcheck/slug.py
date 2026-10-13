"""Turn Markdown headings into the anchors GitHub generates for them.

GitHub renders the heading to plain text and then applies the same rules as
`github-slugger <https://github.com/Flet/github-slugger>`_: lowercase, drop
everything except letters, digits, ``_``, ``-`` and spaces, then turn each
space into ``-``.  Repeated headings get ``-1``, ``-2``, ... suffixes.
"""

from __future__ import annotations

import html
import re

_CODE_SPAN = re.compile(r"(`+)(.+?)\1", re.S)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_INLINE_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REF_LINK = re.compile(r"\[([^\]]*)\]\[[^\]]*\]")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
# Emphasis with underscores only counts at word boundaries (CommonMark
# "left/right-flanking" rules); MAX_FOO_BAR keeps its underscores.
_UNDERSCORE_EMPH = re.compile(r"(?<![\w\\])(_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)")
_STAR_EMPH = re.compile(r"(\*{1,3})(?=\S)(.+?)(?<=\S)\1")
_CUSTOM_ID = re.compile(r"\s*\{#([^}\s]+)[^}]*\}\s*$")
_DROP = re.compile(r"[^\w\- ]", re.UNICODE)


def custom_id(heading: str) -> str | None:
    """Return the ``{#id}`` attribute of a heading, if it has one."""
    m = _CUSTOM_ID.search(heading)
    return m.group(1) if m else None


def heading_text(heading: str) -> str:
    """Approximate the plain text GitHub renders for a heading's Markdown."""
    heading = _CUSTOM_ID.sub("", heading)
    parts: list[str] = []
    pos = 0
    for m in _CODE_SPAN.finditer(heading):
        parts.append(_inline_to_text(heading[pos : m.start()]))
        parts.append(m.group(2).strip() if m.group(2).strip() else m.group(2))
        pos = m.end()
    parts.append(_inline_to_text(heading[pos:]))
    return "".join(parts).strip()


def _inline_to_text(s: str) -> str:
    s = _IMAGE.sub(r"\1", s)
    s = _INLINE_LINK.sub(r"\1", s)
    s = _REF_LINK.sub(r"\1", s)
    s = _HTML_TAG.sub("", s)
    s = _STAR_EMPH.sub(r"\2", s)
    s = _UNDERSCORE_EMPH.sub(r"\2", s)
    s = _ESCAPE.sub(r"\1", s)
    return html.unescape(s)


def slugify(text: str) -> str:
    """Slug a heading's plain text the way github-slugger does."""
    return _DROP.sub("", text.lower()).replace(" ", "-")


class Slugger:
    """Generates unique anchors for a sequence of headings in one document."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def slug(self, heading: str) -> str:
        base = slugify(heading_text(heading))
        result = base
        while result in self._seen:
            self._seen[base] += 1
            result = f"{base}-{self._seen[base]}"
        self._seen.setdefault(base, 0)
        self._seen.setdefault(result, 0)
        return result

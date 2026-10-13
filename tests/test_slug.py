import pytest

from mdlinkcheck.slug import Slugger, heading_text, slugify


@pytest.mark.parametrize(
    "heading, anchor",
    [
        ("Hello World", "hello-world"),
        ("Hello  World", "hello--world"),  # spaces are not collapsed
        ("`MAX_*` constants", "max_-constants"),
        ("`GET /payloads/{payloadId}`", "get-payloadspayloadid"),
        ("Channel Establishment v1", "channel-establishment-v1"),
        ("What's new?", "whats-new"),
        ("C++ & Rust", "c--rust"),
        ("**Bold** and _emph_", "bold-and-emph"),
        ("snake_case_name", "snake_case_name"),
        ("[Linked](https://example.com) heading", "linked-heading"),
        ("![logo](logo.png) Title", "logo-title"),
        ("Heading <sup>1</sup>", "heading-1"),
        ("Übersicht", "übersicht"),
        ("Café & crème", "café--crème"),
        ("v1.2.3 release", "v123-release"),
        ("Fish &amp; chips", "fish--chips"),
        ("Escaped \\_underscore\\_", "escaped-_underscore_"),
        ("emoji 🚀 rocket", "emoji--rocket"),
        ("Custom {#my-id}", "custom"),
    ],
)
def test_github_anchor(heading, anchor):
    assert Slugger().slug(heading) == anchor


def test_duplicates_get_numbered():
    s = Slugger()
    assert [s.slug("Usage"), s.slug("Usage"), s.slug("Usage")] == ["usage", "usage-1", "usage-2"]


def test_duplicate_suffix_does_not_collide_with_real_heading():
    # Same algorithm as github-slugger: "Foo 1" claims foo-1, so the second "Foo" becomes foo-2.
    s = Slugger()
    assert [s.slug("Foo"), s.slug("Foo 1"), s.slug("Foo")] == ["foo", "foo-1", "foo-2"]


def test_heading_text_keeps_code_literal():
    assert heading_text("Use `*args` here") == "Use *args here"


def test_slugify_plain():
    assert slugify("A-B_C d") == "a-b_c-d"

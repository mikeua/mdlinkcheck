from textwrap import dedent

from mdlinkcheck.markdown import parse


def targets(md):
    return [link.target for link in parse(dedent(md)).links]


def test_link_kinds():
    md = """\
    See [a](a.md), ![img](img/x.png "title"), [ref][r] and <a href="b.md#top">b</a>.
    [angle](<with space.md>)

    [r]: ref.md#section
    """
    assert targets(md) == ["a.md", "img/x.png", "b.md#top", "with space.md", "ref.md#section"]


def test_parenthesised_target():
    assert targets("[w](https://en.wikipedia.org/wiki/Foo_(bar))") == ["https://en.wikipedia.org/wiki/Foo_(bar)"]


def test_links_in_code_are_ignored():
    md = """\
    `[not](a.md)` and [yes](b.md)

    ```md
    [not](c.md)
    ```

    ~~~~
    ```
    [not](d.md)
    ~~~~
    <!-- [not](e.md) -->
    """
    assert targets(md) == ["b.md"]


def test_line_and_column():
    links = parse("first line\n  see [x](target.md)\n").links
    assert (links[0].line, links[0].column) == (2, 11)


def test_anchors():
    md = """\
    # Title

    Setext heading
    --------------

    ## Title

    ### Custom {#explicit}

    <a name="legacy"></a>
    <div id="Block-Id"></div>

    ```
    # not a heading
    ```
    """
    anchors = parse(dedent(md)).anchors
    assert {"title", "setext-heading", "title-1", "custom", "explicit", "legacy", "block-id"} <= anchors
    assert "not-a-heading" not in anchors


def test_front_matter_is_not_a_heading():
    md = "---\ntitle: Hello\n---\n\n# Real\n"
    assert parse(md).anchors == {"real"}


def test_list_item_followed_by_rule_is_not_a_heading():
    md = "- item\n---\n"
    assert parse(md).anchors == set()

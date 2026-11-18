"""The EPUB pipeline, end to end, against four publisher conventions.

Each fixture below is named for the convention it stands for. They are mutually
incompatible in ways that matter: one publisher hides its MathML in HTML
comments and ships a PNG of each equation beside it; another ships no `<pre>`
at all and indents code with non-breaking spaces; InDesign exports have no heading tags of
any kind. A converter that handles one and not the others reads as working
right up until the second book.
"""

from __future__ import annotations

import glob
import os
import re

from conftest import read

from h2m.epub import main, spelled_number

PAD = "<p>%s</p>" % (
    (
        "The rule is stated plainly and then qualified, because a rule "
        "without its qualification is how a benchmark flatters itself. "
    )
    * 3
)


def convert(path, tmp_path, *args):
    out = str(tmp_path / "out")
    main([path, "-o", out, "--slug", "b", *args])
    files = sorted(glob.glob(os.path.join(out, "b", "*.md")))
    return files, "\n".join(read(f) for f in files)


# --- MathML commented out beside a picture of itself ---------------------

MATHML = (
    '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">'
    "<mfrac><mi>a</mi><mi>b</mi></mfrac></math>"
)


def test_mathml_hidden_in_an_html_comment_is_recovered_as_latex(epub, tmp_path) -> None:
    # Read naively this book is 549 pictures and no mathematics. The comment is
    # unwrapped before parsing, which is where all 1,698 equations come from.
    body = '<h1>Chapter 1 Basics</h1>%s<p><img src="e1.png" alt="equation"/><!--%s--></p>' % (
        PAD,
        MATHML,
    )
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert r"\frac{a}{b}" in md


def test_the_redundant_picture_of_a_recovered_equation_is_dropped(epub, tmp_path) -> None:
    # Keeping both leaves every equation stated twice, once unreadably.
    body = '<h1>Chapter 1 Basics</h1>%s<p><img src="e1.png" alt="equation"/><!--%s--></p>' % (
        PAD,
        MATHML,
    )
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert "e1.png" not in md


def test_a_display_equation_set_directly_in_the_body_is_kept(epub, tmp_path) -> None:
    # Found by the bundled example: a `<math display="block">` that is a direct
    # child of <body>, not wrapped in a <p> or <div>, was counted in the census
    # (`equations: 1`) and then dropped from the text. Only `h2m verify` showed
    # it, as a 16-character gap.
    body = "<h1>Chapter 1 Basics</h1>%s%s<p>After the equation.</p>" % (PAD, MATHML)
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert "$$\n\\frac{a}{b}\n$$" in md
    assert md.index("frac") < md.index("After the equation.")


def test_a_comment_that_is_not_mathml_never_reaches_the_markdown(epub, tmp_path) -> None:
    # BeautifulSoup's Comment is a NavigableString subclass, so an extractor
    # that tests for NavigableString emits comments as body text. It did.
    body = "<h1>Chapter 1 Basics</h1>%s<!-- InDesign generated: do not edit -->" % PAD
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert "do not edit" not in md


def test_a_page_break_marker_becomes_a_greppable_comment(epub, tmp_path) -> None:
    # Invisible when rendered, but it lets a retrieval hit cite a printed page.
    # Between two blocks, not inside one — the shape that used to vanish.
    body = '<h1>Chapter 1 Basics</h1><span epub:type="pagebreak" title="147"></span>%s' % PAD
    files, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert "<!-- page 147 -->" in md
    assert 'pages: "147-147"' in read(files[0])


PUBLISHER_H1 = (
    '<h1><span epub:type="pagebreak" id="Page_21" role="doc-pagebreak" title="21"/>'
    '<a id="c02"/><span class="chapterNumber">CHAPTER 2</span><br/>'
    '<span class="chapterTitle">Core Ideas and Definitions</span></h1>'
)


def test_a_publisher_heading_shape_survives_intact(epub, tmp_path) -> None:
    """Markup in the shape a publisher EPUB ships, and three traps in one tag.

    The heading carries a page marker inside it, an empty anchor, and its number
    and title in two spans separated by a `<br/>`. What has to come out is one
    heading, one page marker, a numeric `chapter:` field and a title with the
    number stripped off it.
    """
    files, md = convert(epub([("c02.xhtml", "Chapter 2", PUBLISHER_H1 + PAD)]), tmp_path)
    text = read(files[0])
    assert re.search(r"^# CHAPTER 2 — Core Ideas and Definitions$", md, re.M)
    assert "chapter: 2" in text
    assert 'title: "Core Ideas and Definitions"' in text
    assert "<!-- page 21 -->" in md


def test_a_page_marker_inside_a_heading_never_reaches_the_filename(epub, tmp_path) -> None:
    # The marker is parked behind a sentinel during cleanup. The first patch
    # used the wrong delimiter and the sentinel came out inside the h1 — and
    # therefore inside the slug, and therefore inside the filename.
    files, _ = convert(epub([("c02.xhtml", "Chapter 2", PUBLISHER_H1 + PAD)]), tmp_path)
    name = os.path.basename(files[0])
    assert "PAGE" not in name and "21" not in name
    assert name == "00_chapter-2-core-ideas-and-definitions.md"


def test_two_spans_separated_by_a_break_are_joined_and_not_run_together(epub, tmp_path) -> None:
    """The other half of a fix that went too far once.

    Joining a heading's parts with spaces turned InDesign's per-letter spans
    into "Ex ecution" and "Tacti c four". Concatenating instead fixed those and
    means a publisher who emits two spans with no whitespace between them gets
    them welded — the `<br/>` here is what keeps the number and title apart.
    Both behaviours are deliberate; this records which side of the trade-off the
    converter is on.
    """
    welded = (
        '<h1><span class="chapterNumber">CHAPTER 2</span>'
        '<span class="chapterTitle">Basic Concepts</span></h1>'
    )
    _, md = convert(epub([("c02.xhtml", "Chapter 2", welded + PAD)]), tmp_path)
    assert "CHAPTER 2Basic Concepts" in md


def test_a_price_in_the_prose_is_not_read_as_mathematics(epub, tmp_path) -> None:
    # "$0.40 to $4.00" opens and closes an inline maths span, and everything
    # between becomes LaTeX. Escaping is the only thing standing in the way.
    body = "<h1>Chapter 1 Basics</h1>%s<p>Hosting runs $0.40 to $4.00 a month.</p>" % PAD
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert r"\$0.40" in md and r"\$4.00" in md


# --- code in divs, LaTeX in an alt attribute ------------------------------


def test_code_shipped_as_nested_divs_becomes_a_fenced_block(epub, tmp_path) -> None:
    code = (
        '<div class="ProgramCode">'
        '<div class="FixedLine">def size(vol):</div>'
        '<div class="FixedLine">    return risk / vol</div>'
        "</div>"
    )
    body = "<h1>Chapter 1 Basics</h1>%s%s" % (PAD, code)
    files, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path, "--code-lang", "python")
    assert "```python" in md
    assert "    return risk / vol" in md
    assert "code_blocks: 1" in read(files[0])


def test_indentation_written_as_non_breaking_spaces_survives(epub, tmp_path) -> None:
    # Some publishers indent with \\xa0 and hair spaces, which a normalising text
    # extractor collapses. Code needs the whitespace-preserving one.
    code = (
        '<div class="ProgramCode"><div class="FixedLine">if x:</div>'
        '<div class="FixedLine">        deep()</div></div>'
    )
    _, md = convert(
        epub([("c01.xhtml", "Chapter 1", "<h1>Chapter 1 Basics</h1>%s%s" % (PAD, code))]), tmp_path
    )
    assert "\n        deep()" in md


def test_latex_carried_in_an_image_alt_attribute_is_used(epub, tmp_path) -> None:
    body = '<h1>Chapter 1 Basics</h1>%s<p><img src="e.png" alt="$$\\sigma^2$$"/></p>' % PAD
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert r"\sigma^2" in md
    assert "e.png" not in md


def test_a_pre_block_keeps_its_indentation_through_the_whitespace_pass(epub, tmp_path) -> None:
    """The trap that flattened 237 C++ listings.

    A post-processing pass collapses runs of spaces so ragged prose reflows.
    Applied to the whole document it reaches inside code fences and every
    listing loses its nesting — silently, because the code is still there and
    still fenced. Fences are parked behind placeholders during cleanup.
    """
    body = (
        "<h1>Chapter 1 Basics</h1>%s"
        "<pre>for (i=0; i&lt;n; i++) {\n        total += x[i];\n}</pre>" % PAD
    )
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert "\n        total += x[i];" in md


# --- InDesign: no heading tags at all -------------------------------------


def test_a_styled_paragraph_is_read_as_the_heading_it_is(epub, tmp_path) -> None:
    # p.Strategy-Title-NEW is the chapter title; p.heading-N is a section under
    # it, which is why heading-1 maps to `##` and not to `#`. Getting that
    # backwards gives a book with thirty top-level headings and no chapters.
    body = (
        '<p class="Strategy-Title-NEW">Strategy nine: Slow and steady rollout</p>%s'
        '<p class="heading-1">Sizing</p>%s'
        '<p class="heading-3">Buffering</p>%s' % (PAD, PAD, PAD)
    )
    _, md = convert(epub([("c01.xhtml", "c01", body)]), tmp_path)
    assert re.search(r"^# Strategy nine: Slow and steady rollout$", md, re.M)
    assert re.search(r"^## Sizing$", md, re.M)
    assert re.search(r"^### Buffering$", md, re.M)


def test_a_strategy_numbered_in_words_gets_a_numeric_chapter_field(epub, tmp_path) -> None:
    body = '<p class="Strategy-Title-NEW">Strategy nine: Slow and steady rollout</p>%s' % PAD
    files, _ = convert(epub([("c01.xhtml", "c01", body)]), tmp_path)
    assert "chapter: 9" in read(files[0])


def test_a_title_that_is_really_a_filename_is_replaced_from_the_navigation(epub, tmp_path) -> None:
    # InDesign writes <title>c01</title>. Using it names every chapter after a
    # file. The NCX navLabel is the only place the real title exists.
    body = '<p class="Strategy-Title-NEW">Slow and steady rollout</p>%s' % PAD
    path = epub(
        [("c01.xhtml", "9780000000002_c01", body)],
        labels={"c01.xhtml": "Strategy nine: Slow and steady rollout"},
    )
    files, _ = convert(path, tmp_path)
    assert "slow-and-steady-rollout" in os.path.basename(files[0])


def test_spelled_out_numbers_are_understood_up_to_the_fifties() -> None:
    assert spelled_number("nine") == 9
    assert spelled_number("twenty-four") == 24
    assert spelled_number("banana") is None


# --- structure common to every source -------------------------------------


def test_a_table_becomes_a_pipe_table_with_its_header_row(epub, tmp_path) -> None:
    tbl = (
        "<table><tr><th>Ratio</th><th>Value</th></tr><tr><td>Latency</td><td>0.72</td></tr></table>"
    )
    files, md = convert(
        epub([("c01.xhtml", "Chapter 1", "<h1>Chapter 1 Basics</h1>%s%s" % (PAD, tbl))]), tmp_path
    )
    assert "| Ratio | Value |" in md
    assert "| --- | --- |" in md
    assert "tables: 1" in read(files[0])


def test_the_table_of_contents_is_dropped_as_navigation(epub, tmp_path) -> None:
    # It is a list of links to content, not content. Kept, it is the longest
    # "chapter" in the book and every retrieval hit lands in it.
    # Named bm01, not toc: a file literally called toc.xhtml is dropped by the
    # filename rule and the heading rule is never reached. The first version of
    # this test proved only that "toc" is spelled "toc".
    docs = [
        ("bm01.xhtml", "Contents", "<h1>Table of Contents</h1>%s" % PAD),
        ("c01.xhtml", "Chapter 1", "<h1>Chapter 1 Basics</h1>%s" % PAD),
    ]
    files, _ = convert(epub(docs), tmp_path)
    assert len(files) == 1
    assert "basics" in os.path.basename(files[0])


def test_the_front_matter_names_the_book_the_author_and_the_source_file(epub, tmp_path) -> None:
    path = epub(
        [("c01.xhtml", "Chapter 1", "<h1>Chapter 1 Basics</h1>%s" % PAD)],
        title="Field Notes",
        author="A. Writer",
        identifier="urn:isbn:9780000000002",
    )
    files, _ = convert(path, tmp_path)
    text = read(files[0])
    assert 'book: "Field Notes"' in text
    assert 'author: "A. Writer"' in text
    assert 'identifier: "urn:isbn:9780000000002"' in text
    assert 'source_file: "c01.xhtml"' in text
    assert "chapter: 1" in text


def test_the_chapter_number_is_split_off_the_title(epub, tmp_path) -> None:
    files, _ = convert(
        epub([("c07.xhtml", "Chapter 7", "<h1>CHAPTER 7 Position Sizing</h1>%s" % PAD)]), tmp_path
    )
    text = read(files[0])
    assert "chapter: 7" in text
    assert 'title: "Position Sizing"' in text


def test_files_are_named_so_that_plain_sorting_keeps_the_reading_order(epub, tmp_path) -> None:
    # A two-digit prefix puts file 121 before file 14. The padding is chosen
    # from the spine length rather than fixed.
    # It takes more than a hundred documents to see this: with fourteen, two
    # digits are enough either way and a hard-coded %02d looks correct.
    docs = [
        ("c%03d.xhtml" % n, "Chapter %d" % n, "<h1>Chapter %d Topic</h1>%s" % (n, PAD))
        for n in range(1, 106)
    ]
    files, _ = convert(epub(docs), tmp_path)
    names = [os.path.basename(f) for f in files]
    order = [int(re.match(r"(\d+)_", n).group(1)) for n in names]
    assert order == sorted(order)
    assert names[0].startswith("000_")


def test_an_image_with_a_real_description_keeps_the_description(epub, tmp_path) -> None:
    # Real alt text is the machine-readable content of the figure. It lands
    # in the Markdown whether or not the images are extracted.
    body = (
        '<h1>Chapter 1 Basics</h1>%s<figure><img src="f1.png" '
        'alt="A bell-shaped curve centred on the mean"/>'
        "<figcaption>Figure 1.1</figcaption></figure>" % PAD
    )
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    assert "A bell-shaped curve centred on the mean" in md
    assert "images/f1.png" in md


def test_no_markdown_leaks_a_sentinel_or_raw_markup(epub, tmp_path) -> None:
    # The standing check. Every intermediate form the converter uses is a
    # placeholder that must be gone by the time the file is written.
    body = (
        '<h1>Chapter 1 Basics</h1><span epub:type="pagebreak" title="12"/>%s'
        '<p><img src="e.png" alt="equation"/><!--%s--></p>'
        "<table><tr><th>A</th></tr><tr><td>1</td></tr></table>" % (PAD, MATHML)
    )
    _, md = convert(epub([("c01.xhtml", "Chapter 1", body)]), tmp_path)
    for leak in ("PAGE:", "BMATH:", "\x01", "\x02", "<math", "<span", "<div", "<p>"):
        assert leak not in md, leak


def test_a_table_wrapped_in_a_figure_is_still_a_table(epub, tmp_path) -> None:
    """The loss that only the completeness check found.

    Some publishers wrap data tables in `<figure>` with the caption above them, the
    same element it uses for a picture. The figure branch renders a figure as an
    image reference plus its caption and returns, so everything inside was
    discarded — caption kept, table gone. A five-column table of figures in a
    real book was simply not in the output, and nothing about the file looked
    wrong: no fence unbalanced, no link dangling, the caption right there.

    Measured across that book: 16 chapters affected, the worst losing 16% of
    itself.
    """
    fig = (
        "<figure><figcaption><b>TABLE 24.3</b> Throughput by build.</figcaption>"
        "<table><thead><tr><td>Date</td><td>A</td></tr></thead>"
        "<tbody><tr><td>8/23/2000</td><td>100.00</td></tr>"
        "<tr><td>8/24/2000</td><td>99.24</td></tr></tbody></table></figure>"
    )
    files, md = convert(
        epub([("c24.xhtml", "Chapter 24", "<h1>Chapter 24 Risk Control</h1>%s%s" % (PAD, fig))]),
        tmp_path,
    )
    assert "| Date | A |" in md
    assert "| 8/23/2000 | 100.00 |" in md
    assert "| 8/24/2000 | 99.24 |" in md
    assert "TABLE 24.3" in md  # the caption survives too
    assert "tables: 1" in read(files[0])


def test_a_figure_that_really_is_a_picture_is_unchanged(epub, tmp_path) -> None:
    fig = (
        '<figure><img src="f1.png" alt="A bell-shaped curve"/>'
        "<figcaption>Figure 1.1</figcaption></figure>"
    )
    _, md = convert(
        epub([("c01.xhtml", "Chapter 1", "<h1>Chapter 1 Basics</h1>%s%s" % (PAD, fig))]), tmp_path
    )
    assert "![A bell-shaped curve](images/f1.png)" in md

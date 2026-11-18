"""The PDF pipeline, end to end, on PDFs this suite builds itself.

The bug these exist for deleted 6,000 words from a real book and left a word
count that looked entirely plausible. Nothing raised, no fence was unbalanced,
no link dangled — the text was simply not there. Only a comparison against the
source found it, which is why the first test below is a completeness test and
not a formatting one.
"""

from __future__ import annotations

import glob
import os
import re

import pymupdf
from conftest import add_separation_image, read

from h2m.layout import Profile, page_lines
from h2m.pdf import Doc, main

WORDS = (
    "cache queue compiler throughput heap scheduler debugger profiler iterator "
    "replication mutex trees graphs kernel firmware sockets buffers streams "
    "allocator semaphore parsers linkers loaders compression checksums"
).split()


def prose(n, sentences=4):
    """Distinct prose for page `n`.

    Every page must say something different. A fixture that repeats the same
    paragraph on every page is, by any honest definition, a running head — and
    the furniture detector deletes it, correctly. Getting this wrong first is
    what made the fixtures worth explaining here.
    """
    out = []
    for s in range(sentences):
        k = (n * 7 + s * 3) % len(WORDS)
        w = [WORDS[(k + j) % len(WORDS)] for j in range(4)]
        out.append(
            "Measuring %s against %s tells you more about %s than about %s, "
            "which is why the rule is written the way it is." % tuple(w)
        )
    return " ".join(out)


def paragraph(text, size=11.0, x=72.0, width=64):
    """Wrap `text` into (line, kwargs) pairs the PDF builder can draw."""
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            out.append((cur, {"size": size, "x": x}))
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append((cur, {"size": size, "x": x}))
    return out


def book(n, size=11.0, x=72.0):
    """`n` pages of ordinary body prose, no two alike."""
    return [paragraph(prose(i), size=size, x=x) for i in range(n)]


def convert(pdf_path, tmp_path, *args):
    out = str(tmp_path / "out")
    main([pdf_path, "-o", out, "--slug", "b", *args])
    files = sorted(glob.glob(os.path.join(out, "b", "*.md")))
    return files, "\n".join(read(f) for f in files)


# --- the completeness test ------------------------------------------------


def test_body_text_set_high_on_the_page_is_not_eaten_by_the_running_head(pdf, tmp_path) -> None:
    """The 6,000-word bug, reproduced.

    Furniture used to be detected as a recurring *y-band* and everything above
    the band was dropped. A book whose body starts at y=44 — dense technical
    typesetting does — then loses its first line on every page. The head here
    sits at y=30 and the body starts at y=44: 14 points apart, which is less
    than one line of leading.
    """
    path = pdf(
        book(12),
        head="CHAPTER ONE  ·  A SYSTEMATIC APPROACH",
        top=44,
        toc=[[1, "Chapter One A Systematic Approach", 1]],
    )
    _, md = convert(path, tmp_path)
    missing = [w for w in sorted({w for i in range(12) for w in prose(i).split()}) if w not in md]
    assert missing == []


def test_the_running_head_itself_does_not_survive_into_the_markdown(pdf, tmp_path) -> None:
    path = pdf(
        book(12),
        head="CHAPTER ONE  ·  A SYSTEMATIC APPROACH",
        top=44,
        toc=[[1, "Chapter One A Systematic Approach", 1]],
    )
    _, md = convert(path, tmp_path)
    # It is allowed once, as the chapter's own h1. Twelve times means the band
    # detector stopped working.
    assert md.count("A SYSTEMATIC APPROACH") <= 1


def test_a_string_that_appears_at_the_head_height_only_once_is_kept(pdf, tmp_path) -> None:
    # The counter-test to the one above: a line that happens to sit where the
    # running head sits, but says something different on every page, is body
    # text. Dropping it is exactly the bug, one page at a time.
    pages = [
        [("Instrument %s carries its own estimate." % WORDS[n], {})] + paragraph(prose(n))
        for n in range(12)
    ]
    path = pdf(pages, head=None, top=44, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    assert md.count("carries its own estimate") == 12


# --- printed page numbers -------------------------------------------------


def test_a_folio_in_the_outer_margin_becomes_a_page_marker(pdf, tmp_path) -> None:
    # Some books set the page number beside the text block, not under it, so a
    # footer-band rule finds nothing. The rule is "a bare number outside the
    # measured text column", whatever its height.
    path = pdf(book(10), toc=[[1, "Chapter One", 1]], folio_x=560, folio_y=400, folio_from=21)
    _, md = convert(path, tmp_path)
    assert "<!-- page 21 -->" in md
    assert "<!-- page 30 -->" in md


def test_a_number_inside_the_text_column_is_not_read_as_a_page_number(pdf, tmp_path) -> None:
    # Table numbers and equation numbers are bare numbers too. Only position
    # separates them from a folio.
    # Two things had to be arranged before this test could fail for the right
    # reason. The stray number must sit *below* the real folio in reading order,
    # because the last folio found on a page wins — above it, the real one
    # overwrites it and the test passes against a broken rule. And it must stay
    # clear of the footer band, because a bare number repeated down there is a
    # folio by definition, whatever the column rule says.
    pages = [paragraph(prose(i)) + [("42", {"x": 200, "dy": 460})] for i in range(10)]
    path = pdf(pages, toc=[[1, "Chapter One", 1]], folio_x=560, folio_y=200, folio_from=21)
    _, md = convert(path, tmp_path)
    assert "<!-- page 42 -->" not in md


def test_the_printed_page_range_is_recorded_in_the_front_matter(pdf, tmp_path) -> None:
    path = pdf(book(10), toc=[[1, "Chapter One", 1]], folio_x=560, folio_y=400, folio_from=21)
    files, _ = convert(path, tmp_path)
    assert 'printed_pages: "21-30"' in read(files[0])


# --- chapters -------------------------------------------------------------


def test_the_outline_decides_where_chapters_begin(pdf, tmp_path) -> None:
    path = pdf(book(24), toc=[[1, "Chapter One Parsing", 1], [1, "Chapter Two Caching", 13]])
    files, _ = convert(path, tmp_path)
    assert len(files) == 2
    assert "parsing" in files[0] and "caching" in files[1]


def test_an_outline_that_would_split_the_book_into_fragments_is_not_used(pdf, tmp_path) -> None:
    """One real outline has 85 entries over 3 levels; taking them all gave
    53 files averaging 400 words. The rule is that a level is only used when the
    units it produces still average 8 pages or more."""
    toc = [[1, "Chapter One Parsing", 1]] + [[2, "Section %d" % n, n] for n in range(2, 13)]
    toc += [[1, "Chapter Two Caching", 13]] + [[2, "Section %d" % n, n] for n in range(14, 24)]
    path = pdf(book(24), toc=toc)
    files, _ = convert(path, tmp_path)
    assert len(files) == 2


def test_the_chapter_number_is_parsed_out_of_a_spelled_out_title(pdf, tmp_path) -> None:
    path = pdf(book(12), toc=[[1, "Chapter Four Memory Allocation", 1]])
    files, _ = convert(path, tmp_path)
    assert "chapter: 4" in read(files[0])


def test_the_chapter_title_is_not_printed_twice(pdf, tmp_path) -> None:
    # The page carries the title as a heading and the converter knows it from
    # the outline. Emitting both puts the same words on two consecutive lines.
    pages = (
        [[("Chapter One Parsing", {"size": 24.0})] + paragraph(prose(0))]
        + book(11)[1:]
        + book(12)[11:]
    )
    path = pdf(pages, toc=[[1, "Chapter One Parsing", 1]])
    _, md = convert(path, tmp_path)
    assert md.count("# Chapter One Parsing") == 1


# --- content shapes -------------------------------------------------------


def test_a_monospaced_run_becomes_a_fenced_block_with_its_indentation(pdf, tmp_path) -> None:
    code = [
        ("def size(vol):", {"font": "cour", "size": 10.0, "x": 72}),
        ("return risk / vol", {"font": "cour", "size": 10.0, "x": 96}),
        ("# one level in", {"font": "cour", "size": 10.0, "x": 96}),
    ]
    pages = [paragraph(prose(0)) + code] + book(12)[1:]
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path, "--code-lang", "python")
    assert "```python" in md
    block = md.split("```python")[1].split("```")[0]
    assert "def size(vol):" in block
    # Indentation is rebuilt from the x-offset, not read from the PDF.
    assert re.search(r"\n {2,}return risk / vol", block)


def test_two_recurring_columns_become_a_pipe_table(pdf, tmp_path) -> None:
    rows = []
    for a, b in [("Latency", "0.72"), ("Jitter", "1.04"), ("Uptime", "0.31"), ("Errors", "5.20")]:
        rows.append((a, {"size": 9.0, "x": 72, "dy": 0, "leading": 0}))
        rows.append((b, {"size": 9.0, "x": 300, "leading": 14}))
    pages = [paragraph(prose(0)) + rows] + book(12)[1:]
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    assert "| Latency | 0.72 |" in md
    assert "| --- | --- |" in md


def test_a_word_broken_across_a_page_line_is_healed(pdf, tmp_path) -> None:
    lines = [
        ("The portfolio is rebalanced when the weights drift, which port-", {}),
        ("folio construction handles by scaling every position at once.", {}),
    ]
    pages = [lines + paragraph(prose(0))] + book(12)[1:]
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    assert "portfolio construction handles" in md
    assert "port-\nfolio" not in md


def test_the_ligature_repair_only_runs_when_it_is_asked_for(pdf, tmp_path) -> None:
    # It is off by default because a book without the defect gains nothing and
    # risks a false join. One real book needed none; another needed 914.
    lines = [("A profi table system beats an unprofi table one every time.", {})]
    pages = [lines + paragraph(prose(0))] + book(12)[1:]
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, plain = convert(path, tmp_path)
    _, fixed = convert(path, tmp_path / "b", "--fix-ligatures")
    assert "profi table" in plain
    assert "profitable system" in fixed


# --- front matter ---------------------------------------------------------


def test_every_file_opens_with_front_matter_naming_its_source(pdf, tmp_path) -> None:
    path = pdf(book(12), toc=[[1, "Chapter One", 1]])
    files, _ = convert(path, tmp_path)
    text = read(files[0])
    assert text.startswith("---\n")
    assert 'source_pdf: "book.pdf"' in text
    assert re.search(r"\nwords: \d+\n", text)


# --- the profile itself ---------------------------------------------------


def test_the_body_size_is_measured_from_the_document_and_not_assumed(pdf, tmp_path) -> None:
    path = pdf(book(12, size=8.5), toc=[[1, "Chapter One", 1]], body_size=8.5)
    d = Doc(path)
    assert d.prof.body_size == 8.5


def test_the_text_column_bounds_are_measured_from_body_lines(pdf, tmp_path) -> None:
    path = pdf(book(12, x=90.0), toc=[[1, "Chapter One", 1]])
    d = Doc(path)
    assert 85 < d.prof.col_x0 < 95


def test_a_page_with_no_furniture_keeps_every_line(pdf, tmp_path) -> None:
    path = pdf(book(12), toc=[[1, "Chapter One", 1]])
    doc = pymupdf.open(path)
    prof = Profile(doc)
    kept, _ = page_lines(doc, 0, prof)
    assert len(kept) == len(paragraph(prose(0)))


def test_a_head_that_differs_only_by_its_page_number_is_still_furniture(pdf, tmp_path) -> None:
    """Digits are normalised out of the furniture key, so "Page 41" and
    "Page 42" count as the same string.

    The cost of that rule is worth stating: a *body* line differing from its
    neighbours only by a number, set in the top or bottom band of every page,
    would be dropped. No book in the development corpus contains one, and the
    rule is what makes numbered running heads detectable at all.
    """
    pages = [
        [("Systematic Design  ·  Page %d" % (n + 1), {"size": 9.0})] + paragraph(prose(n))
        for n in range(12)
    ]
    path = pdf(pages, top=44, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    assert "Page 7" not in md


def test_the_converter_refuses_the_ligature_flag_when_it_has_no_dictionary(
    pdf, tmp_path, monkeypatch, capsys
) -> None:
    """Refusing is the whole point.

    Without a word list `fix_ligatures` returns the text untouched and reports
    zero repairs, which reads exactly like a book that needed none. One real book needs
    1,394 per 100k words. A silent zero there is a corrupted book that nobody
    thinks to question, so the flag is rejected outright instead.
    """
    import h2m.layout as layout

    monkeypatch.setattr(layout, "_LIGWORDS", set())
    path = pdf(book(12), toc=[[1, "Chapter One", 1]])
    code = main([path, "-o", str(tmp_path / "out"), "--slug", "b", "--fix-ligatures"])
    assert code == 2
    assert "wamerican" in capsys.readouterr().err


def test_a_folio_set_inside_the_running_head_is_still_harvested(pdf, tmp_path) -> None:
    """Verso pages that print "122  CHAPTER TITLE" as one line.

    The furniture branch already harvests a folio from a dropped line, but only
    when the whole line is a number. Some books set the page number and the running
    head as a single text run on even pages; in one, two thirds of the book had a
    marker and one third did not — and nothing about the output showed it. The
    line is already known to be furniture by the time this runs, so a leading
    number on it is a folio and not the start of a sentence.
    """
    pages = [
        [("%d  METHODOLOGICAL FOUNDATIONS" % (n + 120), {"size": 9.0})] + paragraph(prose(n))
        for n in range(12)
    ]
    # No folio of its own: the number in the head is the only one there is.
    path = pdf(pages, top=44, toc=[[1, "Chapter One", 1]], folio=False)
    _, md = convert(path, tmp_path)
    assert "<!-- page 120 -->" in md
    assert "<!-- page 131 -->" in md
    assert "METHODOLOGICAL FOUNDATIONS" not in md


def test_a_number_that_opens_an_ordinary_paragraph_is_not_a_folio(pdf, tmp_path) -> None:
    # The counter-test. A body line starting with a year is not a page number;
    # only a line already identified as running furniture can yield one.
    pages = [paragraph("2008 was the year " + prose(n)) for n in range(12)]
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    assert "<!-- page 2008 -->" not in md
    assert "2008 was the year" in md


# --- extracted images -----------------------------------------------------


def test_an_image_png_cannot_represent_is_still_written_to_disk(pdf, tmp_path) -> None:
    """The dangling-link bug, reproduced.

    One real book stores 49 of its charts as `Separation(…, Black)` — one component,
    exactly like DeviceGray — so the guard, which asked whether the pixmap had
    four or more components, let them through to a PNG writer that cannot take
    them. The write raised, the raise was swallowed, and the Markdown kept the
    link it had already written before extraction was even attempted: 49 of 84
    figures pointing at files that never existed, under a run that printed
    "images: 84 extracted".

    The assertion is the standing check the README claims for every book — no
    broken image links — and it is asserted here against the one colorspace
    that defeated it.
    """
    path = pdf(book(12), toc=[[1, "Chapter One", 1]])
    add_separation_image(path)
    files, md = convert(path, tmp_path, "--images")
    links = re.findall(r"!\[[^\]]*\]\((images/[^)]+)\)", md)
    assert links, "the fixture drew an image and the converter linked none"
    outdir = os.path.dirname(files[0])
    assert [ln for ln in links if not os.path.exists(os.path.join(outdir, ln))] == []


# --- pages printed sideways -----------------------------------------------


def landscape_table(rows, x0=120, page_h=792):
    """A table printed sideways, the way a publisher sets one too wide to fit.

    Each entry becomes a line with dir (0, -1): the text runs up the page, and
    successive lines advance across it. In reading order the page is a normal
    table; on the page it is rotated a quarter turn.
    """
    out = []
    for r, cells in enumerate(rows):
        for c, cell in enumerate(cells):
            out.append(
                (cell, {"rotate": 90, "size": 9.0, "x": x0 + r * 14, "y": page_h - 90 - c * 90})
            )
    return out


def test_a_page_printed_sideways_is_content_not_margin_furniture(pdf, tmp_path) -> None:
    """One real book lost thirteen tables to this, caption and all.

    Rotated text is normally margin furniture — some books set their running heads
    that way and they must keep being dropped — so `page_lines` discarded every
    line whose direction was not left-to-right. But a table too wide for the
    page is often turned sideways rather than shrunk, and then the rotated text
    is the whole page. In that book 23 of 367 pages are landscape tables and none
    of them reached the converter at all: the prose still said "Table 8.2
    shows..." and underneath there was nothing.
    """
    rows = [
        ["TABLE 8.6", "", "", ""],
        ["Build", "Tests", "Seconds", "Failures"],
        ["A1", "142", "16,600.00", "9,125.00"],
        ["B2", "118", "14,737.50", "4,543.75"],
        ["C3", "203", "57,175.00", "12,762.50"],
    ]
    pages = book(12)
    pages[5] = landscape_table(rows)
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    for cell in ("TABLE 8.6", "Failures", "57,175.00", "4,543.75"):
        assert cell in md, cell
    # Present is not enough: the coordinates have to be turned into reading
    # order too, or the cells arrive column-major and the table is gibberish
    # that still contains every string an "is it there" check looks for.
    assert re.search(r"^\| A1 \| 142 \| 16,600\.00 \| 9,125\.00 \|$", md, re.M)
    assert md.index("TABLE 8.6") < md.index("Failures") < md.index("57,175.00")


def test_a_running_head_turned_into_the_margin_is_still_dropped(pdf, tmp_path) -> None:
    # The counter-test, and the reason the rule cannot simply keep rotated text.
    # Some books print the running head sideways in the margin of every page; it is
    # furniture there and one line does not make a page landscape.
    pages = [
        paragraph(prose(n))
        + [("SYSTEMS IN PRACTICE", {"rotate": 90, "size": 8.0, "x": 560, "y": 600})]
        for n in range(12)
    ]
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    assert "SYSTEMS IN PRACTICE" not in md
    assert "Measuring" in md


def test_a_chart_with_many_rotated_labels_is_not_a_landscape_page(pdf, tmp_path) -> None:
    """The guard that stops the cure being worse than the disease.

    One real page is a chart: twelve rotated date labels on the x-axis, nine
    more at 45 degrees, one upright line. Twelve rotated lines is more than some
    real landscape pages carry, so a rule counting rotated lines alone would
    call it landscape and throw away the page's actual text. What separates them
    is the *share* of the page that is rotated — 55% there against 97-100% for a
    real landscape table.
    """
    axis = [
        ("12/31/%d" % y, {"rotate": 90, "size": 7.0, "x": 90 + i * 30, "y": 700})
        for i, y in enumerate(range(1999, 2011))
    ]
    pages = book(12)
    pages[5] = paragraph(prose(99)) + axis
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    assert "Measuring" in md  # the body text of that page survives
    assert "12/31/2005" not in md  # the axis labels stay furniture


def test_a_single_rotated_caption_does_not_make_a_page_landscape(pdf, tmp_path) -> None:
    """A page holding nothing but a rotated caption is 100% rotated.

    Some books have pages that are one rotated figure caption beside one upright
    line, and the share test handles those. This is the harder shape: strip the
    folio and the page is *entirely* rotated, so share alone says landscape. A
    page has to be substantially made of rotated lines, not merely rotated by
    accident of having almost none at all — which is the only thing the minimum
    count guards, and it has to be provable on its own.
    """
    pages = book(12)
    pages[5] = [("FIGURE 23.3 Individual build results", {"rotate": 90, "x": 540, "y": 600})]
    path = pdf(pages, toc=[[1, "Chapter One", 1]], folio=False)
    _, md = convert(path, tmp_path)
    assert "FIGURE 23.3" not in md


def test_a_repaired_book_records_what_it_was_repaired_against(pdf, tmp_path) -> None:
    """Front matter has to name the dictionary, or the book is not reproducible.

    The repair depends on which word list the machine has, and unioning them
    makes it worse rather than better. A converted chapter that does not say
    which list repaired it cannot be reproduced or compared, and a regression
    diff cannot tell a machine difference from a code change — one was once
    reported as the other.
    """
    lines = [("A profi table system beats an unprofi table one every time.", {})]
    pages = [lines + paragraph(prose(0))] + book(12)[1:]
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    files, _ = convert(path, tmp_path, "--fix-ligatures")
    text = read(files[0])
    assert re.search(r'^ligature_dictionary: "[\w-]+"$', text, re.M)
    assert re.search(r"^ligatures_repaired: \d+$", text, re.M)


def test_a_book_converted_without_the_flag_claims_no_dictionary(pdf, tmp_path) -> None:
    # No repair happened, so there is nothing to record and nothing to compare
    # against. Emitting the field anyway would imply a repair that never ran.
    path = pdf(book(12), toc=[[1, "Chapter One", 1]])
    files, _ = convert(path, tmp_path)
    text = read(files[0])
    assert "ligature_dictionary" not in text
    assert "ligatures_repaired" not in text


def test_a_folio_carrying_an_unmapped_glyph_is_still_harvested(pdf, tmp_path) -> None:
    """Some books print the verso folio as "2\\x08" — a digit and a stray control.

    The typesetter emits an unmapped glyph at the end of the folio line,
    and PyMuPDF hands it back as U+0008. `str.strip()` removes whitespace, and
    a backspace is not whitespace, so `"2\\x08"` failed the bare-number test
    while the recto's clean `"3"` passed it. The result was an exactly
    alternating book: every right-hand page citable, every left-hand page not,
    which is invisible in the output unless you count markers against pages.
    """
    pages = [
        [
            ("%d\x08" % (n + 40), {"size": 9.0}),
            ("QUANTITATIVE METHODS", {"size": 7.5, "x": 300, "dy": -14}),
        ]
        + paragraph(prose(n))
        for n in range(12)
    ]
    path = pdf(pages, top=44, toc=[[1, "Chapter One", 1]], folio=False)
    _, md = convert(path, tmp_path)
    assert "<!-- page 40 -->" in md
    assert "<!-- page 51 -->" in md


def test_an_unmapped_glyph_does_not_invent_a_page_marker(pdf, tmp_path) -> None:
    # The counter-test. Scrubbing controls must not turn a body line into a
    # folio: "2008\x08 was the year" is still a sentence, not a page number.
    pages = [paragraph("2008\x08 was the year " + prose(n)) for n in range(12)]
    path = pdf(pages, toc=[[1, "Chapter One", 1]])
    _, md = convert(path, tmp_path)
    assert "<!-- page 2008 -->" not in md


def test_an_unmapped_glyph_becomes_a_space_and_not_nothing(pdf, tmp_path) -> None:
    """Why the scrub substitutes rather than deletes.

    The two shapes can stack: a folio set inside the running head, with the stray
    control sitting between the number and the title. Deleted, the line reads
    "122METHODOLOGICAL" and the harvest rule — which needs whitespace after the
    number — finds nothing. Replaced with a space it reads as it prints.
    """
    pages = [
        [("%d\x08METHODOLOGICAL FOUNDATIONS" % (n + 120), {"size": 9.0})] + paragraph(prose(n))
        for n in range(12)
    ]
    path = pdf(pages, top=44, toc=[[1, "Chapter One", 1]], folio=False)
    _, md = convert(path, tmp_path)
    assert "<!-- page 120 -->" in md
    assert "<!-- page 131 -->" in md


def test_a_landscape_page_keeps_its_folio_through_an_unmapped_glyph(pdf, tmp_path) -> None:
    # The sideways-page path harvests its folio from the one upright line left
    # on the page, and reads it the same way the upright path does. A book that
    # sets landscape tables *and* trails a stray control off its folios would
    # otherwise lose the marker on exactly those pages — the ones carrying the
    # widest tables, and so the ones most worth citing.
    rows = [
        ["TABLE 8.6", "", "", ""],
        ["Build", "Tests", "Seconds", "Failures"],
        ["A1", "142", "16,600.00", "9,125.00"],
        ["B2", "118", "14,737.50", "4,543.75"],
        ["C3", "203", "57,175.00", "12,762.50"],
    ]
    pages = book(12)
    pages[5] = landscape_table(rows)
    path = pdf(pages, toc=[[1, "Chapter One", 1]], folio_from=80, folio_suffix="\x08")
    _, md = convert(path, tmp_path)
    assert "57,175.00" in md, "the landscape table itself must still arrive"
    assert "<!-- page 85 -->" in md, "the landscape page's own folio"
    assert "<!-- page 80 -->" in md, "and the upright pages either side"


def opener(n, folio):
    """A chapter opening page: no running head, folio dropped to the foot.

    A shape many typeset books use. Because the head is suppressed the
    folio cannot ride in it, so it is set at the bottom of the page — inside
    the text column, which is what puts it out of reach of the outer-margin
    rule as well.
    """
    return (
        [("CHAPTER %d" % n, {"size": 20.0})]
        + paragraph(prose(n, sentences=1))
        + [(str(folio), {"x": 300, "y": 740, "size": 9.0})]
    )


def test_a_folio_dropped_to_the_foot_of_a_chapter_opening_is_harvested(pdf, tmp_path) -> None:
    """Without this, chapter openers lose their page numbers.

    A running head recurs often enough to be measured as furniture, and a folio
    riding in it comes along. A chapter opener suppresses the head and prints
    the folio at the foot instead — a position that occurs on 6-12% of the
    pages, under the share it would take to read as furniture, and inside the
    text column, so the outer-margin rule cannot see it either. In the development
    corpus every such page was the *first* page of something, which is the page a
    citation is most likely to want.
    """
    pages, toc = [], []
    for n in range(40):
        if n % 8 == 0:
            toc.append([1, "Chapter %d" % (n // 8 + 1), n + 1])
            pages.append(opener(n, n + 20))
        else:
            pages.append(
                [
                    (str(n + 20), {"size": 9.0, "x": 72, "y": 30}),
                    ("THE SYSTEMATIC EDGE", {"size": 8.0, "x": 200, "y": 30}),
                ]
                + paragraph(prose(n))
            )
    path = pdf(pages, toc=toc, folio=False, top=60)
    _, md = convert(path, tmp_path)
    for n in (0, 8, 16, 24, 32):  # the five openers
        assert "<!-- page %d -->" % (n + 20) in md, "opener page %d" % (n + 20)
    assert "<!-- page 21 -->" in md, "an ordinary page must still work"
    assert "THE SYSTEMATIC EDGE" not in md, "the running head is still furniture"
    # Read as a folio *and* left in place is worse than not reading it: the
    # chapter then opens with a stray line saying "20" above its own marker.
    for n in (0, 8, 16, 24, 32):
        assert not re.search(r"^%d$" % (n + 20), md, re.M), "folio %d left in the body" % (n + 20)


def test_a_number_that_increases_but_does_not_track_the_page_is_not_a_folio(pdf, tmp_path) -> None:
    """Part numbers, which is why lockstep and not merely "recurring".

    One real book prints 23 of them, one per page, always at the same height and always
    increasing — everything a folio looks like except the one thing that matters.
    A folio advances by exactly what the page index advances by; a part number
    goes 1, 2, 3 across pages 40 apart. The book has no printed folios at all,
    so accepting these would not fill a gap, it would invent 23 wrong citations.
    """
    pages = []
    for n in range(40):
        if n % 8 == 0:
            pages.append(
                [("PART %d" % (n // 8 + 1), {"size": 20.0})]
                + paragraph(prose(n, sentences=1))
                + [(str(n // 8 + 1), {"x": 300, "y": 740, "size": 9.0})]
            )
        else:
            pages.append(paragraph(prose(n)))
    path = pdf(pages, toc=[[1, "Chapter One", 1]], folio=False)
    _, md = convert(path, tmp_path)
    for bogus in (1, 2, 3, 4, 5):
        assert "<!-- page %d -->" % bogus not in md, "part number %d became a folio" % bogus


def test_two_pages_agreeing_by_chance_do_not_make_a_folio_band(pdf, tmp_path) -> None:
    # One step in lockstep is a coincidence, not evidence. Two consecutive
    # figure numbers on two consecutive pages read exactly like a folio over
    # that distance, and the book is nowhere near page 3 when they appear.
    pages = []
    for n in range(40):
        p = [
            (str(n + 100), {"size": 9.0, "x": 72, "y": 30}),
            ("THE SYSTEMATIC EDGE", {"size": 8.0, "x": 200, "y": 30}),
        ] + paragraph(prose(n))
        if n in (30, 31):
            p = (
                [("CHAPTER %d" % n, {"size": 20.0})]
                + paragraph(prose(n, sentences=1))
                + [(str(n - 27), {"x": 300, "y": 740, "size": 9.0})]
            )
        pages.append(p)
    path = pdf(pages, toc=[[1, "Chapter One", 1]], folio=False, top=60)
    _, md = convert(path, tmp_path)
    assert "<!-- page 3 -->" not in md
    assert "<!-- page 4 -->" not in md
    assert "<!-- page 100 -->" in md, "the ordinary folios must still be read"


def test_a_height_carrying_two_numbers_on_one_page_is_not_a_folio_band(pdf, tmp_path) -> None:
    """One number per page, or it is a table row.

    A folio is printed once. A height that carries two numbers on the same page
    is carrying data, and which of the two is the folio is not answerable — so
    the band is refused rather than guessed at. Dropping this guard alone takes
    one real book from 3 measured folio bands to 11, and the eight extra ones put table
    cells into the page markers.
    """
    pages, band = [], []
    for n in range(100):
        if n % 9 == 0:
            band.append(n)
            pages.append(
                [("CHAPTER %d" % n, {"size": 20.0})]
                + paragraph(prose(n, sentences=1))
                + [(str(n + 20), {"x": 300, "y": 740, "size": 9.0})]
            )
        else:
            pages.append(paragraph(prose(n)))
    # The last page of the band is a two-cell table row, not a page number.
    pages[band[-1]] = (
        [("Results", {"size": 12.0})]
        + paragraph(prose(7, sentences=1))
        + [
            (str(band[-1] + 20), {"x": 120, "y": 740, "size": 9.0}),
            ("4175", {"x": 300, "y": 740, "size": 9.0}),
        ]
    )
    path = pdf(pages, toc=[[1, "Chapter One", 1]], folio=False)
    _, md = convert(path, tmp_path)
    assert "<!-- page 4175 -->" not in md, "a table cell became the page number"
    assert "<!-- page 20 -->" not in md, "the whole band should be refused, not repaired"


def test_a_running_head_folio_beats_a_number_at_the_folio_height(pdf, tmp_path) -> None:
    """A real page: "25" in the running head, "56" in a table cell.

    The cell lands exactly on the foot band, and the head is right. So the band
    is *held* rather than taken, and used only when nothing else on the page
    produced a folio. The stray sits at the end of the band here for the same
    reason it does not destroy the real one: one bad step out of twelve is inside
    what a band has to tolerate anyway, because the roman-to-arabic jump at the
    end of the front matter breaks lockstep once in every real book.
    """
    pages = []
    for n in range(96):
        p = [
            (str(n + 100), {"size": 9.0, "x": 72, "y": 30}),
            ("THE SYSTEMATIC EDGE", {"size": 8.0, "x": 200, "y": 30}),
        ] + paragraph(prose(n))
        if n % 8 == 0:
            p = (
                [("CHAPTER %d" % n, {"size": 20.0})]
                + paragraph(prose(n, sentences=1))
                + [(str(n + 100), {"x": 300, "y": 740, "size": 9.0})]
            )
        elif n == 94:
            p = p + [("4175", {"x": 300, "y": 740, "size": 9.0})]
        pages.append(p)
    path = pdf(pages, toc=[[1, "Chapter One", 1]], folio=False, top=60)
    _, md = convert(path, tmp_path)
    assert "<!-- page 194 -->" in md, "the running head folio must win on that page"
    assert "<!-- page 4175 -->" not in md, "the table cell must not become the folio"
    assert "<!-- page 108 -->" in md, "and the band must still serve the openers"


# --- images that are not pictures -----------------------------------------


def test_an_image_with_no_ink_is_neither_written_nor_referenced(pdf, tmp_path) -> None:
    """One real book ships 123 of these, a third of everything it extracts.

    A publisher lays a tinted panel behind a chart and `get_images` returns the
    panel exactly as it returns the chart. Written to disk, referenced from the
    Markdown, and showing nothing: 161 across the development corpus and 187 references to
    them, every one a picture an ingestion pipeline would try to make sense of.
    """
    from conftest import add_flat_image

    path = pdf(book(12), toc=[[1, "Chapter One", 1]])
    add_flat_image(path, tone=190)
    _, md = convert(path, tmp_path, "--images")
    assert "images/" not in md, "a flat panel must not be referenced"
    assert not glob.glob(str(tmp_path / "out" / "b" / "images" / "*")), (
        "and must not be written either"
    )


def test_an_image_that_does_carry_ink_is_kept(pdf, tmp_path) -> None:
    # The counter-test, and the only thing standing between this rule and a
    # converter that quietly drops figures. Same fixture, dark enough to read.
    from conftest import add_flat_image

    path = pdf(book(12), toc=[[1, "Chapter One", 1]])
    add_flat_image(path, tone=20)
    _, md = convert(path, tmp_path, "--images")
    assert "images/" in md, "a dark panel is a picture and must be kept"
    assert glob.glob(str(tmp_path / "out" / "b" / "images" / "*"))

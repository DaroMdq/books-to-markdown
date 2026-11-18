"""Completeness: does the Markdown still contain what the book said?

This is the check that would have caught the only bug in this project's history
that mattered. One book passed every structural test — balanced fences, no ragged
tables, no dangling links, a plausible word count — while 6,000 words were
missing. Structure proves the shape of the output. Only this proves the content.

The metric is deliberately blind to three things the converter does on purpose:
it reflows lines, it heals hyphenation, and it repairs split ligatures. All
three change where the spaces are and none of them lose a letter, so both sides
are reduced to a stream of letters and digits before anything is compared.
"""

from __future__ import annotations

from conftest import make_epub

from h2m.verify import (
    compare,
    converted_pages,
    converted_units,
    kept_source_text,
    markdown_text,
    normalise,
)

# Word lengths matter here: the comparison walks fixed-size windows, so the
# hollowed-page test below depends on where words fall against the window grid.
WORDS = (
    "cache queue compiler throughput heap scheduler debugger profiler iterator "
    "replication mutex trees graphs kernel firmware sockets buffers streams "
    "allocator semaphore parsers linkers loaders compression checksums "
    "hashtable lexer trie stack node shard deadlock sandboxes hypervisor "
    "bootloaders certificate handshake virtualisation keystores"
).split()


def test_the_normaliser_keeps_letters_and_digits_and_nothing_else() -> None:
    assert normalise("The 20-day E.M.A., re-based!") == "the20dayemarebased"


def test_identical_text_is_fully_recovered() -> None:
    src = "the service scales out when the request queue grows past the limit " * 20
    assert compare(src, src).recovered == 1.0


def test_text_missing_from_the_output_is_reported_as_a_gap() -> None:
    keep = "the service scales out when the request queue grows past the limit. " * 12
    lost = "Buffer size is set from the recent load on the server. " * 4
    r = compare(keep + lost, keep)
    assert r.recovered < 1.0
    assert r.missing_chars > 100
    assert "buffersize" in r.gaps[0].sample


def test_reflowing_lines_is_not_a_loss() -> None:
    # The converter joins wrapped lines into paragraphs. Every letter survives;
    # only the line breaks move.
    src = "the service scales\nout when the\nrequest queue\ngrows past the limit\n" * 10
    out = "the service scales out when the request queue grows past the limit " * 10
    assert compare(src, out).recovered == 1.0


def test_healing_a_hyphenated_line_break_is_not_a_loss() -> None:
    # "port-\nfolio" -> "portfolio". A word-level comparison scores this as two
    # words lost and one gained; a letter stream sees no difference at all.
    src = "the port-\nfolio is rebalanced when the weights drift away from target " * 10
    out = "the portfolio is rebalanced when the weights drift away from target " * 10
    assert compare(src, out).recovered == 1.0


def test_repairing_a_split_ligature_is_not_a_loss() -> None:
    src = "a profi table system beats an unprofi table one every single time " * 10
    out = "a profitable system beats an unprofitable one every single time " * 10
    assert compare(src, out).recovered == 1.0


def test_content_the_converter_adds_does_not_raise_the_score() -> None:
    # The score answers "how much of the source is present", so output the
    # source never had cannot help it. A converter that emitted the whole
    # dictionary must not score 100%.
    src = "the service scales out when the request queue grows past the limit " * 10
    out = "something else entirely, at length, about a different subject " * 40
    assert compare(src, out).recovered < 0.1


def test_reordered_content_still_counts_as_present() -> None:
    # Chapters are written out in outline order, which is not always spine
    # order. Moving a passage is not losing it.
    a = "the first passage says one thing at reasonable length about graphs " * 6
    b = "the second passage says another thing about locks and its costs " * 6
    assert compare(a + b, b + a).recovered == 1.0


def test_markdown_scaffolding_is_stripped_before_comparing(tmp_path) -> None:
    # Front matter, page markers and image paths are not the book's words. Left
    # in, they inflate the score with text the source never contained.
    (tmp_path / "01.md").write_text(
        '---\nbook: "A Book"\nwords: 9\n---\n'
        "<!-- page 21 -->\n\n"
        "![a chart of the law of averages](images/x12.png)\n\n"
        "The system takes a snapshot.\n"
    )
    # Normalised, because that is the form the comparison actually sees.
    text = normalise(markdown_text(str(tmp_path)))
    assert "thesystemtakesasnapshot" in text
    assert "achartofthelawofaverages" in text  # alt text is the book's
    assert "x12" not in text and "png" not in text  # the path is not
    assert "page21" not in text
    assert "abook" not in text


def test_the_gaps_are_reported_longest_first(tmp_path) -> None:
    keep = "the service scales out when the request queue grows past the limit. " * 12
    small = "A short aside about slippage that also went missing here. "
    big = "A much longer passage about buffer sizing that went missing entirely. " * 5
    r = compare(keep + small + keep + big, keep)
    assert len(r.gaps) >= 2
    assert r.gaps[0].length > r.gaps[1].length


def test_scattered_small_gaps_are_counted_apart_from_paragraph_sized_ones() -> None:
    """The distinction the headline percentage cannot make.

    A converted book has one small gap per page, because the running head was
    removed on purpose. It should never have a gap the size of a paragraph.
    Rolling both into one number means a real hole has to compete with the
    furniture for the reader's attention, and the furniture always wins.
    """
    keep = "the service scales out when the request queue grows past the limit. " * 30
    head = " chapter four request routing "
    src = keep + head + keep + head + keep
    r = compare(src, keep)
    assert r.gap_count >= 2
    assert r.big_gaps == 0  # nothing paragraph-sized is gone

    lost = "A whole paragraph about adaptive buffering that is simply not there. " * 8
    r2 = compare(src + lost, keep)
    assert r2.big_gaps == 1
    assert r2.big_chars > 400


def test_a_loss_spread_one_line_per_page_is_invisible_to_the_big_gap_count() -> None:
    """Recorded because it is the limit of the signal above.

    The furniture bug removes the top line of every page. That is thousands of
    words in a real book and not one gap reaches paragraph size, so `big_gaps`
    stays at zero while the book is being hollowed out. Measured on one real book with
    the bug reintroduced: 1,383 words gone, `big_gaps` 0 in both the correct and
    the broken conversion. What moves is the count of small gaps and the missing
    total — which is why the CLI reports characters missing *per page*.
    """

    # Each page has to say something different. Repeat one paragraph forty times
    # and deleting a line from every page loses nothing unique — the same text
    # is still present elsewhere, and the measurement reads a hollowed-out book
    # as complete. The same mistake the PDF fixtures had to be rescued from.
    def page(n):
        # Three different sentences, not one repeated three times: a page that
        # repeats itself hides its own first line just as well as a book that
        # repeats its pages does.
        return "".join(
            "line %d.%d of the book discusses %s and what it does to the "
            "request that gets served. " % (n, k, WORDS[(n * 3 + k) % len(WORDS)])
            for k in range(3)
        )

    head = "chapter four request routing "
    src = "".join(head + page(n) for n in range(40))
    out = "".join(page(n) for n in range(40))  # heads removed: correct
    hollow = "".join(page(n)[70:] for n in range(40))  # a line per page also gone

    good, bad = compare(src, out), compare(src, hollow)
    assert good.big_gaps == 0 and bad.big_gaps == 0  # neither is visible here
    assert bad.missing_chars > good.missing_chars * 1.5  # but this moves


# --- what the converter never claimed to convert --------------------------


def test_an_epub_document_that_produced_no_output_is_named(tmp_path) -> None:
    """A 91.6% that is really 97% plus a named index.

    One real book's table of contents is 48,820 characters and its index is 37,430,
    and both are dropped as navigation on purpose (N6). Rolled into one
    percentage they look exactly like 86,000 characters of lost book. The
    reader should not have to work that out, and should not have to trust that
    the drop was deliberate either — the documents are named and measured, and
    a chapter appearing in that list is a real bug.
    """
    (tmp_path / "01.md").write_text('---\nsource_file: "c01.xhtml"\n---\nBody.\n')
    (tmp_path / "02.md").write_text('---\nsource_file: "c02.xhtml, c03.xhtml"\n---\nMore.\n')
    assert converted_units(str(tmp_path)) == {"c01.xhtml", "c02.xhtml", "c03.xhtml"}


def test_a_pdf_page_range_is_read_back_out_of_the_front_matter(tmp_path) -> None:
    (tmp_path / "01.md").write_text('---\npdf_pages: "1-12"\n---\nBody.\n')
    (tmp_path / "02.md").write_text('---\npdf_pages: "13-24"\n---\nMore.\n')
    assert converted_pages(str(tmp_path)) == set(range(1, 25))


def test_a_directory_with_no_provenance_claims_nothing(tmp_path) -> None:
    # An output directory that does not say where it came from cannot be
    # credited with skipping anything on purpose.
    (tmp_path / "01.md").write_text("no front matter at all\n")
    assert converted_units(str(tmp_path)) == set()
    assert converted_pages(str(tmp_path)) == set()


def test_the_comparison_can_be_restricted_to_what_the_output_claims(tmp_path) -> None:
    """The number that is actually comparable between books.

    Subtracting the skipped documents from the total is not good enough: a table
    of contents repeats every chapter title, and those titles *are* in the
    output, so its characters are not all missing. Restricting the source to the
    documents the output names is exact where the subtraction is an estimate.
    """
    body = (
        "<p>The first chapter says one particular thing, at enough length "
        "that a sixteen-character window has several of them to land in.</p>"
    )
    prose = (
        "The first chapter says one particular thing, at enough length "
        "that a sixteen-character window has several of them to land in."
    )
    epub_path = make_epub(
        tmp_path / "b.epub",
        [
            ("c01.xhtml", "Chapter 1", body),
            ("bm01.xhtml", "Index", "<p>alpha 12, beta 45, gamma 78, delta 90, epsilon 33</p>"),
        ],
    )
    (tmp_path / "01.md").write_text('---\nsource_file: "c01.xhtml"\n---\n%s\n' % prose)
    whole = kept_source_text(epub_path, str(tmp_path), whole=True)
    kept = kept_source_text(epub_path, str(tmp_path))
    assert "alpha" in normalise(whole)
    assert "alpha" not in normalise(kept)
    assert compare(kept, markdown_text(str(tmp_path))).recovered == 1.0


def test_a_character_reference_in_the_source_is_read_as_its_character(tmp_path) -> None:
    # Found by the bundled example: `&#x2212;` (a minus sign) was counted as the
    # letters "x2212" and reported as a gap the converter could never close.
    from h2m.verify import epub_text

    path = make_epub(
        tmp_path / "b.epub",
        [
            ("c01.xhtml", "Chapter 1", "<p>R = 1 &#x2212; M &amp; S &lt; 2</p>"),
        ],
    )
    text = normalise(epub_text(path))
    assert "r1ms2" in text
    assert "x2212" not in text and "amp" not in text and "lt" not in text

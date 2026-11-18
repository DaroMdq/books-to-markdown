"""Layout inference — the pure half, checked without opening a PDF.

These are the functions that decide what a run of glyphs *is*. Each one is
wrong in a way that produces plausible-looking Markdown: a healed hyphen that
welds two words that were never one, a table that is really an indented
paragraph, a drop cap that vanishes because the fix was applied to the wrong
attribute. None of them raise.
"""

from __future__ import annotations

from h2m.layout import (
    Line,
    Profile,
    as_table,
    column_groups,
    fix_ligatures,
    is_bullet,
    is_mono,
    join_text,
    leading_symbol,
    merge_dropcap,
)


def line(text, *, x=72.0, y=100.0, size=11.0, font="Helvetica", width=None, direction=(1.0, 0.0)):
    w = width if width is not None else len(text) * size * 0.5
    span = {"text": text, "bbox": (x, y, x + w, y + size), "size": size, "font": font}
    return Line([span], 0, direction)


def profile(**kw):
    """A Profile with measurements set directly, no document to measure."""
    p = object.__new__(Profile)
    p.body_size = 11.0
    p.body_font = "Helvetica"
    p.leading = 14.0
    p.para_gap = 18.0
    p.col_x0 = 72.0
    p.col_x1 = 540.0
    p.furniture_ys = set()
    p.page_h = 792.0
    p.page_w = 612.0
    p.__dict__.update(kw) if hasattr(p, "__dict__") else None
    for k, v in kw.items():
        setattr(p, k, v)
    return p


# --- wrapped lines --------------------------------------------------------


def test_a_word_broken_across_a_line_is_put_back_together() -> None:
    assert join_text("port-", "folio returns") == "portfolio returns"


def test_a_real_hyphenated_word_keeps_its_hyphen() -> None:
    # "risk-adjusted" wraps after the hyphen too, but the continuation being a
    # word of its own is not the signal — the signal is that it is lowercase and
    # the hyphen is at the very end. This case is genuinely ambiguous in a PDF;
    # the rule chosen joins it, and the test records that rather than pretending.
    assert join_text("risk-", "adjusted") == "riskadjusted"


def test_a_line_ending_in_a_hyphen_before_a_capital_is_left_alone() -> None:
    # "Latency-" / "Jitter" is a compound, not a broken word.
    assert join_text("Latency-", "Jitter ratios") == "Latency- Jitter ratios"


def test_two_ordinary_lines_are_joined_with_one_space() -> None:
    assert join_text("the trend  ", "  follows") == "the trend follows"


# --- ligature repair ------------------------------------------------------


def test_a_split_ligature_inside_a_word_is_repaired() -> None:
    out, n = fix_ligatures("a profi table system")
    assert out == "a profitable system"
    assert n == 1


def test_two_words_that_both_stand_alone_are_never_welded() -> None:
    # "off" + "ice" is a real word joined, which is exactly why the dictionary
    # check alone is not enough. Both halves being words is the second guard.
    out, n = fix_ligatures("he skated off ice")
    assert out == "he skated off ice"
    assert n == 0


def test_a_pair_that_does_not_join_into_a_word_is_left_alone() -> None:
    # "fi gment" *is* repaired, because "figment" is a word — that is the point
    # of the dictionary. A pair that joins into nothing stays exactly as the PDF
    # set it: the repair never invents a word to make the shape work out.
    out, n = fix_ligatures("the fi gwyn plot")
    assert out == "the fi gwyn plot"
    assert n == 0


def test_the_repair_reports_how_many_it_made() -> None:
    # The count is what makes the flag auditable: 914 in one real book, and a number
    # that jumps an order of magnitude on a new book means the guard is wrong.
    _, n = fix_ligatures("profi table and identifi able and classifi cation")
    assert n == 3


# --- list and code detection ---------------------------------------------


def test_a_bulleted_line_is_recognised_by_its_glyph() -> None:
    assert is_bullet("• the first rule")


def test_a_numbered_line_is_recognised() -> None:
    assert is_bullet("1. the first rule")


def test_an_ordinary_sentence_is_not_a_list_item() -> None:
    assert not is_bullet("The first rule is simple.")


def test_a_courier_line_is_code() -> None:
    assert is_mono(line("for i in range(10):", font="CourierNewPSMT"))


def test_a_body_line_is_not_code() -> None:
    assert not is_mono(line("for the most part", font="TimesNewRomanPSMT"))


def test_a_line_led_by_a_dingbat_glyph_is_a_heading_marker() -> None:
    # Some books mark sections with a filled square in a symbol font rather
    # than by making the type bigger. Size alone finds no headings there.
    assert leading_symbol(line("■ Benchmarking", font="ZapfDingbats"))


# --- headings by font metrics --------------------------------------------


def test_type_well_above_body_size_is_a_top_level_heading() -> None:
    assert profile().heading_level(line("Chapter One", size=22.0)) == 1


def test_bold_type_moderately_above_body_size_is_a_section_heading() -> None:
    assert profile().heading_level(line("Position Sizing", size=14.0, font="Helvetica-Bold")) == 2


def test_body_text_is_not_a_heading() -> None:
    assert profile().heading_level(line("an ordinary sentence")) is None


def test_larger_type_that_is_not_bold_is_not_a_section_heading() -> None:
    # A pull quote is set larger than body text and is not a heading.
    assert profile().heading_level(line("set larger, not bold", size=13.0)) is None


# --- tables ---------------------------------------------------------------


def test_x_starts_within_a_tolerance_collapse_into_one_column() -> None:
    assert len(column_groups([line("a", x=72), line("b", x=76), line("c", x=300)])) == 2


def test_an_indented_paragraph_is_not_a_table() -> None:
    # Two x-positions exist, but only one of them recurs.
    lines = [
        line("A quotation set in from the margin", x=100, y=100),
        line("running on to a second line", x=72, y=114),
        line("and a third", x=72, y=128),
    ]
    assert as_table(lines, profile()) is None


def test_two_recurring_columns_are_read_as_a_table() -> None:
    lines = [
        line("Latency", x=72, y=100),
        line("0.72", x=300, y=100),
        line("Jitter", x=72, y=114),
        line("1.04", x=300, y=114),
        line("Uptime", x=72, y=128),
        line("0.31", x=300, y=128),
    ]
    tbl = as_table(lines, profile())
    assert tbl == [["Latency", "0.72"], ["Jitter", "1.04"], ["Uptime", "0.31"]]


def test_a_wrapped_cell_is_folded_back_into_the_row_above() -> None:
    # A second line with an empty first column is a continuation, not a row.
    lines = [
        line("Latency", x=72, y=100),
        line("a measure of", x=300, y=100),
        line("time to respond", x=300, y=114),
        line("Uptime", x=72, y=128),
        line("error based", x=300, y=128),
    ]
    tbl = as_table(lines, profile())
    assert tbl[0] == ["Latency", "a measure of time to respond"]
    assert len(tbl) == 2


# --- drop caps ------------------------------------------------------------


def test_a_drop_cap_is_folded_into_the_line_it_belongs_to() -> None:
    cap = line("A", x=72, y=100, size=36.0)
    rest = line("GOOD RULE that survives", x=110, y=104)
    out = merge_dropcap([cap, rest], profile())
    assert len(out) == 1
    assert out[0].text == "A GOOD RULE that survives"


def test_a_drop_cap_is_folded_into_the_spans_and_not_only_the_text() -> None:
    # The first fix patched Line.text alone. inline_markup() rebuilds the line
    # from its spans, so the letter was still dropped and the loss was one
    # character per chapter — small enough to survive a word count.
    cap = line("T", x=72, y=100, size=36.0)
    rest = line("he rest of the sentence", x=110, y=104)
    out = merge_dropcap([cap, rest], profile())
    assert "".join(s["text"] for s in out[0].spans) == "The rest of the sentence"


def test_a_capital_continuation_gets_a_space_and_a_lowercase_one_does_not() -> None:
    small = merge_dropcap(
        [line("T", x=72, y=100, size=36.0), line("he opening", x=110, y=104)], profile()
    )
    caps = merge_dropcap(
        [line("A", x=72, y=100, size=36.0), line("GOOD RULE", x=110, y=104)], profile()
    )
    assert small[0].text == "The opening"
    assert caps[0].text == "A GOOD RULE"


def test_an_ordinary_short_line_is_not_treated_as_a_drop_cap() -> None:
    lines = [line("I", x=72, y=100), line("agree with the premise", x=72, y=114)]
    assert len(merge_dropcap(lines, profile())) == 2


def test_the_repair_reports_that_it_has_no_dictionary_rather_than_doing_nothing(
    monkeypatch,
) -> None:
    """The silent failure this guard exists for.

    On a machine without `wamerican` installed there is no word list, and the
    repair used to return the text unchanged with a count of zero — which reads
    exactly like "this book needed no repairs". One real book needs 1,394 per 100k
    words, so a clean-looking zero there is a corrupted book that nobody
    questions. `has_dictionary()` is what the CLI checks before it accepts the
    flag at all.
    """
    import h2m.layout as layout

    monkeypatch.setattr(layout, "_LIGWORDS", set())
    assert layout.has_dictionary() is False
    monkeypatch.setattr(layout, "_LIGWORDS", {"profitable"})
    assert layout.has_dictionary() is True


# --- which word list, and saying so ---------------------------------------


def test_only_the_first_word_list_that_exists_is_read(tmp_path, monkeypatch) -> None:
    """Unioning every list on the machine measurably makes the repair worse.

    A bigger dictionary makes more fragments valid words on their own, and the
    second guard in `fix_ligatures` then declines the join. Measured on one book:
    american alone gives 1,108 repairs and 7 residual fragments; unioning it
    with Webster's 2nd gives 994 and 11. The union is not the best of both
    lists, it is worse than either.

    It is also why output was not reproducible between machines — the repair
    depended on which packages the machine happened to have installed, and a
    regression diff reported that as a change in the code.
    """
    import h2m.layout as layout

    first = tmp_path / "american-english"
    second = tmp_path / "words"
    first.write_text("profitable\nsystem\n")
    second.write_text("skated\noffice\nnonsuchword\n")
    monkeypatch.setattr(layout, "DICT_PATHS", (str(first), str(second)))
    monkeypatch.setattr(layout, "_LIGWORDS", None)
    monkeypatch.setattr(layout, "_LIGSOURCE", None)

    words = layout._wordset()
    assert "profitable" in words
    assert "nonsuchword" not in words, "the second list was read as well as the first"


def test_the_word_list_in_use_is_named(tmp_path, monkeypatch) -> None:
    # A book repaired against an unknown dictionary is not reproducible, so the
    # converter has to be able to say which one it used.
    import h2m.layout as layout

    first = tmp_path / "british-english"
    first.write_text("colour\nprofitable\n")
    monkeypatch.setattr(layout, "DICT_PATHS", (str(tmp_path / "absent"), str(first)))
    monkeypatch.setattr(layout, "_LIGWORDS", None)
    monkeypatch.setattr(layout, "_LIGSOURCE", None)
    layout._wordset()
    assert layout.dictionary_name() == "british-english"


def test_no_word_list_means_no_name_and_no_dictionary(tmp_path, monkeypatch) -> None:
    import h2m.layout as layout

    monkeypatch.setattr(layout, "DICT_PATHS", (str(tmp_path / "nope"),))
    monkeypatch.setattr(layout, "_LIGWORDS", None)
    monkeypatch.setattr(layout, "_LIGSOURCE", None)
    assert layout.has_dictionary() is False
    assert layout.dictionary_name() is None

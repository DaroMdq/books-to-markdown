# Status and possible next steps

## Where this is

Both pipelines and the verifier are complete and have been run on a private corpus of 12 technical books (publisher EPUBs, typeset PDFs and PDF-derived EPUBs): about 400 chapter files and 1.9 million words, every book compared against its source with `h2m verify`. Recovery sits between 92% and 99%; no book has more than four paragraph-sized gaps, and those are recorded below. Those numbers cannot be reproduced from this repository, because the books cannot be committed; what can be reproduced is the suite (`bin/check`) and the bundled example (`tests/test_examples.py`).

| Claim | Evidence | Status |
|---|---|---|
| MathML → LaTeX on the element set publishers use | suite + mutation rows 1–6 | proven |
| layout inference: headings, tables, code, folios, landscape pages | suite + rows 7–15, 29–48 | proven |
| running furniture removed without eating body text | suite + rows 12–13, and the corpus | proven |
| no text lost, across the corpus | `h2m verify` on every book | proven within the 92–99% band |
| ligature repair makes no false joins | two books, every repair read | proven for those two books |
| formulas a book ships only as images | — | not attempted |

## The mutation table

What each row breaks, and the test that must go red. Run a row by making the change, watching the named test fail, reverting, and confirming green. **A mutation that passes means the guard is decorative and must be rewritten before anything else proceeds.** Each row was run when its test was written; rows 7, 23, 24, 49 and 50 were re-run on this tree before it was published.

| # | Break | Test that goes red |
|---|---|---|
| 1 | `mathml`: stop escaping `%` `&` `#` `$` | `test_a_percent_operator_is_escaped` (+1) |
| 2 | `mathml`: `msup` emits `^` for a prime | `test_a_prime_is_written_as_a_prime_and_not_as_an_exponent` |
| 3 | `mathml`: no `cases` block for piecewise | `test_a_piecewise_definition_becomes_a_cases_block` |
| 4 | `mathml`: unknown element drops its text | `test_an_element_the_converter_does_not_know_keeps_its_words` |
| 5 | `mathml`: no Mathematical-Italic fold | `test_a_variable_in_the_mathematical_italic_plane_folds_back_to_a_plain_letter` (+1) |
| 6 | `mathml`: `mroot` arguments swapped | `test_an_nth_root_puts_the_index_in_the_optional_argument` |
| 7 | `layout`: drop the both-halves-are-words ligature guard | `test_two_words_that_both_stand_alone_are_never_welded` |
| 8 | `layout`: drop the ligature dictionary check | `test_a_pair_that_does_not_join_into_a_word_is_left_alone` |
| 9 | `layout`: drop cap patches `.text` only, not `.spans` | `test_a_drop_cap_is_folded_into_the_spans_and_not_only_the_text` |
| 10 | `layout`: no hyphenation healing | `test_a_word_broken_across_a_line_is_put_back_together` (+2) |
| 11 | `layout`: one recurring column is enough for a table | `test_an_indented_paragraph_is_not_a_table` |
| 12 | `layout`: furniture is any recurring height | `test_body_text_set_high_on_the_page_is_not_eaten_by_the_running_head` (+4) |
| 13 | `layout`: furniture drops a band, not exact heights | same (+6) |
| 14 | `layout`: folio by page-width fraction, not measured column | `test_a_number_inside_the_text_column_is_not_read_as_a_page_number` |
| 15 | `pdf`: always take the deepest outline level | `test_an_outline_that_would_split_the_book_into_fragments_is_not_used` |
| 16 | `epub`: do not unwrap MathML from HTML comments | `test_mathml_hidden_in_an_html_comment_is_recovered_as_latex` (+1) |
| 17 | `epub`: emit HTML comments as body text | `test_a_comment_that_is_not_mathml_never_reaches_the_markdown` |
| 18 | `epub`: whitespace pass reaches inside code fences | `test_code_shipped_as_nested_divs_becomes_a_fenced_block` (+2) |
| 19 | `epub`: do not escape a literal `$` in prose | `test_a_price_in_the_prose_is_not_read_as_mathematics` |
| 20 | `epub`: drop the page marker held inside a heading | `test_a_publisher_heading_shape_survives_intact` |
| 21 | `epub`: keep the contents page and index as content | `test_the_table_of_contents_is_dropped_as_navigation` |
| 22 | `epub`: fixed two-digit filename padding | `test_files_are_named_so_that_plain_sorting_keeps_the_reading_order` |
| 23 | `epub`: a figure holding a table renders as a picture | `test_a_table_wrapped_in_a_figure_is_still_a_table` |
| 24 | `pdf`: accept `--fix-ligatures` with no dictionary | `test_the_converter_refuses_the_ligature_flag_when_it_has_no_dictionary` |
| 25 | `verify`: the normaliser keeps the spaces | `test_the_normaliser_keeps_letters_and_digits_and_nothing_else` (+5) |
| 26 | `verify`: cannot read the output's front matter | `test_an_epub_document_that_produced_no_output_is_named` (+2) |
| 27 | `verify`: ignore the output's own provenance | `test_the_comparison_can_be_restricted_to_what_the_output_claims` |
| 28 | `verify`: never report a paragraph-sized gap | `test_scattered_small_gaps_are_counted_apart_from_paragraph_sized_ones` |
| 29 | `layout`: harvest a folio only from a whole-line number | `test_a_folio_set_inside_the_running_head_is_still_harvested` |
| 30 | `layout`: never treat a page as landscape | `test_a_page_printed_sideways_is_content_not_margin_furniture` |
| 31 | `layout`: any rotated line makes a page landscape | `test_a_chart_with_many_rotated_labels_is_not_a_landscape_page` |
| 32 | `layout`: one rotated line is enough to make a page landscape | `test_a_single_rotated_caption_does_not_make_a_page_landscape` |
| 33 | `layout`: keep a landscape page's lines but skip the rotation | `test_a_page_printed_sideways_is_content_not_margin_furniture` |
| 34 | `layout`: keep reading word lists past the first | `test_only_the_first_word_list_that_exists_is_read` |
| 35 | `layout`: stop naming the word list in use | `test_the_word_list_in_use_is_named` (+1) |
| 36 | `pdf`: stop recording the dictionary in front matter | `test_a_repaired_book_records_what_it_was_repaired_against` |
| 37 | `layout`: the control scrub deletes instead of substituting | `test_an_unmapped_glyph_becomes_a_space_and_not_nothing` |
| 38 | `layout`: no control scrub at all | `test_a_folio_carrying_an_unmapped_glyph_is_still_harvested` (+1) |
| 39 | `layout`: backspace dropped from the control class | same (+1) |
| 40 | `layout`: `page_lines` classifies against the raw text | same (+1) |
| 41 | `layout`: the landscape folio reads the raw text | `test_a_landscape_page_keeps_its_folio_through_an_unmapped_glyph` |
| 42 | `layout`: no folio bands at all | `test_a_folio_dropped_to_the_foot_of_a_chapter_opening_is_harvested` (+1) |
| 43 | `layout`: a band needs one page, not four | `test_two_pages_agreeing_by_chance_do_not_make_a_folio_band` |
| 44 | `layout`: a band need not step with the page | `test_a_number_that_increases_but_does_not_track_the_page_is_not_a_folio` |
| 45 | `layout`: two numbers at one height still make a band | `test_a_height_carrying_two_numbers_on_one_page_is_not_a_folio_band` |
| 46 | `layout`: the band overrides a folio already found | `test_a_running_head_folio_beats_a_number_at_the_folio_height` |
| 47 | `layout`: the band's folio is left in the body text | `test_a_folio_dropped_to_the_foot_of_a_chapter_opening_is_harvested` |
| 48 | `layout`: lockstep compares values, not their steps | `test_a_number_that_increases_but_does_not_track_the_page_is_not_a_folio` |
| 49 | `epub`: a display equation at block level falls through to the container branch | `test_a_display_equation_set_directly_in_the_body_is_kept` (+1) |
| 50 | `verify`: character references are not unescaped | `test_a_character_reference_in_the_source_is_read_as_its_character` |
| 51 | `epub`: `MARK` written as the raw byte instead of `"\x01"` | `test_no_source_file_contains_a_raw_control_character` |

**Eight rows came back NOT CAUGHT the first time: 14, 21, 22, 31, 32, 33, 41 and 47.** Every one looked like coverage until it was run:

- **21.** The fixture was a file named `toc.xhtml`. A filename rule catches that before the heading rule is reached, so the test proved only that "toc" is spelled "toc". Renamed to `bm01.xhtml`, it now fails when the guard is broken.
- **22.** The fixture built 14 documents, and two digits are enough for 14, so a hard-coded `%02d` looked correct. It takes more than a hundred documents to see the bug; the test now builds 105.
- **14.** The stray number sat *above* the real folio, and the last folio found on a page wins, so the correct value overwrote the wrong one before the assertion ran.
- **31–33.** The two landscape guards masked each other, so neither was individually load-bearing; and the sideways test asserted only that the cells were *present*, which a page kept but not rotated still satisfies, column-major and unreadable.
- **41.** The control scrub was applied in both places that read a folio, but only one had a test.
- **47.** The opener test checked that the folio arrived as a marker and never that it had *left* the body.

Rows 49 and 50 come from the bundled example: writing it exposed a display equation that was counted in the census and then dropped, and a verifier that read `&#x2212;` as the letters `x2212`. Both tests were watched failing before the fix.

## Possible next steps

Ranked. None blocks using the tool.

1. **Formulas shipped only as images.** Some books render every equation as a picture with empty alt text; they are referenced in place but never read. A model pass (image to LaTeX) would only be acceptable with its own verifier, for example rendering the LaTeX back and comparing it with the source image, so that it fails loudly rather than plausibly.
2. **Name figures the EPUB references but does not contain.** `extract_images` skips them silently.
3. **Paragraph-sized gaps in numeric tables in one typeset PDF.** Four remain, all numeric tables; same family as the landscape and figure-wrapped tables already fixed, not yet diagnosed.
4. **Measure the PDF page size from the most common page, not page 0.** Some books ship a cover at a different size; the bands currently still land correctly, which is exactly why it is worth fixing before something moves.
5. **Resolve unmapped glyphs per font** instead of passing them through as control bytes; and treat the two control codes some books use as hard line breaks as line breaks.
6. **Give the PDF front matter the same census fields as the EPUB one** (equations, figures).
7. **Share the fence-parking helper** duplicated in `epub.py` and `pdf.py`, and split the four longest functions (`pdf.main`, `epub.main`, `Renderer.block`, `mathml.conv`, each over 100 lines), with the mutation table as the safety net.
8. **An optional `verify` threshold** (for example `--min-recovered`) for use as a CI gate.

## Deliberately not built

- **A packaged corpus.** The Markdown is derived from copyrighted books; this repository ships the tools that make it.
- **OCR.** Every supported source is a text PDF or an EPUB. A scanned book is a different project.
- **Chunking, embedding, or anything downstream.** One file per chapter with a page-marked body is the hand-off point.

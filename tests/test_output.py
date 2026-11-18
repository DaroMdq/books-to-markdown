"""The two helpers both converters write their output with.

A slug becomes a filename and a YAML scalar becomes a front-matter field, so
both have to be safe for anything a book's title page can hold.
"""

from __future__ import annotations

from h2m.output import slugify, yaml_str


def test_a_slug_folds_accents_and_drops_punctuation() -> None:
    assert slugify("Café Society: A Reader's Guide!") == "cafe-society-a-readers-guide"


def test_runs_of_spaces_underscores_and_hyphens_become_one_hyphen() -> None:
    assert slugify("  part__one -- the  start ") == "part-one-the-start"


def test_a_slug_is_cut_to_length_without_a_trailing_hyphen() -> None:
    assert slugify("chapter one of the book", 8) == "chapter"


def test_a_title_with_nothing_usable_still_gets_a_slug() -> None:
    assert slugify("") == "untitled"
    assert slugify(None) == "untitled"
    assert slugify("日本語") == "untitled"


def test_a_yaml_scalar_escapes_quotes_and_backslashes() -> None:
    assert yaml_str('a "quoted" C:\\path') == '"a \\"quoted\\" C:\\\\path"'


def test_a_yaml_scalar_is_one_line() -> None:
    assert yaml_str("  two\nlines\tand a tab ") == '"two lines and a tab"'


def test_a_yaml_scalar_accepts_a_non_string() -> None:
    assert yaml_str(42) == '"42"'

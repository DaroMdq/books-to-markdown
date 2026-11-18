"""MathML -> LaTeX, checked against the shapes the real books actually emit.

Every fragment here is written by hand in the *shape* publisher XHTML uses — the
MathML namespace, `display="block"` on a numbered display, variables in the
Mathematical Italic plane (U+1D400) rather than as ASCII letters. Nothing is
pasted out of a book; the point is the markup convention, not the formula.

The failures worth guarding are the silent ones. A `%` that comments out the rest
of a LaTeX line, a prime rendered `M^'`, a piecewise definition flattened into a
single row: none of these raise, and all three read as plausible output until
something downstream tries to typeset them.
"""

from __future__ import annotations

from h2m.mathml import mathml_to_latex

NS = 'xmlns="http://www.w3.org/1998/Math/MathML"'


def tex(inner: str, block: bool = False) -> str:
    attr = ' display="block"' if block else ""
    latex, _ = mathml_to_latex("<math %s%s>%s</math>" % (NS, attr, inner))
    return latex


# --- the plane fold -------------------------------------------------------
# Some publishers set every variable in Mathematical Italic. Read literally, a book of
# formulas comes out as a book of codepoints no LaTeX engine will accept.


def test_a_variable_in_the_mathematical_italic_plane_folds_back_to_a_plain_letter() -> None:
    assert tex("<mi>\U0001d443</mi>") == "P"  # MATHEMATICAL ITALIC CAPITAL P


def test_a_digit_in_the_mathematical_plane_folds_back_to_a_plain_digit() -> None:
    assert tex("<mn>\U0001d7d9</mn>") == "1"  # MATHEMATICAL DOUBLE-STRUCK ONE


def test_a_greek_letter_becomes_its_latex_macro() -> None:
    assert tex("<mi>σ</mi>") == r"\sigma"


def test_a_multi_letter_identifier_is_kept_upright_as_a_word() -> None:
    # "ATR", "EMA" and friends are names, not three variables multiplied.
    assert tex("<mi>ATR</mi>") == r"\mathit{ATR}"


# --- the operators that eat the rest of the line ---------------------------


def test_a_percent_operator_is_escaped() -> None:
    # Unescaped, `%` comments out everything after it and the equation silently
    # loses its right-hand side.
    assert tex("<mn>50</mn><mo>%</mo>") == r"50 \%"


def test_an_ampersand_operator_is_escaped() -> None:
    # Bare `&` is an alignment tab; inside an array it moves a term to the wrong column.
    assert tex("<mo>&amp;</mo>") == r"\&"


def test_a_minus_sign_becomes_a_hyphen_rather_than_the_unicode_glyph() -> None:
    assert tex("<mi>a</mi><mo>−</mo><mi>b</mi>") == "a - b"


# --- scripts --------------------------------------------------------------


def test_a_prime_is_written_as_a_prime_and_not_as_an_exponent() -> None:
    # `M^'` is not valid; `M'` is. The distinction is invisible until it is typeset.
    assert tex("<msup><mi>M</mi><mo>′</mo></msup>") == "M'"


def test_a_prime_on_a_subscripted_variable_is_also_a_prime() -> None:
    # The msup fix missed msubsup once; seven equations shipped with `X_i^'`.
    assert tex("<msubsup><mi>X</mi><mi>i</mi><mo>′</mo></msubsup>") == "X_i'"


def test_a_real_exponent_still_uses_a_caret() -> None:
    assert tex("<msup><mi>x</mi><mn>2</mn></msup>") == "x^2"


def test_a_sum_carries_both_its_bounds() -> None:
    got = tex(
        "<munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>N</mi></munderover>"
    )
    assert got == r"\sum_{i = 1}^N"


def test_an_overbar_becomes_a_bar_accent_rather_than_an_overset() -> None:
    assert tex("<mover><mi>x</mi><mo>¯</mo></mover>") == r"\bar{x}"


# --- structure ------------------------------------------------------------


def test_a_fraction_becomes_a_frac() -> None:
    assert tex("<mfrac><mi>a</mi><mi>b</mi></mfrac>") == r"\frac{a}{b}"


def test_an_nth_root_puts_the_index_in_the_optional_argument() -> None:
    # \sqrt[n]{x}, not \sqrt[x]{n} — the MathML child order is the other way round.
    assert tex("<mroot><mi>x</mi><mi>n</mi></mroot>") == r"\sqrt[n]{x}"


def test_a_piecewise_definition_becomes_a_cases_block() -> None:
    # `mfenced open="{"` with no close is how a piecewise function is written.
    # Flattened, the two branches read as one expression and the condition is lost.
    got = tex(
        '<mfenced open="{" close="">'
        "<mtable><mtr><mtd><mn>1</mn></mtd><mtd><mi>x</mi><mo>&gt;</mo><mn>0</mn></mtd></mtr>"
        "<mtr><mtd><mn>0</mn></mtd><mtd><mtext>otherwise</mtext></mtd></mtr></mtable>"
        "</mfenced>"
    )
    assert got == r"\begin{cases} 1 & x > 0 \\ 0 & \text{otherwise} \end{cases}"


def test_ordinary_parentheses_survive_as_a_left_right_pair() -> None:
    assert tex("<mfenced><mi>x</mi></mfenced>") == r"\left( x \right)"


def test_text_inside_an_equation_is_escaped_before_it_reaches_latex() -> None:
    assert tex("<mtext>a_b</mtext>") == r"\text{a\_b}"


# --- how it fails ---------------------------------------------------------


def test_a_display_equation_reports_itself_as_a_block() -> None:
    _, block = mathml_to_latex('<math %s display="block"><mi>x</mi></math>' % NS)
    assert block is True


def test_an_inline_equation_does_not() -> None:
    _, block = mathml_to_latex("<math %s><mi>x</mi></math>" % NS)
    assert block is False


def test_an_unparseable_fragment_returns_none_rather_than_raising() -> None:
    # 1,698 equations in one book: one malformed fragment must not end the run.
    latex, _ = mathml_to_latex("<math %s><mi>x</mi>" % NS)
    assert latex is None


def test_an_element_the_converter_does_not_know_keeps_its_words() -> None:
    # Degrading to the text is a visible loss of notation; dropping the element
    # is an invisible loss of content. Only the first is acceptable.
    assert "kurtosis" in tex("<mglyph>kurtosis</mglyph>")

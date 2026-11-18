"""MathML -> LaTeX. Covers the element set publisher EPUBs use in practice.

Deliberately small: no external deps, no DOM library beyond stdlib ElementTree.
Unknown elements degrade to their concatenated text rather than vanishing.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

MML = "{http://www.w3.org/1998/Math/MathML}"

# Unicode operator -> LaTeX. Anything not listed passes through verbatim.
OPS = {
    "−": "-",
    "×": r"\times",
    "÷": r"\div",
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "√": r"\sqrt",
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "≡": r"\equiv",
    "±": r"\pm",
    "∓": r"\mp",
    "∞": r"\infty",
    "→": r"\to",
    "⇒": r"\Rightarrow",
    "∈": r"\in",
    "∉": r"\notin",
    "⊂": r"\subset",
    "⊆": r"\subseteq",
    "∪": r"\cup",
    "∩": r"\cap",
    "∂": r"\partial",
    "∇": r"\nabla",
    "·": r"\cdot",
    "•": r"\cdot",
    "⋯": r"\cdots",
    "…": r"\ldots",
    "⋮": r"\vdots",
    "⋱": r"\ddots",
    "′": "'",
    "″": "''",
    "°": r"^{\circ}",
    "∣": "|",
    "∥": r"\|",
    "←": r"\leftarrow",
    "¬": r"\neg",
    "∧": r"\wedge",
    "∨": r"\vee",
    "∀": r"\forall",
    "∃": r"\exists",
    "∼": r"\sim",
    "∝": r"\propto",
    "≅": r"\cong",
    "∑̂": r"\sum",
    "–": "-",
    "—": "---",
    " ": r"\,",
    "⁢": "",
    "⁡": "",
    "⁤": "",
}

# Combining/stretchy accents that appear as <mo> inside <mover>.
ACCENTS = {
    "̂": r"\hat",
    "^": r"\hat",
    "̄": r"\bar",
    "¯": r"\bar",
    "̃": r"\tilde",
    "~": r"\tilde",
    "̇": r"\dot",
    "̈": r"\ddot",
    "→": r"\vec",
    "⃗": r"\vec",
}

GREEK = {
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\phi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
}


# Some publishers use Mathematical Italic codepoints (U+1D400 block) for variables.
def _fold_math_alphanum(s):
    out = []
    for ch in s:
        cp = ord(ch)
        if 0x1D400 <= cp <= 0x1D7FF:
            # Map the styled plane back to ASCII / Greek by offset within block.
            for base, start in (
                (0x1D400, "A"),
                (0x1D41A, "a"),
                (0x1D434, "A"),
                (0x1D44E, "a"),
                (0x1D468, "A"),
                (0x1D482, "a"),
                (0x1D4D0, "A"),
                (0x1D4EA, "a"),
                (0x1D5A0, "A"),
                (0x1D5BA, "a"),
                (0x1D608, "A"),
                (0x1D622, "a"),
                (0x1D670, "A"),
                (0x1D68A, "a"),
            ):
                if base <= cp < base + 26:
                    out.append(chr(ord(start) + cp - base))
                    break
            else:
                if 0x1D7CE <= cp <= 0x1D7FF:  # styled digits
                    out.append(str((cp - 0x1D7CE) % 10))
                elif 0x1D6A8 <= cp <= 0x1D6E1:  # styled Greek capitals/lowercase
                    out.append(chr(0x0391 + (cp - 0x1D6A8)))
                elif 0x1D6FC <= cp <= 0x1D735:
                    out.append(chr(0x03B1 + (cp - 0x1D6FC)))
                else:
                    out.append(ch)
        else:
            out.append(ch)
    return "".join(out)


def _tx(s):
    """Normalise a leaf token to LaTeX-safe text."""
    if s is None:
        return ""
    s = _fold_math_alphanum(s)
    s = "".join(GREEK.get(c, c) for c in s)
    return s


def _esc_text(s):
    for a, b in (
        ("\\", r"\backslash "),
        ("{", r"\{"),
        ("}", r"\}"),
        ("%", r"\%"),
        ("&", r"\&"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("$", r"\$"),
    ):
        s = s.replace(a, b)
    return s


def _tag(el):
    return el.tag.replace(MML, "")


def _brace(s):
    """Wrap in braces unless already a single token."""
    s = s.strip()
    if len(s) == 1 or (re.fullmatch(r"\\?[A-Za-z]+", s) and len(s) <= 2):
        return s
    return "{" + s + "}"


def _kids(el):
    return [c for c in el if isinstance(c.tag, str)]


def conv(el):
    t = _tag(el)
    ch = _kids(el)

    if t in ("math", "mrow", "mstyle", "semantics", "mpadded"):
        return " ".join(x for x in (conv(c) for c in ch) if x).strip()

    if t == "mi":
        v = _tx(el.text or "")
        if len(v) > 1 and v.isalpha() and not v.startswith("\\"):
            return r"\mathit{%s}" % v
        return v

    if t == "mn":
        return _tx(el.text or "")

    if t == "mo":
        raw = _tx(el.text or "")
        if raw in OPS:
            return OPS[raw]
        # Bare %, &, # would be swallowed by LaTeX (comment / align / macro).
        return {"%": r"\%", "&": r"\&", "#": r"\#", "$": r"\$"}.get(raw, raw)

    if t == "mtext":
        v = _tx(el.text or "")
        if not v.strip():
            return r"\ "
        return r"\text{%s}" % _esc_text(v)

    if t == "mspace":
        return r"\,"

    if t == "msub":
        return "%s_%s" % (_brace(conv(ch[0])), _brace(conv(ch[1]))) if len(ch) == 2 else ""

    if t == "msup":
        if len(ch) != 2:
            return ""
        sup = conv(ch[1]).strip()
        if sup in ("'", "''", "'''"):  # prime: M' not M^'
            return "%s%s" % (_brace(conv(ch[0])), sup)
        return "%s^%s" % (_brace(conv(ch[0])), _brace(sup))

    if t == "msubsup":
        if len(ch) == 3:
            sup = conv(ch[2]).strip()
            if sup in ("'", "''", "'''"):
                return "%s_%s%s" % (_brace(conv(ch[0])), _brace(conv(ch[1])), sup)
            return "%s_%s^%s" % (_brace(conv(ch[0])), _brace(conv(ch[1])), _brace(sup))
        return ""

    if t == "mfrac":
        if len(ch) == 2:
            return r"\frac{%s}{%s}" % (conv(ch[0]), conv(ch[1]))
        return ""

    if t == "msqrt":
        return r"\sqrt{%s}" % " ".join(conv(c) for c in ch)

    if t == "mroot":
        if len(ch) == 2:
            return r"\sqrt[%s]{%s}" % (conv(ch[1]), conv(ch[0]))
        return ""

    if t in ("mover", "munder", "munderover"):
        base = conv(ch[0]) if ch else ""
        if t == "mover" and len(ch) == 2:
            acc = (ch[1].text or "").strip()
            if acc in ACCENTS:
                return "%s{%s}" % (ACCENTS[acc], base)
            return r"\overset{%s}{%s}" % (conv(ch[1]), _brace(base))
        if t == "munder" and len(ch) == 2:
            return "%s_%s" % (base, _brace(conv(ch[1])))
        if t == "munderover" and len(ch) == 3:
            return "%s_%s^%s" % (base, _brace(conv(ch[1])), _brace(conv(ch[2])))
        return base

    if t == "mfenced":
        o = el.get("open", "(")
        c = el.get("close", ")")
        sep = el.get("separators", ",")
        # open="{" with no close is piecewise notation -> proper cases block.
        if o == "{" and not c and len(ch) == 1 and _tag(ch[0]) == "mtable":
            rows = []
            for tr in _kids(ch[0]):
                rows.append(" & ".join(conv(td) for td in _kids(tr)))
            return r"\begin{cases} %s \end{cases}" % r" \\ ".join(rows)
        parts = [conv(k) for k in ch]
        sep = (sep or "").strip()
        joiner = (sep[0] + " ") if sep else " "
        inner = joiner.join(p for p in parts if p)
        lo = {"": ".", "|": r"|", "{": r"\{", "[": "["}.get(o, o) or "."
        rc = {"": ".", "|": r"|", "}": r"\}", "]": "]"}.get(c, c) or "."
        return r"\left%s %s \right%s" % (lo, inner, rc)

    if t == "menclose":
        return r"\overline{%s}" % " ".join(conv(c) for c in ch)

    if t == "mtable":
        rows = []
        for tr in ch:
            cells = [conv(td) for td in _kids(tr)]
            rows.append(" & ".join(cells))
        body = r" \\ ".join(rows)
        ncol = max((len(_kids(tr)) for tr in ch), default=1)
        return r"\begin{array}{%s} %s \end{array}" % ("c" * ncol, body)

    if t in ("mtr", "mtd"):
        return " ".join(conv(c) for c in ch)

    if t == "mmultiscripts":
        return conv(ch[0]) if ch else ""

    # Unknown element: keep the words rather than dropping them.
    txt = "".join(el.itertext())
    return _tx(txt).strip()


def mathml_to_latex(fragment: str) -> tuple[str | None, bool]:
    """Convert one <math>...</math> string to LaTeX. Returns (latex, is_block)."""
    frag = fragment.strip()
    block = 'display="block"' in frag[:200]
    # ElementTree chokes on undeclared entities; the source uses numeric ones only.
    try:
        root = ET.fromstring(frag)
    except ET.ParseError:
        frag2 = re.sub(r'\sxmlns_xlink="[^"]*"', "", frag)
        frag2 = re.sub(r"\s(?:epub|xlink):\w+=\"[^\"]*\"", "", frag2)
        try:
            root = ET.fromstring(frag2)
        except ET.ParseError:
            return None, block
    out = conv(root)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([_^])\s+", r"\1", out)
    return out, block

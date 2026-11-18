"""Turn a text PDF's spans into classified, reflowed blocks.

A PDF has no structure — only glyphs at coordinates. Everything here is
inferred from geometry and font metrics, so every threshold is derived from
the document itself (see `Profile.measure`) rather than hard-coded.
"""

from __future__ import annotations

import collections
import itertools
import os
import re

HYPHENS = "‐‑‒–­-"

# A glyph the font's ToUnicode map does not cover comes back as a C0 control.
# One typeset PDF ends every verso folio with one ("2\x08"), and because a
# backspace is not whitespace, `str.strip()` left it in place and the
# bare-number test failed — every left-hand page in the book lost its marker
# while every right-hand page kept it. Scrub these before classifying a line,
# never from the line itself: in other books the same kind of control stands
# for a real symbol (a multiplication sign, a vertical bar) that deleting would
# quietly destroy. Tab and newline are left alone: they are layout, not damage.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def classify_text(text):
    """A line's text as the classifiers should see it, not as it prints."""
    return CONTROL.sub(" ", text).strip()


BARE_NUMBER = re.compile(r"[ivxlcdm]+|\d{1,4}", re.I)
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def folio_value(text):
    """A folio as a number, arabic or roman, so two of them can be compared."""
    if text.isdigit():
        return int(text)
    t = text.lower()
    total = 0
    for a, b in zip(t, t[1:] + " "):
        total += -_ROMAN[a] if _ROMAN[a] < _ROMAN.get(b, 0) else _ROMAN[a]
    return total


def _round(x, n=1):
    return round(x, n)


class Line:
    __slots__ = (
        "bold",
        "dir",
        "font",
        "italic",
        "kind",
        "page",
        "size",
        "spans",
        "text",
        "x0",
        "x1",
        "y0",
        "y1",
    )

    def __init__(self, spans, page, direction=(1.0, 0.0)):
        self.spans = spans
        self.page = page
        self.dir = tuple(round(x, 2) for x in direction)
        self.text = "".join(s["text"] for s in spans)
        xs = [s["bbox"] for s in spans]
        self.x0 = min(b[0] for b in xs)
        self.x1 = max(b[2] for b in xs)
        self.y0 = min(b[1] for b in xs)
        self.y1 = max(b[3] for b in xs)
        big = max(spans, key=lambda s: len(s["text"]) or 1)
        self.size = round(big["size"], 1)
        self.font = big["font"]
        self.bold = "Bold" in self.font or "Semibold" in self.font
        self.italic = "Italic" in self.font or "Oblique" in self.font
        self.kind = None

    def __repr__(self):
        return "<%s p%d y%.0f %.0f %r>" % (self.kind, self.page, self.y0, self.size, self.text[:40])


class Profile:
    """Document-level measurements used to classify lines."""

    def __init__(self, doc, sample=None):
        self.doc = doc
        self.page_h = doc[0].rect.height
        self.page_w = doc[0].rect.width
        self.measure(sample or range(min(len(doc), 400)))

    def measure(self, pages):
        sizes = collections.Counter()
        fonts = collections.Counter()
        ytop = collections.Counter()
        ybot = collections.Counter()
        gaps = []
        for i in pages:
            prev = None
            for ln in raw_lines(self.doc, i):
                t = ln.text.strip()
                if not t:
                    continue
                sizes[ln.size] += len(t)
                fonts[(ln.size, ln.font)] += len(t)
                if ln.y0 < self.page_h * 0.10:
                    ytop[round(ln.y0)] += 1
                if ln.y0 > self.page_h * 0.86:
                    ybot[round(ln.y0)] += 1
        self.body_size = sizes.most_common(1)[0][0] if sizes else 11.0
        self.body_font = max(
            (k for k in fonts if abs(k[0] - self.body_size) < 0.2),
            key=lambda k: fonts[k],
            default=(self.body_size, ""),
        )[1]
        # Header / footer bands. A recurring *position* proves nothing — dense
        # layouts start body text high on the page. Running furniture is
        # recurring *text*, so look for the same string (ignoring digits)
        # appearing at the same height across many pages.
        n = max(len(list(pages)), 1)
        self.furniture_ys = self._furniture_bands(pages, n)
        self.folio_ys = self._folio_bands(pages)
        # Leading and paragraph gap, from consecutive body lines.
        for i in list(pages)[:120]:
            prev = None
            for ln in raw_lines(self.doc, i):
                if abs(ln.size - self.body_size) > 0.2 or not ln.text.strip():
                    continue
                if prev is not None and 0 < ln.y0 - prev < 40:
                    gaps.append(round(ln.y0 - prev, 1))
                prev = ln.y0
        g = collections.Counter(gaps)
        # Text-column bounds, from body-size lines only. A folio sits outside.
        x0s, x1s = [], []
        for i in list(pages)[:150]:
            for ln in raw_lines(self.doc, i):
                if abs(ln.size - self.body_size) < 0.3 and len(ln.text.strip()) > 25:
                    x0s.append(ln.x0)
                    x1s.append(ln.x1)
        x0s.sort()
        x1s.sort()
        self.col_x0 = x0s[len(x0s) // 20] if x0s else 0.0
        self.col_x1 = x1s[-max(1, len(x1s) // 20)] if x1s else self.page_w
        self.leading = g.most_common(1)[0][0] if g else 13.0
        self.para_gap = self.leading * 1.28
        self.sizes = sizes

    def _furniture_bands(self, pages, n):
        top = collections.defaultdict(collections.Counter)
        bot = collections.defaultdict(collections.Counter)
        for i in pages:
            for ln in raw_lines(self.doc, i):
                t = ln.text.strip()
                if not t or ln.dir != (1.0, 0.0):
                    continue
                key = re.sub(r"\d+", "#", t.lower())[:60]
                if ln.y0 < self.page_h * 0.14:
                    top[round(ln.y0)][key] += 1
                elif ln.y0 > self.page_h * 0.84:
                    bot[round(ln.y0)][key] += 1

        ys = set()
        for buckets in (top, bot):
            for y, c in buckets.items():
                if not c or sum(c.values()) < n * 0.15:
                    continue  # too rare to be running furniture
                # Furniture is drawn from a small vocabulary: one title per
                # chapter, at most. Body text at the same height is not.
                if len(c) <= max(3, n / 12.0):
                    ys.add(y)
        return ys

    def _folio_bands(self, pages):
        """Heights where a bare number counts along with the page index.

        A folio that rides in the running head is already caught, because the
        head recurs often enough to be measured as furniture. A chapter opener
        suppresses the head and drops the folio to the foot instead, and that
        position is out of reach of both existing rules at once: it occurs on
        6-12% of the pages, under the share it takes to read as furniture, and
        it sits inside the text column, so the outer-margin rule cannot see it
        either. In the corpus this was developed against, every such page was the
        first page of a chapter or a part.

        What separates a folio from any other number at a fixed height is that
        it steps in lockstep with the page index. A table cell does not, and
        neither does a part number: one book prints 23 of those, one per page,
        always at the same height and always increasing — and in lockstep on
        none of them, which is the only thing that keeps them out of here.
        """
        buckets = collections.defaultdict(list)
        for i in pages:
            for ln in raw_lines(self.doc, i):
                if ln.dir != (1.0, 0.0):
                    continue
                t = classify_text(ln.text)
                if BARE_NUMBER.fullmatch(t):
                    buckets[round(ln.y0)].append((i, folio_value(t)))

        ys = set()
        for y, hits in buckets.items():
            # Two numbers at one height on one page is a table row, not a folio.
            if len(hits) < FOLIO_MIN_PAGES or len({i for i, _ in hits}) != len(hits):
                continue
            hits.sort()
            steps = list(itertools.pairwise(hits))
            lock = sum(1 for a, b in steps if b[1] - a[1] == b[0] - a[0])
            if lock >= len(steps) * FOLIO_LOCKSTEP:
                ys.add(y)
        return ys

    def heading_level(self, ln):
        """Bigger than body and set bold/semibold => a heading."""
        s = ln.size
        b = self.body_size
        if s >= b * 1.7:
            return 1
        if s >= b * 1.25 and (ln.bold or "Semibold" in ln.font):
            return 2
        if s > b + 0.4 and ln.bold:
            return 3
        return None


def raw_lines(doc, index):
    page = doc[index]
    out = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines", []):
            spans = [s for s in ln["spans"] if s["text"]]
            if spans:
                out.append(Line(spans, index, ln.get("dir", (1.0, 0.0))))
    out.sort(key=lambda l: (round(l.y0, 1), l.x0))
    return out


# A page turned sideways to fit a wide table, against a running head set into
# the margin. Both are rotated text; only how much of the page is rotated tells
# them apart. Measured on the development corpus: a rotated running head is
# 1-11% of its page, a landscape table is 97-100% of its page.
# A folio band has to survive the roman-to-arabic jump at the end of the front
# matter, which breaks lockstep exactly once however long the band is, so the
# share is a share and not "all of them". Four pages is the floor: three steps
# in lockstep by chance is unlikely, two is not.
FOLIO_MIN_PAGES = 4
FOLIO_LOCKSTEP = 0.9

LANDSCAPE_SHARE = 0.9
LANDSCAPE_MIN_ROTATED = 8
SIDEWAYS = (0.0, -1.0)


def unrotate_landscape(page_h, lines):
    """A page printed sideways: its lines in reading order, and its folio.

    Rotated text is normally margin furniture and `page_lines` drops it — some
    books set their running heads that way. But a table too wide for the page is
    often turned a quarter turn rather than shrunk, and then the rotated text is
    the whole page. In one 367-page book 23 pages are landscape tables, and
    dropping them cost 13 tables with their captions: the prose still said
    "Table 8.2 shows..." and underneath there was nothing.

    The rotation is applied to each line's own bounds, so leading, columns,
    paragraph gaps and table detection are all measured in reading order by the
    code that already exists rather than by a second set of rules.

    Returns (None, None) when the page is not landscape. Only a quarter turn
    anticlockwise is handled, because that is the only rotation any book in the
    development corpus uses for a table; the other direction would need its own
    transform and there is nothing to check one against.
    """
    if not lines:
        return None, None
    rot = [ln for ln in lines if ln.dir == SIDEWAYS]
    if len(rot) < LANDSCAPE_MIN_ROTATED or len(rot) / len(lines) < LANDSCAPE_SHARE:
        return None, None
    # The folio stays upright in the footer while the table turns. It is the
    # only upright line left on the page, and it is a bare number.
    folio = None
    for ln in lines:
        t = classify_text(ln.text)
        if ln.dir == (1.0, 0.0) and BARE_NUMBER.fullmatch(t):
            folio = t
    for ln in rot:
        x0, x1, y0, y1 = ln.x0, ln.x1, ln.y0, ln.y1
        ln.x0, ln.x1 = page_h - y1, page_h - y0
        ln.y0, ln.y1 = x0, x1
    rot.sort(key=lambda ln: (round(ln.y0, 1), ln.x0))
    return rot, folio


def page_lines(doc, index, prof):
    """Body lines for one page, with the running head/foot removed."""
    raw = raw_lines(doc, index)
    turned, turned_folio = unrotate_landscape(doc[index].rect.height, raw)
    if turned is not None:
        return turned, turned_folio
    kept, folio, band = [], None, None
    for ln in raw:
        t = classify_text(ln.text)
        if not t:
            continue
        # A bare number sitting where this book's folios sit. Held rather than
        # taken: it is only the folio if nothing else on the page is, because
        # a data table can put a cell at that height too: one real page has
        # "56" there and "25" in its running head, and the head is right.
        if (
            BARE_NUMBER.fullmatch(t)
            and ln.dir == (1.0, 0.0)
            and any(abs(ln.y0 - y) <= 2 for y in prof.folio_ys)
        ):
            band = (ln, t)
        if ln.dir != (1.0, 0.0):
            # Margin furniture — but the folio often rides along with it.
            if BARE_NUMBER.fullmatch(t):
                folio = t
            continue
        # A bare number alone in the outer margin is a folio, wherever it sits
        # vertically — some books set it beside the text block, not below it.
        if BARE_NUMBER.fullmatch(t) and (ln.x0 > prof.col_x1 + 4 or ln.x1 < prof.col_x0 - 4):
            folio = t
            continue
        # Drop only the specific heights running furniture occupies — not
        # everything above or below them, which would take body text with it.
        if any(abs(ln.y0 - y) <= 2 for y in prof.furniture_ys):
            if BARE_NUMBER.fullmatch(t):
                folio = t
            else:
                # Many books set the folio and the running head as one text
                # run — "122  METHODOLOGICAL FOUNDATIONS" on the verso, the
                # mirror image on the recto. Harvesting only whole-line numbers
                # left two thirds of one book with page markers and a third
                # without, which nothing in the output revealed. This is safe
                # precisely because the line is already known to be furniture:
                # a body line opening with a year never reaches here.
                m = re.match(r"^(\d{1,4}|[ivxlcdm]+)\s+\S", t, re.I) or re.search(
                    r"\S\s+(\d{1,4}|[ivxlcdm]+)$", t, re.I
                )
                if m:
                    folio = m.group(1)
            continue
        kept.append(ln)
    if folio is None and band is not None:
        line, folio = band
        kept = [k for k in kept if k is not line]
    return kept, folio


def merge_dropcap(lines, prof):
    """Chapter openings set a huge initial letter beside a small-caps run."""
    if len(lines) < 2:
        return lines
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if len(ln.text.strip()) == 1 and ln.size > prof.body_size * 2 and i + 1 < len(lines):
            nxt = lines[i + 1]
            if abs(nxt.y0 - ln.y0) < ln.size * 1.2:
                cap = ln.text.strip()
                rest = nxt.text
                # "A" + "GOOD RULE..." needs a space; "T" + "he rest" does not.
                sep = " " if rest[:1].isupper() else ""
                nxt.text = cap + sep + rest
                # Emphasis is rebuilt from spans later, so patch the span too.
                nxt.spans = [dict(nxt.spans[0], text=cap + sep + nxt.spans[0]["text"])] + list(
                    nxt.spans[1:]
                )
                nxt.x0 = ln.x0
                out.append(nxt)
                i += 2
                continue
        out.append(ln)
        i += 1
    return out


MONO_HINTS = ("courier", "mono", "consol", "menlo", "inconsolata")
SYMBOL_HINTS = ("dingbat", "symbol", "wingding", "zapf")


def is_mono(line):
    f = (line.font or "").lower()
    return any(h in f for h in MONO_HINTS)


def leading_symbol(line):
    """A heading marked by a bullet glyph rather than by size."""
    if not line.spans:
        return False
    f = (line.spans[0]["font"] or "").lower()
    return any(h in f for h in SYMBOL_HINTS)


def join_text(a, b):
    """Join two wrapped lines, healing end-of-line hyphenation."""
    a = a.rstrip()
    b = b.lstrip()
    if not a:
        return b
    if a[-1] in HYPHENS and len(a) > 1 and a[-2].isalpha() and b[:1].islower():
        return a[:-1] + b
    return a + " " + b


def is_bullet(text):
    return bool(
        re.match(
            r"^\s*(?:[•●▪‣⁃·∙]"
            r"|[-–—]\s|\d{1,2}[.)]\s|[a-z][.)]\s)",
            text,
        )
    )


def inline_markup(ln, prof):
    """Emphasis from font runs, skipping the small-caps opener of a chapter."""
    parts = []
    for s in ln.spans:
        t = s["text"]
        if not t:
            continue
        f = s["font"]
        bold = "Bold" in f or "Semibold" in f
        ital = "Italic" in f or "Oblique" in f
        # A bold run that is the whole line at body size is usually a lead-in
        # or small-caps opener, not emphasis worth marking.
        if bold and ital:
            t = "***%s***" % t.strip() + (" " if t.endswith(" ") else "")
        elif ital and t.strip():
            t = "*%s*" % t.strip() + (" " if t.endswith(" ") else "")
        parts.append(t)
    return "".join(parts)


# --------------------------------------------------------------- table sniff
def column_groups(lines, tol=14):
    """Cluster line x-starts into columns."""
    xs = sorted(l.x0 for l in lines)
    cols = []
    for x in xs:
        if cols and x - cols[-1][-1] <= tol:
            cols[-1].append(x)
        else:
            cols.append([x])
    return [sum(c) / len(c) for c in cols]


def as_table(lines, prof):
    """Lay a run of lines out as rows x columns, or return None.

    A table is recognised by two or more x-columns that both recur down the
    page — a single indented block does not qualify.
    """
    cols = column_groups(lines)
    if len(cols) < 2:
        return None
    # Every column must carry several lines, else it is prose with an indent.
    assign = {}
    for l in lines:
        ci = min(range(len(cols)), key=lambda i: abs(cols[i] - l.x0))
        assign.setdefault(ci, []).append(l)
    if len([c for c in assign.values() if len(c) >= 2]) < 2:
        return None
    # Rows: lines whose y overlaps within a leading.
    rows = []
    for l in sorted(lines, key=lambda l: (l.y0, l.x0)):
        if rows and abs(l.y0 - rows[-1][0]) < prof.leading * 0.8:
            rows[-1][1].append(l)
        else:
            rows.append([l.y0, [l]])
    # Merge continuation rows: a row whose cells all continue the row above
    # (same columns, no new leading column-1 entry) belongs to it.
    table = []
    for _, cells in rows:
        slot = [""] * len(cols)
        for l in cells:
            ci = min(range(len(cols)), key=lambda i: abs(cols[i] - l.x0))
            slot[ci] = join_text(slot[ci], l.text.strip()) if slot[ci] else l.text.strip()
        table.append(slot)
    merged = []
    for row in table:
        if merged and not row[0].strip() and any(c.strip() for c in row[1:]):
            for i, c in enumerate(row):
                if c.strip():
                    merged[-1][i] = join_text(merged[-1][i], c)
            continue
        merged.append(row)
    return merged


def gap_before(prev, ln):
    return ln.y0 - prev.y1 if prev else 0.0


# ------------------------------------------------------------ ligature repair
# In preference order, and only the first one that exists is read. Unioning
# them measurably makes the repair worse: a bigger dictionary makes more
# fragments valid words on their own, and fix_ligatures' second guard then
# declines the join. Measured on one book: american alone 1,108 repairs and 7
# residual fragments, unioned with Webster's 2nd 994 and 11. The union is not
# the best of both lists; it is worse than either.
DICT_PATHS = (
    "/usr/share/dict/american-english",
    "/usr/share/dict/british-english",
    "/usr/share/dict/words",
)

_LIGWORDS = None
_LIGSOURCE = None


def _wordset():
    """The first word list that exists, never the union of several.

    Reading one named list rather than whatever happens to be installed is what
    makes a repaired book reproducible: two machines with different packages
    used to produce different output, and a regression diff reported that as a
    code change.
    """
    global _LIGWORDS, _LIGSOURCE
    if _LIGWORDS is None:
        _LIGWORDS, _LIGSOURCE = set(), None
        for p in DICT_PATHS:
            try:
                with open(p, errors="ignore") as fh:
                    _LIGWORDS = {x.strip().lower() for x in fh if x.strip()}
            except OSError:
                continue
            _LIGSOURCE = os.path.basename(p)
            break
    return _LIGWORDS


def dictionary_name() -> str | None:
    """Which word list the repair is using, or None. Recorded in front matter."""
    _wordset()
    return _LIGSOURCE


def has_dictionary() -> bool:
    """Whether a system word list was found.

    `fix_ligatures` cannot work without one and returns the text untouched,
    which is indistinguishable from a book that needed no repairs. The CLI
    checks this before accepting --fix-ligatures so the difference is never
    silent. On Debian and Ubuntu the list comes from `wamerican`.
    """
    return bool(_wordset())


# The break falls inside a word ("profi table"), so match a fragment that
# ends in an f-ligature followed by the rest of the word.
LIG_RE = re.compile(r"\b([A-Za-z]*(?:ffi|ffl|fi|fl|ff))\s+([a-z]{1,20})\b")


def fix_ligatures(text: str) -> tuple[str, int]:
    """Repair 'profi table' -> 'profitable', only when the join is a real word.

    Some PDFs emit an f-ligature as its own glyph run followed by a space.
    Two guards keep ordinary prose safe: the joined form must be in the
    dictionary, and the two fragments must not already both be words on their
    own (so "skated off ice" is never welded into "office").
    """
    words = _wordset()
    if not words:
        return text, 0
    n = 0

    def sub(m):
        nonlocal n
        a, b = m.group(1), m.group(2)
        joined = a + b
        if joined.lower() not in words:
            return m.group(0)
        if a.lower() in words and b.lower() in words:
            return m.group(0)  # both halves stand alone: leave it
        n += 1
        return joined

    return LIG_RE.sub(sub, text), n

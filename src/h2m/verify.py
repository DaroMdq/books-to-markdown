"""Does the Markdown still contain what the book said?

Structure is cheap to check and proves little. One book passed every structural
test in this repo while 6,000 words were missing: fences balanced, tables
square, links resolving, a word count that looked entirely reasonable. This
module is the other check — it reads the source and the output and asks how much
of the first survives in the second.

The comparison is deliberately blind to what the converter does on purpose. It
reflows wrapped lines, heals hyphenation across a line break, and repairs split
ligatures; all three move the spaces and none of them lose a letter. Both sides
are therefore reduced to a stream of letters and digits, with every space, hyphen
and mark of punctuation removed, before anything is compared. A word-level
comparison scores "port-\\nfolio" -> "portfolio" as a loss. This one does not.

What it will report as missing, correctly:
  - running heads and folios, which the converter removes on purpose
  - the index and the table of contents, dropped as navigation (N6)
  - anything the converter actually lost
The first two are the reason a real book never scores 100%, and the reason the
gap list matters more than the percentage: a gap you can read is a gap you can
judge.
"""

from __future__ import annotations

import glob
import html
import os
import posixpath
import re
import sys
import zipfile

KEEP = re.compile(r"[^a-z0-9]+")
# A running head is about 40 characters; a paragraph is several hundred. Gaps
# are split at this length because the two mean completely different things.
BIG = 300
# The window is long enough that an accidental match is unlikely and short
# enough that one altered character does not hide a whole paragraph.
WINDOW = 16


def normalise(text: str | None) -> str:
    """Letters and digits only, lowercased. Everything else goes.

    This single step is what makes reflowing, hyphenation healing and ligature
    repair invisible to the comparison rather than counted as loss.
    """
    return KEEP.sub("", (text or "").lower())


class Gap:
    """A stretch of source text with no counterpart in the output."""

    __slots__ = ("length", "offset", "sample")

    def __init__(self, offset, length, sample):
        self.offset = offset
        self.length = length
        self.sample = sample

    def __repr__(self):
        return "<Gap %d chars at %d %r>" % (self.length, self.offset, self.sample[:40])


class Result:
    """`gaps` is the longest few, for reading. `gap_count` is all of them."""

    __slots__ = (
        "big_chars",
        "big_gaps",
        "gap_count",
        "gaps",
        "missing_chars",
        "output_chars",
        "recovered",
        "source_chars",
    )

    def __init__(
        self,
        source_chars,
        output_chars,
        missing_chars,
        recovered,
        gaps,
        gap_count,
        big_gaps,
        big_chars,
    ):
        self.source_chars = source_chars
        self.output_chars = output_chars
        self.missing_chars = missing_chars
        self.recovered = recovered
        self.gaps = gaps
        self.gap_count = gap_count
        # A running head is ~40 characters and there is one per page, so a book
        # with the furniture stripped has hundreds of small gaps and that is
        # correct. A gap of 300+ characters is a paragraph, and no convention
        # removes paragraphs. Separating the two is what makes the number
        # readable: scattered furniture is expected, a big gap never is.
        self.big_gaps = big_gaps
        self.big_chars = big_chars


def _front_matter(path):
    with open(path) as fh:
        s = fh.read()
    if not s.startswith("---\n"):
        return ""
    end = s.find("\n---\n", 4)
    return s[4:end] if end != -1 else ""


def converted_units(outdir):
    """The EPUB documents the output says it came from.

    Read back out of each file's `source_file:` field rather than guessed. A
    document in the spine and not in this set was skipped, and the point of
    naming them is that "the index, on purpose" and "chapter 9, by accident"
    look identical in a percentage.
    """
    got = set()
    for f in sorted(glob.glob(os.path.join(outdir, "*.md"))):
        m = re.search(r'^source_file: "([^"]*)"', _front_matter(f), re.M)
        if m:
            got |= {x.strip() for x in m.group(1).split(",") if x.strip()}
    return got


def converted_pages(outdir):
    """The 1-based PDF pages the output says it covers, from `pdf_pages:`."""
    got = set()
    for f in sorted(glob.glob(os.path.join(outdir, "*.md"))):
        m = re.search(r'^pdf_pages: "(\d+)-(\d+)"', _front_matter(f), re.M)
        if m:
            got |= set(range(int(m.group(1)), int(m.group(2)) + 1))
    return got


def skipped_epub_documents(path, outdir):
    """[(name, chars)] for spine documents that produced no output, biggest first."""
    kept = converted_units(outdir)
    if not kept:
        return []
    out = []
    for name, text in _epub_documents(path):
        base = posixpath.basename(name)
        if base not in kept:
            n = len(normalise(text))
            if n:
                out.append((base, n))
    out.sort(key=lambda t: -t[1])
    return out


def skipped_pdf_pages(path, outdir):
    """(page_count, chars) for pages no chapter claims."""
    kept = converted_pages(outdir)
    if not kept:
        return 0, 0
    import pymupdf

    doc = pymupdf.open(path)
    pages = [i for i in range(doc.page_count) if (i + 1) not in kept]
    return len(pages), sum(len(normalise(doc[i].get_text())) for i in pages)


def source_pages(path):
    """Printed pages in the source, or 0 when it does not say.

    A PDF always knows. An EPUB knows only if it carries pagebreak markers —
    books set from an InDesign export usually do not, and guessing a page count
    from a character count would make the per-page figure meaningless.
    """
    if path.lower().endswith(".epub"):
        z = zipfile.ZipFile(path)
        n = 0
        for name in z.namelist():
            if name.endswith((".xhtml", ".html", ".htm")):
                n += len(
                    re.findall(r'epub:type="pagebreak"', z.read(name).decode("utf8", "replace"))
                )
        return n
    import pymupdf

    return pymupdf.open(path).page_count


def compare(source: str, output: str, window: int = WINDOW, limit: int = 25) -> Result:
    """How much of `source` survives in `output`, and where it does not.

    Both are normalised, then the source is walked in non-overlapping windows
    and each is looked up in the set of every window the output contains. The
    output index is built at stride 1 because the two texts are not aligned:
    the converter reorders chapters, drops running heads and adds page markers,
    so a source window may land anywhere.
    """
    src = normalise(source)
    out = normalise(output)
    if not src:
        return Result(0, len(out), 0, 1.0, [], 0, 0, 0)
    seen = {hash(out[i : i + window]) for i in range(max(0, len(out) - window + 1))}

    gaps, run_start = [], None
    for i in range(0, len(src) - window + 1, window):
        if hash(src[i : i + window]) in seen:
            if run_start is not None:
                gaps.append((run_start, i))
                run_start = None
        elif run_start is None:
            run_start = i
    if run_start is not None:
        gaps.append((run_start, len(src)))

    missing = sum(b - a for a, b in gaps)
    found = [Gap(a, b - a, src[a : a + 90]) for a, b in gaps]
    found.sort(key=lambda g: -g.length)
    big = [g for g in found if g.length >= BIG]
    return Result(
        len(src),
        len(out),
        missing,
        1.0 - missing / len(src),
        found[:limit],
        len(found),
        len(big),
        sum(g.length for g in big),
    )


# ----------------------------------------------------------------- sources
def pdf_text(path, first=0, last=None):
    import pymupdf

    doc = pymupdf.open(path)
    last = doc.page_count if last is None else last
    return "\n".join(doc[i].get_text() for i in range(first, min(last, doc.page_count)))


def _epub_documents(path):
    """[(archive name, plain text)] for every spine document, in spine order.

    Read from the spine rather than the archive so the order matches what the
    converter saw, and so files that are in the zip but not in the book — cover
    art, fonts, leftovers — are not counted as missing content.
    """

    z = zipfile.ZipFile(path)
    names = z.namelist()
    opf = next((n for n in names if n.endswith(".opf")), None)
    if opf is None:
        raise zipfile.BadZipFile("%s has no .opf package file" % path)
    raw = z.read(opf).decode("utf8", "replace")
    base = posixpath.dirname(opf)
    ids = dict(re.findall(r'<item\s[^>]*id="([^"]+)"[^>]*href="([^"]+)"', raw))
    ids.update({i: h for h, i in re.findall(r'<item\s[^>]*href="([^"]+)"[^>]*id="([^"]+)"', raw)})
    out = []
    for idref in re.findall(r'<itemref[^>]*idref="([^"]+)"', raw):
        href = ids.get(idref)
        if not href:
            continue
        p = posixpath.normpath(posixpath.join(base, href.split("#")[0]))
        if p not in names:
            continue
        s = z.read(p).decode("utf8", "replace")
        # Comments first: some publishers hide MathML in them; it is not visible text.
        s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
        s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
        # <head> is not the book. Its <title> is often a filename (InDesign
        # exports title every document after its file), and counting those as
        # missing content puts pure noise at the top of the gap list.
        s = re.sub(r"(?is)<head\b.*?</head>", " ", s)
        # An alt attribute is the figure's words; keep it, drop the rest of the tag.
        s = re.sub(r'<img\b[^>]*\balt="([^"]*)"[^>]*>', r" \1 ", s)
        # Character references are characters: "&#x2212;" is a minus sign, not
        # the letters "x2212" the comparison would otherwise look for.
        out.append((p, html.unescape(re.sub(r"<[^>]+>", " ", s))))
    return out


def epub_text(path):
    return "\n".join(t for _, t in _epub_documents(path))


def kept_source_text(path, outdir, whole=False, **kw):
    """The source text, restricted to what `outdir` says it converted.

    With `whole=True`, or when the output carries no provenance, this is the
    whole book. Otherwise it is exactly the EPUB documents named in
    `source_file:` or the PDF pages covered by `pdf_pages:` — which makes the
    recovery figure comparable between books instead of being dominated by how
    long each publisher's index happens to be.
    """
    if whole:
        return source_text(path, **kw)
    if path.lower().endswith(".epub"):
        kept = converted_units(outdir)
        if not kept:
            return epub_text(path)
        return "\n".join(t for n, t in _epub_documents(path) if posixpath.basename(n) in kept)
    kept = converted_pages(outdir)
    if not kept:
        return pdf_text(path, **kw)
    import pymupdf

    doc = pymupdf.open(path)
    return "\n".join(doc[i].get_text() for i in range(doc.page_count) if (i + 1) in kept)


def source_text(path, **kw):
    if path.lower().endswith(".epub"):
        return epub_text(path)
    return pdf_text(path, **kw)


def markdown_text(outdir):
    """The converted text, with the scaffolding the source never had removed."""
    parts = []
    for f in sorted(glob.glob(os.path.join(outdir, "*.md"))):
        with open(f) as fh:
            s = fh.read()
        # Front matter is metadata, per file — a document-wide regex would eat
        # everything between the first file's opening and the last file's close.
        if s.startswith("---\n"):
            end = s.find("\n---\n", 4)
            if end != -1:
                s = s[end + 5 :]
        s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)  # page markers
        # Keep the alt text, drop the path: the description came from the book,
        # the filename came from this converter.
        s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r" \1 ", s)
        parts.append(s)
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    """`h2m verify`: report how much of a book survives in its Markdown. Returns the exit code."""
    import argparse

    ap = argparse.ArgumentParser(
        prog="h2m verify",
        description="Compare a converted directory against the book it came from.",
    )
    ap.add_argument("source", help="the .pdf or .epub the Markdown was made from")
    ap.add_argument("outdir", help="the directory of converted .md files")
    ap.add_argument(
        "--gaps", type=int, default=8, help="how many of the longest gaps to print (0 for none)"
    )
    ap.add_argument(
        "--window",
        type=int,
        default=WINDOW,
        help="comparison window in characters (default: %d)" % WINDOW,
    )
    ap.add_argument(
        "--whole-book",
        action="store_true",
        help="compare against every page and document, including the "
        "index and the table of contents the converter drops",
    )
    a = ap.parse_args(argv)

    if not glob.glob(os.path.join(a.outdir, "*.md")):
        # Otherwise a mistyped path reads as "0% recovered".
        sys.stderr.write("h2m verify: no .md files in %s\n" % a.outdir)
        return 1
    out_text = markdown_text(a.outdir)
    r = compare(kept_source_text(a.source, a.outdir, whole=a.whole_book), out_text, window=a.window)
    pages = source_pages(a.source)
    print(
        "%s  ->  %s%s"
        % (os.path.basename(a.source), a.outdir, "   (whole book)" if a.whole_book else "")
    )
    print(
        "  source %s chars, output %s chars"
        % (format(r.source_chars, ","), format(r.output_chars, ","))
    )
    print(
        "  recovered %.2f%%   missing %s chars in %d gaps"
        % (r.recovered * 100, format(r.missing_chars, ","), r.gap_count)
    )
    # The headline number counts the running heads and folios the converter
    # removes on purpose — one gap per page — so no real book reaches 100%.
    # This second line is the one to read.
    print(
        "  gaps of %d+ chars: %d, totalling %s (%.2f%% of the source)"
        % (BIG, r.big_gaps, format(r.big_chars, ","), 100.0 * r.big_chars / max(r.source_chars, 1))
    )
    if pages:
        # The signal for the failure this tool exists for. A converter eating
        # the top line of every page does not leave one big hole; it leaves one
        # small one per page, so neither the percentage nor the big-gap count
        # moves much. Per page, it doubles. Compare against the length of one
        # line — roughly 60 to 80 characters once the spaces are gone — and
        # against the reading guide in the README.
        print(
            "  %d printed pages, %.0f chars missing per page  (one running "
            "head is ~40-60; two lines' worth means body text is going)"
            % (pages, r.missing_chars / pages)
        )
    # Name what the converter never claimed to convert. Without this the index
    # and the table of contents — dropped as navigation on purpose — read as
    # tens of thousands of characters of lost book.
    if a.source.lower().endswith(".epub"):
        skipped = skipped_epub_documents(a.source, a.outdir)
        if skipped:
            total = sum(n for _, n in skipped)
            print(
                "  %d source documents produced no output, %s chars (%.2f%% of "
                "the source):"
                % (len(skipped), format(total, ","), 100.0 * total / max(r.source_chars, 1))
            )
            for name, n in skipped[:6]:
                print("    %-24s %8s chars" % (name, format(n, ",")))
            print(
                "    a chapter in that list is a bug; an index or a contents page is "
                "dropped on purpose"
            )
    else:
        npages, nchars = skipped_pdf_pages(a.source, a.outdir)
        if npages:
            print(
                "  %d pages lie outside every chapter's range, %s chars (%.2f%%)"
                " — front and back matter the outline does not cover"
                % (npages, format(nchars, ","), 100.0 * nchars / max(r.source_chars, 1))
            )
    if a.gaps and r.gaps:
        print("  longest gaps — read them before calling any of this a loss:")
        for g in r.gaps[: a.gaps]:
            print("    %6d chars  %s…" % (g.length, g.sample[:72]))
    return 0

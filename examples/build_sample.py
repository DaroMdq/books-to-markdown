"""Build examples/field-guide.epub, the bundled sample book.

    python examples/build_sample.py

The text is original and written for this repository. It is small on purpose,
but it carries the shapes the converter exists for: a heading hierarchy, page
break markers, a table, a code listing, MathML (display and inline), a
footnote, a block quote, and a contents page that is dropped as navigation.

The archive is written with fixed timestamps so that rebuilding it produces
the same bytes; `tests/test_examples.py` checks that, and that converting it
reproduces the committed Markdown in `examples/output/`.
"""

from __future__ import annotations

import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "field-guide.epub")

TITLE = "A Field Guide to Plain Text"
AUTHOR = "Sample Author"
IDENTIFIER = "urn:uuid:5b0a6c1e-0000-4000-8000-000000000001"

XHTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>%s</title></head>
<body>
%s
</body>
</html>
"""

MATH = 'xmlns="http://www.w3.org/1998/Math/MathML"'


def page(n: int) -> str:
    return '<span epub:type="pagebreak" id="page%d" title="%d"/>' % (n, n)


CONTENTS = """<h1>Contents</h1>
<p>Chapter 1: Text Is Not Text</p>
<p>Chapter 2: Measuring What Survives</p>
<p>Chapter 3: Keeping the Page</p>
<p>This page lists the chapters of the guide and links to each of them. It is
navigation rather than content, so a converter should leave it out.</p>
"""

CHAPTER_1 = (
    "<h1>"
    + page(1)
    + """Chapter 1: Text Is Not Text</h1>
<p>A book on a screen looks like text. Underneath, it rarely is. A PDF stores
glyphs at coordinates and has no idea where a paragraph begins. An EPUB stores
markup, but each publishing tool writes its own dialect of it, and the dialect
decides what a program can recover.</p>
<h2>Three kinds of source</h2>
<p>Most technical books arrive in one of three shapes. Each one hides its
structure in a different place.</p>
<table>
<tr><th>Source</th><th>Where structure lives</th><th>Typical trap</th></tr>
<tr><td>Publisher EPUB</td><td>Tags and class names</td><td>Formulas shipped as images</td></tr>
<tr><td>Typeset PDF</td><td>Font sizes and positions</td><td>Running heads mixed into the text</td></tr>
<tr><td>PDF-derived EPUB</td><td>Almost nowhere</td><td>Every section is a top-level heading</td></tr>
</table>
<h2>What a reader needs</h2>
<p>A person skims past a running head without noticing it. A language model
does not: it reads the header on every page as part of the argument. The job
of a converter is to keep what the author wrote and drop what the layout
added, and to say so when it cannot tell the two apart.</p>
"""
    + page(2)
    + """
<h3>A note on headings</h3>
<p>Headings carry the outline of the book. When they are lost, a chapter
becomes one long paragraph and the reader loses the map along with it.</p>
"""
)

CHAPTER_2 = (
    "<h1>"
    + page(3)
    + """Chapter 2: Measuring What Survives</h1>
<p>A conversion that looks right can still be short. The only way to know is
to compare the output against the source, character by character, after
removing everything that is allowed to change.</p>
<h2>The recovery figure</h2>
<p>Write <math %s><mi>S</mi></math> for the number of letters and digits in the
source and <math %s><mi>M</mi></math> for the number that have no counterpart
in the output. The recovery figure is then</p>
<math %s display="block"><mi>R</mi><mo>=</mo><mn>1</mn><mo>&#x2212;</mo>
<mfrac><mi>M</mi><mi>S</mi></mfrac></math>
<p>and it is a band rather than a grade, because page numbers and running
heads are removed on purpose and count as missing.</p>
"""
    % (MATH, MATH, MATH)
    + page(4)
    + """
<h2>Normalising both sides</h2>
<p>Reflowing a paragraph moves spaces; healing a hyphenated word removes a
hyphen. Neither loses a letter, so both sides are reduced to letters and
digits before they are compared:</p>
<pre>import re

def normalise(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())</pre>
<p>A gap of a few characters per page is a running head. A gap the size of a
paragraph is a bug.</p>
"""
)

CHAPTER_3 = (
    "<h1>"
    + page(5)
    + """Chapter 3: Keeping the Page</h1>
<p>A citation points at a printed page. If the page numbers are thrown away
during conversion, every quotation taken from the output becomes impossible to
check against the book.<a epub:type="noteref" href="#note1">1</a></p>
<h2>Markers that cost nothing</h2>
<p>Each page break becomes an HTML comment. It is invisible when the Markdown
is rendered and easy to find with a search when a passage needs a page.</p>
<blockquote><p>Keep what the author wrote. Drop what the layout added. Say so
when you cannot tell the difference.</p></blockquote>
<h2>Checklist</h2>
<ul>
<li>Convert the book.</li>
<li>Run the verifier against the source.</li>
<li>Read the longest gaps before trusting the percentage.</li>
</ul>
"""
    + page(6)
    + """
<aside epub:type="footnote" id="note1"><p>1. Some sources carry no page
markers at all. For those, the output simply has none, and the verifier says
so instead of inventing them.</p></aside>
"""
)

DOCS = [
    ("contents.xhtml", "Contents", CONTENTS),
    ("chapter01.xhtml", "Chapter 1", CHAPTER_1),
    ("chapter02.xhtml", "Chapter 2", CHAPTER_2),
    ("chapter03.xhtml", "Chapter 3", CHAPTER_3),
]

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""


def opf() -> str:
    items = "\n".join(
        '    <item id="d%d" href="%s" media-type="application/xhtml+xml"/>' % (i, name)
        for i, (name, _, _) in enumerate(DOCS)
    )
    spine = "\n".join('    <itemref idref="d%d"/>' % i for i in range(len(DOCS)))
    return """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>%s</dc:title>
    <dc:creator>%s</dc:creator>
    <dc:identifier id="id">%s</dc:identifier>
    <dc:language>en</dc:language>
    <dc:date>2026-01-01</dc:date>
  </metadata>
  <manifest>
%s
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
%s
  </spine>
</package>
""" % (TITLE, AUTHOR, IDENTIFIER, items, spine)


def ncx() -> str:
    points = "\n".join(
        '    <navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
        '<content src="%s"/></navPoint>' % (i, i + 1, label, name)
        for i, (name, label, _) in enumerate(DOCS)
    )
    return """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head/>
  <docTitle><text>%s</text></docTitle>
  <navMap>
%s
  </navMap>
</ncx>
""" % (TITLE, points)


def write(z: zipfile.ZipFile, name: str, data: str) -> None:
    # A fixed timestamp and no compression keep the archive byte-identical
    # across rebuilds and across zlib builds.
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o644 << 16
    z.writestr(info, data)


def build(path: str = TARGET) -> str:
    """Write the sample EPUB to `path` and return the path."""
    with zipfile.ZipFile(path, "w") as z:
        # The mimetype entry must come first and be stored uncompressed (OCF spec).
        write(z, "mimetype", "application/epub+zip")
        write(z, "META-INF/container.xml", CONTAINER)
        write(z, "OEBPS/content.opf", opf())
        write(z, "OEBPS/toc.ncx", ncx())
        for name, title, body in DOCS:
            write(z, "OEBPS/" + name, XHTML % (title, body))
    return path


if __name__ == "__main__":
    print(build())

"""Synthetic books.

No fixture in this suite is a real book. Every EPUB and PDF here is built from
scratch, in the *shape* a publisher emits — MathML commented out beside an
equation image, code shipped as `div.ProgramCode`, a running head repeated on
every page, a folio in the outer margin. That keeps the suite runnable by anyone
(real books are copyrighted and cannot be committed) and, more usefully, makes each fixture say out loud
which publisher convention it stands for.

The cost is real and worth stating: a synthetic fixture proves the converter
handles the convention as understood, not as a real book actually ships it.
Real books are the other half of the evidence, and they stay outside the repo.
"""

from __future__ import annotations

import zipfile

import pymupdf
import pytest

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

XHTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>%s</title></head><body>%s</body></html>"""


def make_epub(
    path, docs, title="A Book", author="A Writer", identifier="urn:isbn:9780000000000", labels=None
):
    """Build an EPUB from [(filename, doc_title, body_html), ...].

    `labels` supplies NCX navLabels when they should differ from <title> —
    the InDesign case, where <title> is a meaningless filename.
    """
    ids = ["d%d" % i for i in range(len(docs))]
    manifest = "\n".join(
        '<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (i, d[0])
        for i, d in zip(ids, docs)
    )
    spine = "\n".join('<itemref idref="%s"/>' % i for i in ids)
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>%s</dc:title><dc:creator>%s</dc:creator>
<dc:identifier id="id">%s</dc:identifier><dc:language>en</dc:language>
<dc:date>2024-01-01</dc:date></metadata>
<manifest>%s
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>
<spine toc="ncx">%s</spine></package>""" % (title, author, identifier, manifest, spine)

    points = "\n".join(
        '<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
        '<content src="%s"/></navPoint>' % (n, n + 1, (labels or {}).get(d[0], d[1]), d[0])
        for n, d in enumerate(docs)
    )
    ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head/><docTitle><text>%s</text></docTitle><navMap>%s</navMap></ncx>""" % (title, points)

    with zipfile.ZipFile(path, "w") as z:
        # mimetype must be first and stored, per the OCF spec.
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/toc.ncx", ncx)
        for name, doc_title, body in docs:
            z.writestr("OEBPS/" + name, XHTML % (doc_title, body))
    return str(path)


def make_pdf(
    path,
    pages,
    toc=None,
    head=None,
    folio_from=1,
    body_size=11.0,
    head_size=9.0,
    top=60,
    leading=14,
    folio_x=None,
    folio_y=760,
    folio=True,
    folio_suffix="",
):
    """Build a text PDF from a list of pages.

    Each page is a list of (text, kwargs) where kwargs may set `size`, `font`,
    `x`, `dy` (extra space before the line). `head` is a running head drawn on
    every page at y=30; `folio_from` numbers the printed pages.
    """
    doc = pymupdf.open()
    for n, lines in enumerate(pages):
        page = doc.new_page(width=612, height=792)
        if head:
            page.insert_text((72, 30), head, fontname="helv", fontsize=head_size)
        y = top
        for text, kw in lines:
            y += kw.get("dy", 0)
            if kw.get("rotate"):
                # A line printed sideways. `rotate=90` gives dir (0, -1), which
                # is how a wide table is set when the publisher turns it to fit
                # the page rather than shrinking it — and also how some books set
                # their running heads, which is why the two have to be told apart
                # by how much of the page is rotated rather than by direction.
                page.insert_text(
                    (kw.get("x", 72), kw.get("y", y)),
                    text,
                    fontname=kw.get("font", "helv"),
                    fontsize=kw.get("size", body_size),
                    rotate=kw["rotate"],
                )
            else:
                # `y` pins a line to an absolute height, for a fixture that
                # needs something at the foot of the page rather than after
                # whatever came before it.
                page.insert_text(
                    (kw.get("x", 72), kw.get("y", y)),
                    text,
                    fontname=kw.get("font", "helv"),
                    fontsize=kw.get("size", body_size),
                )
            y += kw.get("leading", leading)
        # The folio sits outside the text column — the shape some typeset PDFs
        # use, where it rides in the outer margin rather than under the text block.
        # `folio=False` leaves it off entirely, for a book that sets the page
        # number inside its running head instead of on a line of its own.
        if folio:
            # `folio_suffix` hangs an unmapped glyph off the number, the way
            # one real typesetter does on every verso page.
            page.insert_text(
                (folio_x if folio_x is not None else 300, folio_y),
                str(folio_from + n) + folio_suffix,
                fontname="helv",
                fontsize=9,
            )
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return str(path)


def add_separation_image(path, rect=(72, 500, 172, 600)):
    """Draw one `Separation(…, Black)` image onto page 1 of an existing PDF.

    A shape real books ship: one stored 49 of its charts in a Separation
    colorspace, which has **one** component — exactly like DeviceGray — but is
    not gray, and PNG cannot represent it. Component count therefore cannot
    tell the two apart, which is the whole point of this fixture.

    Built by inserting an ordinary grey image and then repointing its
    `/ColorSpace` at a Separation array. The samples stay valid: one component
    at 8 bits either way.
    """
    doc = pymupdf.open(path)
    pix = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 8, 8), False)
    # 230, not a mid grey. The Separation function below is C0=[1] C1=[0], so
    # the tint transform *inverts*: a high sample is a dark figure. It has to
    # land dark, or the ink rule reads it as a background panel and drops it
    # before the colorspace this fixture exists to test is ever reached.
    pix.set_rect(pix.irect, (230,))
    doc[0].insert_image(pymupdf.Rect(*rect), pixmap=pix)
    doc.save(path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    doc.close()

    doc = pymupdf.open(path)
    xref = doc[0].get_images(full=True)[0][0]
    fn = doc.get_new_xref()
    doc.update_object(fn, "<</FunctionType 2/Domain[0 1]/C0[1]/C1[0]/N 1>>")
    cs = doc.get_new_xref()
    doc.update_object(cs, "[/Separation/Black/DeviceGray %d 0 R]" % fn)
    doc.xref_set_key(xref, "ColorSpace", "%d 0 R" % cs)
    doc.save(path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    doc.close()
    return path


def add_flat_image(path, tone=180, page=0, rect=(72, 400, 272, 500)):
    """Draw one flat, ink-free rectangle onto a page of an existing PDF.

    A shape real books ship often: a publisher lays a tinted panel behind a
    chart, and `get_images` hands that panel back exactly as it hands back the
    chart. Every one was written to disk and referenced from the Markdown as a
    picture showing nothing.

    `tone` is the grey level. Anything above the ink threshold is a fill; pass
    something dark to build the counter-case.
    """
    doc = pymupdf.open(path)
    pix = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 16, 16), False)
    pix.set_rect(pix.irect, (tone,))
    doc[page].insert_image(pymupdf.Rect(*rect), pixmap=pix)
    doc.save(path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    doc.close()
    return path


def read(path):
    """Read a converted file. A helper so no test leaks a file handle."""
    with open(path) as fh:
        return fh.read()


@pytest.fixture
def epub(tmp_path):
    def build(docs, **kw):
        return make_epub(tmp_path / "book.epub", docs, **kw)

    return build


@pytest.fixture
def pdf(tmp_path):
    def build(pages, **kw):
        return make_pdf(tmp_path / "book.pdf", pages, **kw)

    return build

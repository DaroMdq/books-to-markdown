"""PDF -> Markdown + YAML front-matter, split into chapters by the PDF outline.

    h2m pdf BOOK.pdf -o OUT [--slug NAME] [--first N] [--last N]

Structure is inferred, not read: see `h2m.layout.Profile` for how the body
size, running-head bands, leading and paragraph gap are measured off the
document.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata

import pymupdf

from h2m.layout import (
    Profile,
    as_table,
    dictionary_name,
    fix_ligatures,
    has_dictionary,
    inline_markup,
    is_bullet,
    is_mono,
    join_text,
    leading_symbol,
    merge_dropcap,
    page_lines,
)


def slugify(s, maxlen=60):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:maxlen].strip("-") or "untitled"


def yaml_str(v):
    v = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % re.sub(r"\s+", " ", v).strip()


class Doc:
    def __init__(self, path, first=0, last=None):
        self.doc = pymupdf.open(path)
        self.path = path
        self.first = first
        self.last = last if last is not None else self.doc.page_count
        self.prof = Profile(self.doc, range(first, min(self.last, first + 250)))
        # One xref can be placed on fifty pages; read its samples once.
        self.ink = {}

    # -- one page -> list of ("kind", payload) ---------------------------
    def page_blocks(self, i):
        prof = self.prof
        lines, folio = page_lines(self.doc, i, prof)
        lines = merge_dropcap(lines, prof)
        out = []
        if folio:
            out.append(("folio", folio))

        # Split the page into runs of similar font size, so a table set in a
        # different face is handled apart from the prose around it.
        runs, cur = [], []
        for ln in lines:
            if cur and abs(cur[-1].size - ln.size) > 0.6:
                runs.append(cur)
                cur = []
            cur.append(ln)
        if cur:
            runs.append(cur)

        # Images sit between the text runs; place them by vertical position.
        imgs, seen = [], set()
        try:
            for im in self.doc[i].get_images(full=True):
                for r in self.doc[i].get_image_rects(im[0]):
                    if r.width < 40 or r.height < 18:
                        continue  # rules, bullets, printer marks
                    if im[0] in seen:
                        continue  # one xref can have several rects
                    seen.add(im[0])
                    if not has_ink(self.doc, im[0], self.ink):
                        continue  # a background panel, not a picture
                    imgs.append((r.y0, im[0], r.width, r.height))
        except Exception:
            pass
        imgs.sort()

        def flush_images(upto):
            while imgs and imgs[0][0] <= upto:
                _y, xref, w, h = imgs.pop(0)
                kind = "code/equation strip" if (h < 160 and w > 150) else "figure"
                out.append(("image", (xref, kind, i)))

        for run in runs:
            flush_images(run[0].y0)
            if is_mono(run[0]) and all(is_mono(l) for l in run):
                out.append(("code", self.code_run(run)))
                continue
            if len(run) <= 3 and leading_symbol(run[0]):
                txt = " ".join(l.text for l in run)
                txt = re.sub(r"^[^\w(]+", "", txt).strip()
                if txt:
                    out.append(("h2", re.sub(r"\s+", " ", txt)))
                continue
            lvl = prof.heading_level(run[0])
            if lvl and len(run) <= 3 and all(prof.heading_level(l) for l in run):
                txt = " ".join(l.text.strip() for l in run)
                out.append(("h%d" % lvl, re.sub(r"\s+", " ", txt)))
                continue
            if abs(run[0].size - prof.body_size) > 0.6 and len(run) >= 4:
                tbl = as_table(run, prof)
                if tbl and len(tbl) >= 2:
                    out.append(("table", tbl))
                    continue
            out.extend(self.flow(run, prof))
        flush_images(float("inf"))
        return out

    def code_run(self, lines):
        """Monospaced lines -> source text, indentation rebuilt from x."""
        base = min(l.x0 for l in lines)
        cw = max(lines[0].size * 0.6, 1.0)  # Courier advance width
        out = []
        for l in lines:
            pad = round((l.x0 - base) / cw)
            out.append(" " * max(0, pad) + l.text.rstrip())
        while out and not out[0].strip():
            out.pop(0)
        while out and not out[-1].strip():
            out.pop()
        return "\n".join(out)

    def flow(self, lines, prof):
        """Reflow wrapped lines into paragraphs and list items."""
        out, buf, prev = [], "", None
        indent0 = min((l.x0 for l in lines), default=0)
        for ln in lines:
            txt = inline_markup(ln, prof).strip()
            if not txt:
                continue
            newpara = False
            if prev is not None:
                gap = ln.y0 - prev.y1
                if gap > prof.leading * 0.55:
                    newpara = True
                if ln.x0 > indent0 + 9 and not is_bullet(txt):
                    newpara = newpara or gap > prof.leading * 0.3
                if is_bullet(txt):
                    newpara = True
            if newpara and buf:
                out.append(("p", buf))
                buf = ""
            buf = join_text(buf, txt) if buf else txt
            prev = ln
        if buf:
            out.append(("p", buf))
        return out

    # -- whole document ---------------------------------------------------
    def chapters(self):
        """Split on the PDF outline; fall back to one chunk per 30 pages."""
        toc = [t for t in self.doc.get_toc() if self.first < t[2] <= self.last]
        span = max(self.last - self.first, 1)
        # Books nest their outline differently: some put chapters at level 1,
        # others at level 2 under parts. Take the deepest level that still
        # yields chapter-sized units rather than fragments.
        depth = 1
        for d in (1, 2, 3):
            n = len([t for t in toc if t[0] <= d])
            if n and span / n >= 8:
                depth = d
        marks = []
        for lvl, title, pg in toc:
            if lvl <= depth:
                marks.append((pg - 1, title.strip(), lvl))
        marks.sort()
        if not marks:
            return [(self.first, self.last, "Document", 1)]
        out = []
        for n, (pg, title, lvl) in enumerate(marks):
            end = marks[n + 1][0] if n + 1 < len(marks) else self.last
            if end > pg:
                out.append((pg, end, title, lvl))
        return out


CODE_LANG = [""]
IMAGES = []

# A page is layered, and a publisher lays a tinted panel behind a chart.
# `get_images` hands that panel back exactly as it hands back the chart, so in
# the corpus this was developed against 161 of them were written to disk and
# referenced from the Markdown as pictures showing nothing, a third of
# everything one book extracted.
#
# Measured, not chosen: no pixel in any of the 161 is darker than 120 of 255,
# while the faintest real figure in the same corpus reaches 93. The reading has
# to be taken in **grayscale**, because a CMYK image stores 0 as *no ink* — the
# inverse of what that byte means anywhere else — and one book's charts were
# all CMYK, which is why a first pass called none of its panels blank.
#
# It also removes two publisher logos, orange on white and so mid-grey once the
# colour is gone. That is consistent rather than collateral: a logo is brand
# furniture on a front-matter page, the same class of thing as the running head
# this converter already drops.
#
# The conversion is unconditional, and skipping it when the pixmap already has
# one component would be the same bug that once hid 49 charts in one book: a
# Separation pixmap has one component too, and its tint transform *inverts* the
# byte, so a dark figure reads as a pale panel. Component count never says what
# a sample means. `test_an_image_png_cannot_represent_is_still_written_to_disk`
# catches it, and did.
INK_MAX = 120


def has_ink(doc, xref, cache):
    """Does this image draw anything a reader could see?

    An image that cannot be read at all counts as ink: unreadable and blank are
    different, and only one of them is safe to throw away.
    """
    if xref not in cache:
        try:
            pix = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.Pixmap(doc, xref))
            if pix.alpha:
                pix = pymupdf.Pixmap(pix, 0)
            cache[xref] = min(pix.samples) <= INK_MAX
        except Exception:
            cache[xref] = True
    return cache[xref]


def render(blocks):
    md, pages = [], []
    for kind, val in blocks:
        if kind == "folio":
            pages.append(val)
            md.append("<!-- page %s -->" % val)
        elif kind == "table":
            w = max(len(r) for r in val)
            rows = [r + [""] * (w - len(r)) for r in val]
            cells = lambda r: "| " + " | ".join(c.replace("|", "\\|").strip() for c in r) + " |"
            md.append(
                "\n".join(
                    [cells(rows[0]), "| " + " | ".join("---" for _ in range(w)) + " |"]
                    + [cells(r) for r in rows[1:]]
                )
            )
        elif kind == "image":
            xref, ikind, pg = val
            # Name by xref alone: one image reused on several pages must map
            # to a single file, or later references dangle.
            name = "x%d.png" % xref
            IMAGES.append((xref, name))
            md.append("![%s from page %d](images/%s)" % (ikind, pg + 1, name))
        elif kind == "code":
            if val.strip():
                fence = "```" if "```" not in val else "~~~"
                md.append("%s%s\n%s\n%s" % (fence, CODE_LANG[0], val, fence))
        elif kind.startswith("h"):
            md.append("#" * int(kind[1:]) + " " + val)
        else:
            md.append(val)
    text = "\n\n".join(m for m in md if m and m.strip())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, pages


def main(argv: list[str] | None = None) -> int:
    """`h2m pdf`: convert one PDF into per-chapter Markdown files. Returns the exit code."""
    ap = argparse.ArgumentParser(prog="h2m pdf")
    ap.add_argument("pdf", help="the .pdf file to convert")
    ap.add_argument("-o", "--out", required=True, help="output root; files land in OUT/SLUG/")
    ap.add_argument("--slug", default=None, help="output subdirectory; defaults to the filename")
    ap.add_argument("--first", type=int, default=0, help="0-based first page (default: 0)")
    ap.add_argument(
        "--last",
        type=int,
        default=None,
        help="0-based page to stop before (exclusive; default: the end)",
    )
    ap.add_argument("--limit", type=int, default=0, help="only the first N chapters")
    ap.add_argument("--code-lang", default="", help="tag for fenced code blocks")
    ap.add_argument("--images", action="store_true", help="extract figures")
    ap.add_argument(
        "--max-px",
        type=int,
        default=1400,
        help="downscale extracted figures to this longest edge; 0 = full size",
    )
    ap.add_argument(
        "--fix-ligatures",
        action="store_true",
        help="repair 'fi nd' / 'profi table' split-ligature damage",
    )
    a = ap.parse_args(argv)
    # IMAGES is module-level state. Clear it so a second conversion in the same
    # process (the test suite runs many) does not inherit the previous book's
    # figures and write them into this book's directory.
    IMAGES.clear()

    if a.fix_ligatures and not has_dictionary():
        sys.stderr.write(
            "h2m: --fix-ligatures needs a system word list and none was found.\n"
            "     Without it the repair does nothing and reports zero repairs,\n"
            "     which is indistinguishable from a book that needed none.\n"
            "     Install one (Debian/Ubuntu: sudo apt install wamerican).\n"
        )
        return 2

    CODE_LANG[0] = a.code_lang
    D = Doc(a.pdf, a.first, a.last)
    slug = a.slug or slugify(os.path.splitext(os.path.basename(a.pdf))[0])
    outdir = os.path.join(a.out, slug)
    os.makedirs(outdir, exist_ok=True)

    meta = D.doc.metadata or {}
    btitle = meta.get("title") or os.path.basename(a.pdf)
    author = meta.get("author") or ""

    chaps = D.chapters()
    if a.limit:
        chaps = chaps[: a.limit]
    pad = max(2, len(str(len(chaps))))
    total = dict(w=0, t=0)
    ligtotal = [0]
    for n, (start, end, title, _lvl) in enumerate(chaps):
        chapter_lig = 0
        blocks = []
        for i in range(start, end):
            blocks.extend(D.page_blocks(i))
        md, pages = render(blocks)
        if a.fix_ligatures:
            # Never inside code — a fence may legitimately contain "ff x".
            fences = []
            # B023: the lambda closes over this iteration's `fences`, which is
            # correct — re.sub runs to completion before the loop moves on.
            md = re.sub(
                r"(?ms)^(```|~~~).*?^\1[ \t]*$",
                lambda m: (
                    fences.append(m.group(0)),  # noqa: B023
                    "\x01F%d\x01" % (len(fences) - 1),  # noqa: B023
                )[1],
                md,
            )
            md, chapter_lig = fix_ligatures(md)
            md = re.sub(r"\x01F(\d+)\x01", lambda m: fences[int(m.group(1))], md)  # noqa: B023
            ligtotal[0] += chapter_lig
        if len(md.split()) < 30:
            continue
        cnum = None
        m = re.match(r"Chapter\s+([A-Za-z]+|\d+)[.\s]", title)
        if m:
            from h2m.epub import spelled_number

            cnum = int(m.group(1)) if m.group(1).isdigit() else spelled_number(m.group(1))
        ntab = md.count("\n| --- ")
        fm = [
            "---",
            "book: %s" % yaml_str(btitle),
            "author: %s" % yaml_str(author),
            "chapter: %s" % (cnum if cnum is not None else "null"),
            "title: %s" % yaml_str(title),
            "source_pdf: %s" % yaml_str(os.path.basename(a.pdf)),
            "pdf_pages: %s" % yaml_str("%d-%d" % (start + 1, end)),
            "printed_pages: %s" % yaml_str("%s-%s" % (pages[0], pages[-1]) if pages else ""),
            "words: %d" % len(md.split()),
            "tables: %d" % ntab,
        ]
        if a.fix_ligatures:
            # Name the word list. The repair depends on which one the machine
            # has, so a chapter that does not say cannot be reproduced or
            # compared against another machine.
            fm += [
                "ligature_dictionary: %s" % yaml_str(dictionary_name() or ""),
                "ligatures_repaired: %d" % chapter_lig,
            ]
        fm += ["---", ""]
        fname = "%0*d_%s.md" % (pad, n, slugify(title, 48))
        with open(os.path.join(outdir, fname), "w") as fh:
            # The page usually carries the chapter title already; only add
            # one when the detected heading does not match.
            first_h = re.match(r"\s*(?:<!--[^>]*-->\s*)?#\s+(.+)", md)
            norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
            fh_norm = norm(first_h.group(1)) if first_h else ""
            t_norm = norm(title)
            same = fh_norm and (fh_norm == t_norm or fh_norm in t_norm or t_norm in fh_norm)
            head = "" if same else "# " + title + "\n\n"
            fh.write("\n".join(fm) + head + md + "\n")
        total["w"] += len(md.split())
        total["t"] += ntab
        print(
            "  %-46s %7d words  %3d tbl  pp.%s"
            % (
                fname[:46],
                len(md.split()),
                ntab,
                ("%s-%s" % (pages[0], pages[-1])) if pages else "-",
            )
        )
    if a.images and IMAGES:
        import io

        dest = os.path.join(outdir, "images")
        os.makedirs(dest, exist_ok=True)
        nb = written = 0
        for xref, name in sorted(set(IMAGES)):
            try:
                pix = pymupdf.Pixmap(D.doc, xref)
                try:
                    data = pix.tobytes("png")
                except Exception:
                    # PNG takes gray or RGB and nothing else. CMYK is the
                    # obvious case, but a Separation pixmap carries ONE
                    # component — indistinguishable from DeviceGray by width,
                    # which is how a whole book's charts got past a guard that
                    # asked `pix.n - pix.alpha >= 4`. Ask the writer whether it
                    # can take the pixmap instead of guessing from its shape.
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    data = pix.tobytes("png")
                try:
                    from PIL import Image

                    im = Image.open(io.BytesIO(data))
                    if max(im.size) > a.max_px:
                        im.thumbnail((a.max_px, a.max_px), Image.LANCZOS)
                    buf = io.BytesIO()
                    rgb = im.convert("RGB")
                    cols = rgb.getcolors(maxcolors=8192)
                    if cols is not None:
                        rgb.convert("P", palette=Image.ADAPTIVE, colors=256).save(
                            buf, "PNG", optimize=True
                        )
                    else:
                        rgb.save(buf, "JPEG", quality=85, optimize=True)
                    if 0 < buf.tell() < len(data):
                        data = buf.getvalue()
                except Exception:
                    pass
                with open(os.path.join(dest, name), "wb") as fh:
                    fh.write(data)
                nb += len(data)
                written += 1
            except Exception:
                pass
        print("images: %d of %d extracted (%.1f MB)" % (written, len(set(IMAGES)), nb / 1e6))

    print(
        "\n-> %s   %d words, %d tables%s"
        % (
            outdir,
            total["w"],
            total["t"],
            ", %d ligatures repaired" % ligtotal[0] if ligtotal[0] else "",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

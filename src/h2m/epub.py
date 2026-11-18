"""EPUB -> Markdown + YAML front-matter, one file per spine document.

Built around the conventions publisher EPUBs actually use (MathML hidden in
HTML comments, code shipped as nested divs, InDesign exports with no heading
tags) and written to degrade gracefully: anything it does not recognise falls
through to its text rather than vanishing.

    h2m epub BOOK.epub -o OUT [--slug NAME] [--limit N]
"""

from __future__ import annotations

import argparse
import html
import os
import posixpath
import re
import unicodedata
import warnings
import zipfile

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

try:
    from bs4 import XMLParsedAsHTMLWarning

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    pass

from h2m.mathml import mathml_to_latex

MATH_RE = re.compile(r"<math\b.*?</math>", re.S | re.I)
# Some publishers ship a PNG of each equation and comment the MathML out beside it.
# Unwrapping the comment turns a picture back into real LaTeX.
COMMENTED_MATH_RE = re.compile(r"<!--\s*(<math\b.*?</math>)\s*-->", re.S | re.I)
BLOCK = {
    "p",
    "div",
    "section",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "tr",
    "table",
    "figure",
    "figcaption",
    "blockquote",
    "pre",
    "ul",
    "ol",
    "dl",
    "dt",
    "dd",
    "aside",
    "header",
    "footer",
    "hr",
    "br",
}
SKIP = {"script", "style", "head", "nav"}
# Some publishers ship code as nested divs rather than <pre>, and mark inline
# monospace with a class instead of <code>.
PRE_CLASSES = ("programcode", "codeblock", "listing")
LINE_CLASSES = ("fixedline",)
MONO_CLASSES = ("emphasisfontcategorynonproportional", "emphasistypemonospace")
ITALIC_CLASSES = ("emphasistypeitalic", "emphasis", "italic")
# InDesign exports style paragraphs instead of using <h1>..<h6>.
HEADING_CLASS_RE = re.compile(r"^(?:heading|head|title|hd)-?(\d)$")
TOP_HEADING_CLASSES = (
    "strategy-title-new",
    "chapter-title",
    "chaptertitle",
    "part-title",
    "parttitle",
)
QUOTE_CLASSES = ("quote", "quote-source", "extract", "epigraph")
STRONG_CLASSES = ("emphasis-strong", "bold", "emphasistypebold")
BOLD_CLASSES = ("emphasistypebold",)
BOLDITALIC_CLASSES = ("emphasistypebolditalic",)
# LaTeX carried in an <img alt="...">, another publisher's equation convention.
TEX_ALT_RE = re.compile(r"^\s*\$\$(.+)\$\$\s*$|^\s*\\\((.+)\\\)\s*$", re.S)


def cls(node):
    c = node.get("class") or []
    if isinstance(c, str):
        c = c.split()
    return {x.strip().lower() for x in c}


def has_cls(node, names):
    return bool(cls(node) & set(names))


def raw_text(node):
    """Text with whitespace intact — for code, where indentation is meaning."""
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return str(node).replace("\xa0", " ").replace("\u200a", " ")
    if not isinstance(node, Tag):
        return ""
    if node.name.lower() in SKIP:
        return ""
    return "".join(raw_text(c) for c in node.children)


# --------------------------------------------------------------------- utils
def slugify(s, maxlen=60):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:maxlen].strip("-") or "untitled"


def yaml_str(v):
    v = str(v).replace("\\", "\\\\").replace('"', '\\"')
    v = re.sub(r"\s+", " ", v).strip()
    return '"%s"' % v


def norm_ws(s):
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", s)


# ----------------------------------------------------------------- container
class Epub:
    def __init__(self, path):
        self.z = zipfile.ZipFile(path)
        self.names = self.z.namelist()
        self.opf = next(n for n in self.names if n.endswith(".opf"))
        self.base = posixpath.dirname(self.opf)
        raw = self.z.read(self.opf).decode("utf8", "replace")
        self.opf_raw = raw
        self.meta = self._metadata(raw)
        self.spine = self._spine(raw)

    def _metadata(self, raw):
        m = {}
        for tag, val in re.findall(r"<dc:(\w+)[^>]*>(.*?)</dc:\1>", raw, re.S):
            val = html.unescape(re.sub(r"<[^>]+>", "", val)).strip()
            m.setdefault(tag, []).append(val)
        return m

    def _spine(self, raw):
        ids = dict(re.findall(r'<item\s[^>]*id="([^"]+)"[^>]*href="([^"]+)"', raw))
        ids.update(
            {i: h for h, i in re.findall(r'<item\s[^>]*href="([^"]+)"[^>]*id="([^"]+)"', raw)}
        )
        out = []
        for idref in re.findall(r'<itemref[^>]*idref="([^"]+)"', raw):
            href = ids.get(idref)
            if not href:
                continue
            p = posixpath.normpath(posixpath.join(self.base, href.split("#")[0]))
            if p in self.names:
                out.append(p)
        return out

    def read(self, p):
        return self.z.read(p).decode("utf8", "replace")


# ------------------------------------------------------------------ renderer
class Renderer:
    def __init__(self, doc_path, media_prefix="images", code_lang=""):
        self.doc_dir = posixpath.dirname(doc_path)
        self.media_prefix = media_prefix
        self.code_lang = code_lang
        self.code_blocks = 0
        self.code_lines = 0
        self.alt_tex = 0
        self.math = []
        self.pages = []
        self.held_marks = []
        self.figures = []
        self.tables = 0

    # ---- inline -------------------------------------------------------
    def inline(self, node):
        if isinstance(node, Comment):
            return ""
        if isinstance(node, NavigableString):
            # Escape literal $ so prices ("$0.40 to $4.00") never read as math.
            return norm_ws(str(node)).replace("$", r"\$")
        if not isinstance(node, Tag):
            return ""
        n = node.name.lower()
        if n in SKIP:
            return ""
        if n == "br":
            return "\n"
        if n == "img":
            return self.img(node)
        if n == "mathph":
            return self.math_ref(node)

        inner = "".join(self.inline(c) for c in node.children)

        if n in ("i", "em", "cite"):
            return self._wrap(inner, "*")
        if n in ("b", "strong"):
            return self._wrap(inner, "**")
        if n in ("code", "kbd", "samp", "tt"):
            return "`%s`" % inner.strip() if inner.strip() else ""
        if n in ("sub",):
            return "~%s~" % inner.strip() if inner.strip() else ""
        if n in ("sup",):
            return "^%s^" % inner.strip() if inner.strip() else ""
        if n == "a":
            href = node.get("href", "")
            if href.startswith("http"):
                return "[%s](%s)" % (inner.strip(), href) if inner.strip() else ""
            return inner  # internal anchors -> plain text
        if n == "span" and node.get("epub:type") == "pagebreak":
            return self.pagebreak(node)
        if n == "span":
            if has_cls(node, MONO_CLASSES):
                t = inner.strip()
                return "`%s`" % t if t else ""
            if has_cls(node, STRONG_CLASSES):
                return self._wrap(inner, "**")
            if has_cls(node, BOLDITALIC_CLASSES):
                return self._wrap(inner, "***")
            if has_cls(node, BOLD_CLASSES):
                return self._wrap(inner, "**")
            if has_cls(node, ITALIC_CLASSES):
                return self._wrap(inner, "*")
        return inner

    def drain_marks(self, out):
        """Emit the page markers a heading held back, ahead of the heading."""
        for m in self.held_marks:
            out.append(("raw", m))
        self.held_marks = []

    @staticmethod
    def _wrap(inner, mark):
        """Emphasis that never emits ** ** around whitespace."""
        if not inner.strip():
            return inner
        lead = " " if inner[:1].isspace() else ""
        tail = " " if inner[-1:].isspace() else ""
        return "%s%s%s%s%s" % (lead, mark, inner.strip(), mark, tail)

    def pagebreak(self, node):
        num = node.get("title") or node.get("aria-label") or ""
        num = num.strip()
        if num:
            self.pages.append(num)
            return "PAGE:%s" % num
        return ""

    def math_ref(self, node):
        idx = int(node["data-i"])
        tex, block = self.math[idx]
        if tex is None:
            return ""
        if block:
            return "BMATH:%d" % idx
        return "$%s$" % tex

    def img(self, node):
        src = node.get("src", "")
        alt_raw = node.get("alt", "") or ""
        # Some publishers render each equation as a PNG but keep the LaTeX in alt.
        m = TEX_ALT_RE.match(alt_raw.strip())
        if m:
            tex = (m.group(1) or m.group(2) or "").strip()
            if tex:
                self.math.append((tex, True))
                self.alt_tex += 1
                return "\x01BMATH:%d\x01" % (len(self.math) - 1)
        alt = norm_ws(alt_raw).strip()
        # Some EPUBs repeat the filename in alt when there is no real description.
        if re.fullmatch(r"[\w./-]+\.(jpe?g|png|gif|svg)", alt, re.I):
            alt = ""
        if alt.lower() in ("image", "images", "equation", "figure", "photo", ""):
            alt = ""
        path = posixpath.normpath(posixpath.join(self.doc_dir, src)) if src else ""
        name = posixpath.basename(path)
        self.figures.append({"file": name, "alt": alt})
        return "IMG:%s|%s" % (name, alt)

    # ---- block --------------------------------------------------------
    def block(self, node, out, depth=0):
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            t = norm_ws(str(node)).replace("$", r"\$")
            if t.strip():
                out.append(("p", t.strip()))
            return
        if not isinstance(node, Tag):
            return
        n = node.name.lower()
        if n in SKIP:
            return

        # An equation container: the MathML supersedes its PNG rendering.
        if node.find("mathph") is not None and node.find("img") is not None:
            for im in node.find_all("img"):
                alt = im.get("alt", "").strip().lower()
                sib = im.find_next_sibling()
                near_math = sib is not None and getattr(sib, "name", "") == "mathph"
                if (
                    alt in ("equation", "image", "images")
                    or re.search(r"(math|-i)\d+\.\w+$", im.get("src", ""))
                    or near_math
                ):
                    im.decompose()

        # A pagebreak marker reached at block level — between two paragraphs
        # rather than inside one. The container branch below renders a node's
        # *children*, and an empty <span/> has none, so the marker was dropped
        # without a trace. Page numbers are the whole citation story, so this is
        # handled before anything else can swallow it.
        if n == "span" and node.get("epub:type") == "pagebreak":
            mark = self.pagebreak(node)
            if mark:
                out.append(("raw", mark))
            return

        # An equation set directly at block level, not inside a paragraph. The
        # container branch below would render its (empty) children and drop it.
        if n == "mathph":
            ref = self.math_ref(node)
            if ref:
                out.append(("p", ref))
            return

        if re.fullmatch(r"h[1-6]", n):
            txt = self.heading_text(node)
            self.drain_marks(out)
            if txt:
                out.append(("h%d" % int(n[1]), txt))
            return

        if n == "p":
            names = cls(node)
            if names & set(TOP_HEADING_CLASSES):
                txt = self.heading_text(node)
                self.drain_marks(out)
                if txt:
                    out.append(("h1", txt))
                return
            for c in names:
                m = HEADING_CLASS_RE.match(c)
                if m:
                    txt = self.heading_text(node)
                    self.drain_marks(out)
                    if txt:
                        out.append(("h%d" % min(6, max(2, int(m.group(1)))), txt))
                    return
            if names & set(QUOTE_CLASSES):
                txt = "".join(self.inline(c) for c in node.children).strip()
                txt = self.resolve(txt)
                if txt:
                    out.append(("raw", "> " + txt.replace("\n", "\n> ")))
                return

        if n == "table":
            out.append(("raw", self.table(node)))
            self.tables += 1
            return

        if n == "figure":
            # A figure holding a table is a table with a caption, not a picture.
            # At least one publisher wraps every data table this way, the same
            # element it uses for a photograph, and the picture path below
            # renders the caption and then throws the contents away. In the book
            # that exposed it, sixteen chapters lost their tables, the worst 16%
            # of the chapter, and nothing about the output looked wrong: the
            # caption was still there.
            tables = node.find_all("table")
            if tables:
                head = self.figure(node)
                if head.strip():
                    out.append(("raw", head))
                for t in tables:
                    self.block(t, out, depth + 1)
                return
            out.append(("raw", self.figure(node)))
            return

        if n in ("ul", "ol"):
            out.append(("raw", self.list(node, ordered=(n == "ol"))))
            return

        if has_cls(node, PRE_CLASSES):
            out.append(("raw", self.code_block(node)))
            return

        if n == "pre":
            body = raw_text(node).strip("\n")
            if not body.strip():
                return
            self.code_blocks += 1
            self.code_lines += body.count("\n") + 1
            fence = "```" if "```" not in body else "~~~"
            out.append(("raw", "%s%s\n%s\n%s" % (fence, self.code_lang, body, fence)))
            return

        if n == "blockquote":
            sub = []
            for c in node.children:
                self.block(c, sub, depth + 1)
            body = "\n\n".join(self.emit(sub).split("\n\n"))
            out.append(
                ("raw", "\n".join("> " + ln if ln.strip() else ">" for ln in body.split("\n")))
            )
            return

        if n == "hr":
            out.append(("raw", "---"))
            return

        # Container: recurse if it holds block children, else treat as a para.
        if any(isinstance(c, Tag) and c.name.lower() in BLOCK for c in node.children):
            for c in node.children:
                self.block(c, out, depth + 1)
            return

        txt = "".join(self.inline(c) for c in node.children)
        txt = txt.strip()
        if txt:
            out.append(("p", txt))

    def code_block(self, node):
        """div.ProgramCode -> fenced block, one line per div.FixedLine."""
        lines = []
        holders = node.find_all(lambda t: isinstance(t, Tag) and has_cls(t, LINE_CLASSES))
        if holders:
            for h in holders:
                lines.append(raw_text(h).rstrip())
        else:
            lines = raw_text(node).split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return ""
        # Drop indentation common to every line.
        ind = [len(l) - len(l.lstrip(" ")) for l in lines if l.strip()]
        cut = min(ind) if ind else 0
        body = "\n".join(l[cut:] if l.strip() else "" for l in lines)
        body = body.replace("\u200a", " ")
        self.code_blocks += 1
        self.code_lines += len(lines)
        fence = "```" if "```" not in body else "~~~"
        return "%s%s\n%s\n%s" % (fence, self.code_lang, body, fence)

    def heading_text(self, node):
        """Join heading spans with a separator so 'CHAPTER 2' + title do not fuse.

        A page marker found inside the heading is held in `self.held_marks` for
        the caller to emit rather than discarded. Publisher EPUBs often open a
        chapter with one, and dropping it makes the first printed page of each chapter — the
        page a citation is most likely to want — the one page that cannot be
        cited.
        """
        parts = []
        for c in node.children:
            if isinstance(c, Tag) and c.name.lower() == "br":
                parts.append("")
                continue
            s = self.inline(c)
            # Keep the marker out of the heading text, but hold on to it.
            self.held_marks.extend(re.findall(r"\x01PAGE:[^\x01]*\x01", s))
            s = re.sub(r"\x01PAGE:[^\x01]*\x01", "", s)
            # Concatenate rather than join: InDesign splits words across spans
            # ("Exe"+"cution"), and a joining space would break them apart.
            parts.append(s)
        txt = "".join(parts)
        txt = txt.replace("  ", " — ").replace("", " — ")
        txt = re.sub(r"\s+", " ", txt).strip()
        txt = re.sub(r"^\s*—\s*|\s*—\s*$", "", txt)
        return txt

    def list(self, node, ordered=False):
        lines = []
        i = 1
        for li in node.find_all("li", recursive=False):
            nested = []
            for sub in li.find_all(["ul", "ol"], recursive=False):
                nested.append(self.list(sub, sub.name.lower() == "ol"))
                sub.extract()
            body = "".join(self.inline(c) for c in li.children).strip()
            body = re.sub(r"\s+", " ", body)
            mark = ("%d." % i) if ordered else "-"
            # Endnote lists repeat their own number in the text; drop the echo.
            if ordered:
                body = re.sub(r"^%d\s+(?=\S)" % i, "", body)
            if body:
                lines.append("%s %s" % (mark, body))
                i += 1
            for nb in nested:
                lines.append("\n".join("  " + l for l in nb.split("\n")))
        return "\n".join(lines)

    def figure(self, node):
        img = node.find("img")
        cap = node.find("figcaption")
        parts = []
        if img is not None:
            parts.append(self.inline(img))
        if cap is not None:
            c = "".join(self.inline(x) for x in cap.children).strip()
            c = re.sub(r"\s+", " ", c)
            if c:
                parts.append("CAP:%s" % c)
        return "\n".join(parts)

    def table(self, node):
        rows = []
        for tr in node.find_all("tr"):
            cells = []
            for td in tr.find_all(["td", "th"]):
                v = "".join(self.inline(c) for c in td.children)
                v = self.resolve(v)
                v = re.sub(r"\s+", " ", v).strip()
                # LaTeX norm bars (\|) would otherwise read as column breaks.
                v = v.replace(r"\|", r"\Vert ")
                v = v.replace("|", "\\|")
                span = int(td.get("colspan", 1) or 1)
                cells.append(v)
                cells += [""] * (span - 1)
            rows.append(cells)
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        # Use the first row as header only if it looks like labels, not data.
        head = rows[0]
        has_th = node.find("th") is not None
        numericish = sum(1 for c in head if re.fullmatch(r"[-+]?[\d.,%$ ]+", c or "x"))
        if not has_th and numericish > width / 2:
            head = [""] * width
            body = rows
        else:
            body = rows[1:]
        out = [
            "| " + " | ".join(head) + " |",
            "| " + " | ".join("---" for _ in range(width)) + " |",
        ]
        out += ["| " + " | ".join(r) + " |" for r in body]
        cap = node.find("caption")
        if cap is not None:
            t = re.sub(r"\s+", " ", cap.get_text(" ")).strip()
            if t:
                out.insert(0, "**%s**\n" % t)
        return "\n".join(out)

    # ---- placeholder resolution --------------------------------------
    def resolve(self, s, keep_pages=True):
        def page(m):
            return " <!-- page %s --> " % m.group(1) if keep_pages else ""

        s = re.sub(r"PAGE:([^]*)", page, s)

        def bmath(m):
            tex, _ = self.math[int(m.group(1))]
            return "\n\n$$\n%s\n$$\n\n" % tex if tex else ""

        s = re.sub(r"BMATH:(\d+)", bmath, s)

        def image(m):
            name, alt = m.group(1), m.group(2)
            return "\n\n![%s](%s/%s)\n" % (alt, self.media_prefix, name)

        s = re.sub(r"IMG:([^|]*)\|([^]*)", image, s)
        s = re.sub(r"CAP:([^]*)", lambda m: "*%s*" % m.group(1), s)
        return s

    def emit(self, blocks):
        chunks = []
        for kind, val in blocks:
            if kind == "raw":
                chunks.append(val)
            elif kind.startswith("h"):
                chunks.append("#" * int(kind[1:]) + " " + val)
            else:
                chunks.append(val)
        text = "\n\n".join(c for c in chunks if c and c.strip())
        return text


# --------------------------------------------------------------------- main
WORD_NUM = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    )
}
WORD_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def spelled_number(text):
    """'nine' -> 9, 'twenty-four' -> 24. Some books number their units in words."""
    t = text.strip().lower().replace("\u2013", "-")
    if t in WORD_NUM:
        return WORD_NUM[t]
    if t in WORD_TENS:
        return WORD_TENS[t]
    m = re.match(r"(twenty|thirty|forty|fifty)[\s-]+(\w+)$", t)
    if m and m.group(2) in WORD_NUM:
        return WORD_TENS[m.group(1)] + WORD_NUM[m.group(2)]
    return None


def toc_chapter_starts(book, spine, titles):
    """Recover chapter boundaries from a flat spine using the TOC document.

    Some EPUBs converted out of PDF have no hierarchy at all: every section is
    a peer <h1> and the NCX is one level deep. Their TOC page still lists the
    chapters, one <p> per chapter, the chapter name first. Matching those names
    back to section headings *exactly* — and keeping only matches that move
    forward through the book — gives real boundaries without guessing.
    """
    tocdoc = None
    for p_, t in zip(spine, titles):
        if t.strip().lower() in ("table of contents", "contents"):
            tocdoc = p_
            break
    if not tocdoc:
        return {}
    raw = book.read(tocdoc)
    names = []
    for para in re.findall(r"<p[^>]*>(.*?)</p>", raw, re.S):
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", para))).strip()
        m = re.match(r"(.+?)\s*\.\s*\.\s*\.", txt)
        if m:
            cand = m.group(1).strip()
            if 3 < len(cand) < 80:
                names.append(cand)
    norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    index = {}
    for i, t in enumerate(titles):
        index.setdefault(norm(t), i)
    starts, last = {}, -1
    for n in names:
        i = index.get(norm(n))
        if i is not None and i > last:
            starts[i] = n
            last = i
    return starts


def ncx_labels(book):
    """spine path -> its NCX label. Some exports leave <title> as a filename."""
    ncx = [n for n in book.names if n.endswith(".ncx")]
    if not ncx:
        return {}
    raw = book.z.read(ncx[0]).decode("utf8", "replace")
    base = posixpath.dirname(ncx[0])
    out = {}
    for m in re.finditer(r"<navPoint.*?</navPoint>", raw, re.S):
        blk = m.group(0)
        t = re.search(r"<text>(.*?)</text>", blk, re.S)
        c = re.search(r'<content[^>]*src="([^"]+)"', blk)
        if not (t and c):
            continue
        label = html.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip()
        tgt = posixpath.normpath(posixpath.join(base, c.group(1).split("#")[0]))
        if label:
            out.setdefault(tgt, label)
    return out


def doc_title(book, path):
    """The <title> element, a better fallback than the source filename."""
    m = re.search(r"<title[^>]*>(.*?)</title>", book.read(path), re.S | re.I)
    if not m:
        return ""
    t = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    return re.sub(r"\s+", " ", t)


def convert_doc(book, path, media_prefix, code_lang=""):
    raw = book.read(path)
    r = Renderer(path, media_prefix, code_lang)

    # Rescue MathML left commented out beside each equation PNG.
    raw = COMMENTED_MATH_RE.sub(lambda m: m.group(1), raw)

    # Pull MathML out before parsing: bs4 mangles the namespace, and the
    # tested converter wants the original fragment.
    def stash(m):
        r.math.append(mathml_to_latex(m.group(0)))
        return '<mathph data-i="%d"></mathph>' % (len(r.math) - 1)

    raw = MATH_RE.sub(stash, raw)

    soup = BeautifulSoup(raw, "lxml")
    body = soup.body or soup
    blocks = []
    for child in body.children:
        r.block(child, blocks)
    md = r.emit(blocks)
    md = r.resolve(md)

    # Whitespace tidying must not reach inside code fences, where the
    # indentation is the meaning.
    fences = []

    def _park(m):
        fences.append(m.group(0))
        return "\x01FENCE:%d\x01" % (len(fences) - 1)

    md = re.sub(r"(?ms)^(```|~~~).*?^\1[ \t]*$", _park, md)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r" {2,}", " ", md)
    md = re.sub(r"\x01FENCE:(\d+)\x01", lambda m: fences[int(m.group(1))], md)
    return md.strip(), r


def title_of(md, fallback):
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else fallback


def extract_images(book, outdir, prefix, max_px):
    """Pull the figures the Markdown actually references, optionally downscaled."""
    import glob as _glob

    refs = set()
    for f in _glob.glob(os.path.join(outdir, "*.md")):
        with open(f) as fh:
            refs |= set(re.findall(r"!\[[^\]]*\]\(%s/([^)]+)\)" % re.escape(prefix), fh.read()))
    by = {posixpath.basename(n): n for n in book.names}
    dest = os.path.join(outdir, prefix)
    os.makedirs(dest, exist_ok=True)
    written = total = 0
    for r in sorted(refs):
        src = by.get(r)
        if not src:
            continue
        data = book.z.read(src)
        out = os.path.join(dest, r)
        if max_px:
            try:
                import io

                from PIL import Image

                im = Image.open(io.BytesIO(data))
                if max(im.size) > max_px:
                    im.thumbnail((max_px, max_px), Image.LANCZOS)
                # The source stores line charts as full RGB PNG, which is
                # ~90x larger than they need to be. Palette them when the
                # colour count says "chart"; fall back to JPEG for photos.
                buf = io.BytesIO()
                rgb = im.convert("RGB")
                colors = rgb.getcolors(maxcolors=8192)
                if colors is not None:
                    rgb.convert("P", palette=Image.ADAPTIVE, colors=256).save(
                        buf, "PNG", optimize=True
                    )
                else:
                    rgb.save(buf, "JPEG", quality=85, optimize=True)
                if 0 < buf.tell() < len(data):
                    data = buf.getvalue()
            except Exception:
                pass
        with open(out, "wb") as fh:
            fh.write(data)
        written += 1
        total += len(data)
    print("images: %d extracted (%.1f MB)" % (written, total / 1e6))


def main(argv: list[str] | None = None) -> int:
    """`h2m epub`: convert one EPUB into per-chapter Markdown files. Returns the exit code."""
    ap = argparse.ArgumentParser(prog="h2m epub")
    ap.add_argument("epub", help="the .epub file to convert")
    ap.add_argument("-o", "--out", required=True, help="output root; files land in OUT/SLUG/")
    ap.add_argument("--slug", default=None, help="output subdirectory; defaults to the filename")
    ap.add_argument("--limit", type=int, default=0, help="only the first N spine documents")
    ap.add_argument(
        "--media-prefix",
        default="images",
        help="directory name used in image links (default: images)",
    )
    ap.add_argument(
        "--group-sections",
        action="store_true",
        help="for flat EPUBs with one <h1> section per spine doc: "
        "merge consecutive sections into chapter files using "
        "boundaries recovered from the TOC page",
    )
    ap.add_argument(
        "--code-lang", default="", help="language tag for fenced code blocks, e.g. cpp, python"
    )
    ap.add_argument(
        "--images",
        action="store_true",
        help="also extract referenced figures (off by default: the "
        "alt-text descriptions already carry the meaning, and "
        "the raw PNGs run to gigabytes)",
    )
    ap.add_argument(
        "--max-px",
        type=int,
        default=1400,
        help="downscale extracted figures to this longest edge; 0 = full size",
    )
    a = ap.parse_args(argv)

    book = Epub(a.epub)
    slug = a.slug or slugify(os.path.splitext(os.path.basename(a.epub))[0])
    outdir = os.path.join(a.out, slug)
    os.makedirs(outdir, exist_ok=True)

    btitle = (book.meta.get("title") or ["Untitled"])[0]
    subtitle = (book.meta.get("title") or ["", ""])[1:2]
    author = ", ".join(book.meta.get("creator", []))
    ident = (book.meta.get("identifier") or [""])[0]
    date = (book.meta.get("date") or [""])[0][:10]
    lang = (book.meta.get("language") or ["en"])[0]

    docs = book.spine[: a.limit] if a.limit else book.spine

    # Pass 1: render every spine document.
    labels = ncx_labels(book)
    rendered = []
    navdocs = []
    for i, p in enumerate(docs):
        name = posixpath.basename(p)
        stem = os.path.splitext(name)[0]
        if stem.lower() in ("cover", "navigation", "toc", "eula", "nav"):
            continue
        md, r = convert_doc(book, p, a.media_prefix, a.code_lang)
        if len(md.split()) < 20:
            continue
        t = doc_title(book, p)
        if not t or re.fullmatch(r"[\w.-]*\d[\w.-]*", t):
            t = labels.get(p, "") or t  # <title> is a filename here
        h1 = title_of(md, t or stem)
        nav = re.sub(r"[^a-z ]", "", h1.lower()).strip()
        if nav in (
            "table of contents",
            "contents",
            "index",
            "front matter",
            "back matter",
            "copyright",
        ):
            navdocs.append(dict(path=p, h1=h1))
            continue
        rendered.append(dict(i=i, path=p, name=name, md=md, r=r, h1=h1))

    # Optional pass 2: fold a flat section list into chapter-sized files.
    groups = []
    if a.group_sections:
        toc_paths = [d["path"] for d in navdocs if "content" in d["h1"].lower()] or [
            x["path"] for x in rendered
        ]
        starts = toc_chapter_starts(
            book,
            toc_paths + [x["path"] for x in rendered],
            ["Table of Contents"] * len(toc_paths) + [x["h1"] for x in rendered],
        )
        starts = {k - len(toc_paths): v for k, v in starts.items() if k >= len(toc_paths)}
        if len(starts) >= 5:
            cur = None
            for n, item in enumerate(rendered):
                if n in starts or cur is None:
                    cur = dict(title=starts.get(n, item["h1"]), items=[])
                    groups.append(cur)
                cur["items"].append(item)
            print("grouped %d sections into %d chapters via the TOC" % (len(rendered), len(groups)))
        else:
            print("TOC gave only %d boundaries; keeping one file per section" % len(starts))
    if not groups:
        groups = [dict(title=x["h1"], items=[x]) for x in rendered]

    # Zero-pad the file prefix wide enough that plain sorting stays in order.
    pad = max(2, len(str(max((g["items"][0]["i"] for g in groups), default=0))))

    manifest = []
    for gi, g in enumerate(groups):
        items = g["items"]
        first = items[0]
        if len(items) == 1:
            md = first["md"]
        else:
            # Demote each section to a level-2 heading under the chapter title.
            parts = ["# %s" % g["title"]]
            for it in items:
                body = re.sub(r"^#\s+.*$", "", it["md"], count=1, flags=re.M).strip()
                parts.append("## %s\n\n%s" % (it["h1"], body))
            md = "\n\n".join(parts)
        h1 = g["title"]
        cnum = None
        clean = h1
        mm = re.match(r"(?:CHAPTER|CHAP\.?|Ch\.?)\s+(\d+)\s*[.:—-]*\s*(.*)$", h1, re.I)
        if not mm:
            mm = re.match(r"(\d{1,2})\s*[.:]\s+(\S.*)$", h1)
        # "Strategy nine: ..." / "Part Two: ..." number the unit in words.
        wm = re.match(r"(?:strategy|part|tactic|chapter)\s+([\w-]+)\s*[:.]\s*(.*)$", h1, re.I)
        if mm:
            cnum = int(mm.group(1))
            clean = mm.group(2).strip() or h1
        elif wm and spelled_number(wm.group(1)) is not None:
            cnum = spelled_number(wm.group(1))
            clean = h1
        elif len(groups) < len(rendered):
            cnum = gi  # grouped mode: position is the chapter number
        eqs = sum(sum(1 for t, _ in it["r"].math if t) for it in items)
        tbls = sum(it["r"].tables for it in items)
        figs = sum(len(it["r"].figures) for it in items)
        cbs = sum(it["r"].code_blocks for it in items)
        cls_ = sum(it["r"].code_lines for it in items)
        pages = [pg for it in items for pg in it["r"].pages]
        fname = "%0*d_%s.md" % (pad, first["i"], slugify(h1, 48))
        fm = [
            "---",
            "book: %s" % yaml_str(btitle),
            "edition: %s" % yaml_str(subtitle[0]) if subtitle else None,
            "author: %s" % yaml_str(author),
            "identifier: %s" % yaml_str(ident),
            "published: %s" % yaml_str(date),
            "language: %s" % yaml_str(lang),
            "chapter: %s" % (cnum if cnum is not None else "null"),
            "title: %s" % yaml_str(clean),
            "sections: %d" % len(items),
            "source_file: %s" % yaml_str(", ".join(it["name"] for it in items)[:200]),
            "source_epub: %s" % yaml_str(os.path.basename(a.epub)),
            "words: %d" % len(md.split()),
            "equations: %d" % eqs,
            "tables: %d" % tbls,
            "figures: %d" % figs,
            "code_blocks: %d" % cbs,
            "code_lines: %d" % cls_,
            "pages: %s" % yaml_str("%s-%s" % (pages[0], pages[-1]) if pages else ""),
            "---",
            "",
        ]
        fm = [x for x in fm if x is not None]
        with open(os.path.join(outdir, fname), "w") as fh:
            fh.write("\n".join(fm) + md + "\n")
        manifest.append((fname, h1, len(md.split()), eqs, tbls, figs))
        print(
            "  %-44s %7d words  %4d eq  %3d tbl  %4d fig  %3d code"
            % (fname[:44], len(md.split()), eqs, tbls, figs, cbs)
        )

    if a.images:
        extract_images(book, outdir, a.media_prefix, a.max_px)

    tot = [sum(x[i] for x in manifest) for i in (2, 3, 4, 5)]
    print("\n%d files -> %s" % (len(manifest), outdir))
    print(
        "totals: %,d words | %d equations | %d tables | %d figures".replace("%,d", "{:,}").format(
            tot[0]
        )
        % (tot[1], tot[2], tot[3])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

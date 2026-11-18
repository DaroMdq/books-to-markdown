"""Audit a directory of converted books the way a consumer would read them.

    python bin/audit.py OUT_ROOT        # OUT_ROOT holds one directory per book

Structural faults fail the run (exit 1): unparseable front matter, an odd number
of code fences or `$$` markers, unbalanced LaTeX braces, a ragged table, an
image link with no file. Those make a file wrong for any reader, whatever it
says.

Content defects are counted, not raised. A control byte, a blank image and a
line of leaked markup are all real, and none of them stops a machine reading
the file. Failing on them would keep the gate red until somebody fixes them,
which teaches the next reader to ignore it.

Every check that hunts for stray markup runs on the prose only. A web-scraping
chapter can hold `<html lang="en">` inside a Python string, and that is correct
content: it is inside a fence and is skipped. A listing that was never fenced
is not skipped, and is counted as leaked markup, which it is.

`bin/audit.py` is a development tool and is not installed with the package;
`tests/test_audit.py` runs it against the bundled example.
"""

from __future__ import annotations

import glob
import os
import re
import sys

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
FENCE = re.compile(r"^```.*?^```", re.M | re.S)
TICKS = re.compile(r"`[^`\n]*`")
IMG = re.compile(r"!\[[^\]]*\]\((images/[^)]+)\)")
RAW_HTML = re.compile(r"</?(?:div|span|p|table|tr|td|th|body|html|head)\b", re.I)
RAW_MATH = re.compile(r"</?m(?:ath|row|i|n|o|frac|sup|sub)\b", re.I)
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def prose_only(text):
    """The text with fenced blocks and inline code removed.

    Every check below that looks for stray markup has to run on this and not on
    the raw file. A web-scraping chapter's Python strings can contain
    `<html lang="en">`, which is correct content and looks exactly like leaked
    markup to a grep.
    """
    return TICKS.sub("`` ", FENCE.sub("\n", text))


def maths_spans(text):
    """Every `$...$` and `$$...$$` run, with escaped dollars left alone.

    A book can write spreadsheet references as `\\text{\\$} 2` inside maths, so
    a splitter that treats every dollar as a delimiter cuts one expression into
    two broken halves and reports both. That is not a corpus fault, and it took
    reading the LaTeX to see it.
    """
    text = re.sub(r"\\\$", "\x00", prose_only(text))
    return re.findall(r"\$\$(.*?)\$\$", text, re.S) + re.findall(r"(?<!\$)\$([^$\n]+)\$", text)


def latex_balanced(text):
    """Braces inside maths only. Prose braces are prose."""
    bad = 0
    for chunk in maths_spans(text):
        depth = 0
        for i, c in enumerate(chunk):
            if c == "{" and (i == 0 or chunk[i - 1] != "\\"):
                depth += 1
            elif c == "}" and (i == 0 or chunk[i - 1] != "\\"):
                depth -= 1
            if depth < 0:
                break
        if depth != 0:
            bad += 1
    return bad


def ragged(text):
    """A pipe table whose rows disagree about how many columns there are.

    An escaped pipe is content, not a column boundary — a book can set conditional
    probabilities as `P(A \\| B)` inside a table cell.
    """
    bad, run = 0, []
    for line in prose_only(text).splitlines() + [""]:
        if line.startswith("|") and line.endswith("|"):
            run.append(line.replace("\\|", "").count("|"))
            continue
        if len(run) > 2 and len(set(run)) > 1:
            bad += 1
        run = []
    return bad


def blank_images(book):
    """A figure with no dark ink anywhere is a background fill, not a figure."""
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return None
    out = []
    for f in sorted(glob.glob(os.path.join(book, "images", "*"))):
        try:
            im = Image.open(f).convert("L")
        except Exception:
            continue
        if im.getextrema()[0] > 100 and ImageStat.Stat(im).stddev[0] < 35:
            out.append(os.path.basename(f))
    return out


def main(root: str) -> int:
    """Audit every book directory under `root`; return 0, 1 (structural faults) or 2."""
    books = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    if not books:
        print("no book directories under %s" % root, file=sys.stderr)
        return 2

    # Words are counted on Unicode whitespace, so this runs a little above
    # `wc -w`: books are full of non-breaking spaces, and "3 000" is two words
    # however it was typeset.
    fatal = 0
    print(
        "%-20s %5s %8s %7s %6s %6s %6s %6s %6s"
        % ("BOOK", "files", "words", "marks", "imgs", "blank", "ctrl", "mkup", "FAULT")
    )
    tot = dict.fromkeys(
        ("files", "words", "markers", "imgs", "blank", "ctrl", "bad", "dangle", "html"), 0
    )
    for b in books:
        d = os.path.join(root, b)
        files = sorted(glob.glob(d + "/*.md"))
        words = markers = ctrl = bad = html = 0
        refs = set()
        for f in files:
            with open(f) as fh:
                text = fh.read()
            words += len(text.split())
            markers += text.count("<!-- page ")
            ctrl += sum(1 for ln in text.splitlines() if CONTROL.search(ln))
            refs |= {m for m in IMG.findall(text)}
            why = []
            if not FRONT.match(text):
                why.append("no front matter")
            if text.count("```") % 2:
                why.append("odd code fences")
            if prose_only(text).replace("\\$", "").count("$$") % 2:
                why.append("odd $$")
            n = latex_balanced(text)
            if n:
                why.append("%d unbalanced maths" % n)
            clean = prose_only(text)
            html += len(RAW_HTML.findall(clean)) + len(RAW_MATH.findall(clean))
            n = ragged(text)
            if n:
                why.append("%d ragged tables" % n)
            if why:
                bad += 1
                print("   FAIL %s: %s" % (os.path.relpath(f, root), "; ".join(why)))
        have = set(os.listdir(d + "/images")) if os.path.isdir(d + "/images") else set()
        dangle = {r[len("images/") :] for r in refs} - have
        for x in sorted(dangle):
            print("   FAIL %s: image link with no file (%s)" % (b, x))
        blanks = blank_images(d)
        nb = "-" if blanks is None else len(blanks)
        fatal += bad + len(dangle)
        print(
            "%-20s %5d %8d %7d %6d %6s %6d %6d %6d"
            % (b, len(files), words, markers, len(have), nb, ctrl, html, bad + len(dangle))
        )
        for k, v in (
            ("files", len(files)),
            ("words", words),
            ("markers", markers),
            ("imgs", len(have)),
            ("ctrl", ctrl),
            ("bad", bad),
            ("dangle", len(dangle)),
            ("html", html),
            ("blank", 0 if blanks is None else len(blanks)),
        ):
            tot[k] += v
    print(
        "%-20s %5d %8d %7d %6d %6d %6d %6d %6d"
        % (
            "TOTAL",
            tot["files"],
            tot["words"],
            tot["markers"],
            tot["imgs"],
            tot["blank"],
            tot["ctrl"],
            tot["html"],
            tot["bad"] + tot["dangle"],
        )
    )
    print()
    if fatal:
        print("STRUCTURAL FAULTS: %d — the corpus is not fit to hand over" % fatal)
        return 1
    print("No structural faults: every file parses and every image link resolves.")
    print("Counted defects (real, but none of them stops a reader):")
    print("  blank  %4d images carrying no ink" % tot["blank"])
    print("  ctrl   %4d lines with an unmapped glyph as a control byte" % tot["ctrl"])
    print(
        "  mkup   %4d markup fragments in prose, from listings that were never fenced" % tot["html"]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "out"))

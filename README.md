# books-to-markdown

[![CI](https://github.com/DaroMdq/books-to-markdown/actions/workflows/ci.yml/badge.svg)](https://github.com/DaroMdq/books-to-markdown/actions/workflows/ci.yml)

`h2m` converts technical books (EPUB and text PDF) into one Markdown file per chapter for language models, and then checks the output against the source so that nothing is silently dropped. In a book, a formula may be a picture, a heading may be just a font size, and a page number may sit alone in the margin. Every real bug this tool has had produced output that *looked right*, so the comparison against the source is part of the tool, not an afterthought.

## Quick start

Needs Python 3.12 or newer. The sample book is original text bundled in `examples/`.

```bash
git clone https://github.com/DaroMdq/books-to-markdown.git && cd books-to-markdown
python3 -m venv .venv && . .venv/bin/activate
pip install .
h2m epub examples/field-guide.epub -o out --slug field-guide --code-lang python
h2m verify examples/field-guide.epub out/field-guide
```

## What the output looks like

`out/field-guide/` holds `01_chapter-1-text-is-not-text.md`, `02_…`, `03_…`, named so that plain sorting gives reading order. The same files are committed in [`examples/output/`](examples/output/field-guide/). An excerpt from chapter 2:

```markdown
---
book: "A Field Guide to Plain Text"
chapter: 2
title: "Measuring What Survives"
source_file: "chapter02.xhtml"
words: 175
equations: 3
tables: 0
code_blocks: 1
pages: "3-4"
---
<!-- page 3 -->

# Chapter 2: Measuring What Survives
…
$$
R = 1 - \frac{M}{S}
$$
```

The front matter is a census, not decoration: a chapter that should have 148 equations and reports 0 is visible without opening the file. Printed page numbers become `<!-- page N -->`, which is invisible when rendered and easy to grep when an answer needs to cite a page. MathML becomes LaTeX, tables become pipe tables, and code keeps its indentation.

## Commands

**`h2m epub BOOK.epub -o OUT`** writes `OUT/SLUG/*.md`, one file per spine document (or per chapter with `--group-sections`).

**`h2m pdf BOOK.pdf -o OUT`** splits on the PDF outline. A PDF has no structure, only glyphs at coordinates, so headings, paragraphs, tables, code, running heads and page numbers are all *inferred* from font metrics and geometry measured off each document.

| Flag | Default | Meaning | Command |
|---|---|---|---|
| `-o DIR` | required | output root; files land in `DIR/SLUG/` | epub, pdf |
| `--slug NAME` | file name | output subdirectory | epub, pdf |
| `--code-lang L` | none | language tag on fenced code, e.g. `python` | epub, pdf |
| `--limit N` | 0 (all) | only the first N spine documents (epub) or chapters (pdf) | epub, pdf |
| `--images` | off | also extract figures; the alt text is in the Markdown either way | epub, pdf |
| `--max-px N` | 1400 | longest edge of extracted figures; `0` keeps full size | epub, pdf |
| `--group-sections` | off | rebuild chapters from the contents page when every section is a top-level document (PDF-derived EPUBs) | epub |
| `--media-prefix P` | `images` | directory name used in image links | epub |
| `--first N` / `--last N` | 0 / end | page range, **0-based**; `--last` is exclusive | pdf |
| `--fix-ligatures` | off | repair split ligatures (`profi table` → `profitable`), dictionary-checked | pdf |

**`h2m verify SOURCE OUTDIR`** compares a book with its converted directory. Flags: `--gaps N` (how many of the longest gaps to print, default 8), `--window N` (comparison window in characters, default 16), `--whole-book` (also count the contents and index pages the converter drops on purpose).

`--fix-ligatures` needs a system word list (`/usr/share/dict/words` on macOS; `sudo apt install wamerican` on Debian/Ubuntu) and refuses to run without one: without it the repair would do nothing and report zero repairs, which reads exactly like a book that needed none. It reads the first list it finds and records its name in each chapter's front matter, so a result can be reproduced elsewhere.

## How verification works

`verify` reduces both the source and the Markdown to a stream of lowercase letters and digits, so reflowed lines, healed hyphenation and repaired ligatures do not count as loss. It walks the source in 16-character windows and reports every stretch with no counterpart in the output. On the sample:

```
  recovered 98.54%   missing 32 chars in 2 gaps
  gaps of 300+ chars: 0, totalling 0 (0.00% of the source)
  6 printed pages, 5 chars missing per page  (…)
  1 source documents produced no output, 193 chars (8.79% of the source):
    contents.xhtml                193 chars
```

Read it in this order. **Paragraph-sized gaps (300+ characters)** should be zero: no convention removes paragraphs. **Characters missing per page** should be about one running head; twice that means body text is going. **The recovery percentage** is a band, not a grade: running heads and page numbers are removed on purpose and count as missing, so a real book never reaches 100%. Measured on a private corpus of 12 technical books, it ranged from 92% to 99%. The two 16-character gaps above are things the converter *added* (the `\frac` in the LaTeX and the `python` fence tag), and the dropped contents page is named rather than hidden.

"Fails loudly" means: unreadable input exits non-zero with a one-line message; a flag that cannot work refuses to run; the census shows a missing category at a glance; and `verify` names every skipped document and prints the longest gaps so you can read them. `verify` itself is a report: it exits 0 whatever it finds (1 only if the directory holds no Markdown), because deciding that a gap is a loss is your call. [`bin/audit.py`](bin/audit.py) is the structural gate: it fails (exit 1) on unparseable front matter, odd code fences or `$$`, unbalanced LaTeX braces, ragged tables and image links with no file.

## Known limits

- **No OCR.** Scanned PDFs are out of scope; formulas that a book ships only as images stay images (referenced in place, never read).
- **PDF front matter is thinner** than the EPUB one: words and tables, no equation or figure count.
- **In PDFs, block quotes and margin notes are not separated** from body text; they are kept, but flow into the adjacent paragraph.
- **Footnote references are flattened**: the marker becomes plain text and the note text is kept where the source puts it.
- **Contents and index pages are dropped** as navigation (`verify --whole-book` counts them).
- Only a quarter turn anticlockwise is handled for landscape pages, because that is the only rotation seen in practice.

Design choices and their reasons are numbered in [`docs/DECISIONS.md`](docs/DECISIONS.md); the module map is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); status and next steps in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
bin/check            # ruff check, ruff format --check, pytest
```

The suite runs on EPUBs and PDFs it builds itself in each publisher's *shape* (see `tests/conftest.py`), so no real book is needed and none is committed. The ligature tests read the system word list (built into macOS; `sudo apt install wamerican` on Debian/Ubuntu). `tests/test_examples.py` rebuilds the sample and fails if `examples/output/` no longer matches what the converter produces. CI runs the same three checks on Python 3.12 and 3.13.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success (for `verify`: the report was printed) |
| 1 | input could not be read: missing file, corrupt EPUB, not a PDF, or a `verify` directory with no `.md` files |
| 2 | usage error: unknown command, bad or missing flag, or `--fix-ligatures` with no word list |

## Licence

Copyright (C) 2026 Dario Rocci. Licensed under the [GNU AGPL v3.0](LICENSE), because the PDF pipeline is built on PyMuPDF, which is itself AGPL-licensed.

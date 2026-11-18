"""One entry point, three commands.

    h2m epub   BOOK.epub -o out --slug my-book
    h2m pdf    BOOK.pdf  -o out --slug my-book --fix-ligatures
    h2m verify BOOK.pdf  out/my-book

Dispatch is a plain argv split rather than a shared argparse parent, because the
two pipelines genuinely do not share options: an EPUB has no page range and a PDF
has no spine. A shared parser would have to advertise flags that are ignored on
one side, which is how a flag ends up silently doing nothing.
"""

from __future__ import annotations

import sys
import zipfile

USAGE = """usage: h2m {epub|pdf|verify} SOURCE ... [options]

  h2m epub   BOOK.epub -o out --slug my-book --images
  h2m pdf    BOOK.pdf  -o out --slug my-book --code-lang python --fix-ligatures
  h2m verify BOOK.pdf  out/my-book

`--help` after any of the three lists its options. Converting is not finished
until `verify` has been run: every defect this project has had produced
output that looked right.
"""


def main(argv: list[str] | None = None) -> int:
    """Dispatch to a pipeline and return its exit code (0 ok, 1 unreadable input, 2 usage)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    verb, rest = argv[0], argv[1:]
    if verb == "epub":
        from h2m.epub import main as run
    elif verb == "pdf":
        from h2m.pdf import main as run
    elif verb == "verify":
        from h2m.verify import main as run
    else:
        sys.stderr.write("h2m: unknown command %r\n\n%s" % (verb, USAGE))
        return 2
    import pymupdf

    # A missing file, a corrupt archive, or a PDF PyMuPDF cannot open: say so in
    # one line rather than with a traceback. Anything else is a bug and should
    # keep its traceback.
    unreadable = (OSError, zipfile.BadZipFile, pymupdf.FileDataError, pymupdf.FileNotFoundError)
    try:
        return run(rest) or 0
    except unreadable as exc:
        sys.stderr.write("h2m %s: cannot read input: %s\n" % (verb, exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

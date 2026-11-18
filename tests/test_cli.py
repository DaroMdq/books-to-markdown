"""The `h2m` command as a user runs it: real processes, real exit codes.

Exit codes are part of the interface: 0 for success, 1 for an input that cannot
be read, 2 for a usage error (unknown command, bad flag, or `--fix-ligatures`
with no word list on the machine).
"""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import make_epub, make_pdf

from h2m.cli import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "examples", "field-guide.epub")
SAMPLE_OUT = os.path.join(ROOT, "examples", "output", "field-guide")


def h2m(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m h2m.cli ARGS` in a fresh process."""
    return subprocess.run(
        [sys.executable, "-m", "h2m.cli", *args], capture_output=True, text=True, check=False
    )


def test_converting_an_epub_exits_zero_and_writes_one_file_per_chapter(tmp_path) -> None:
    r = h2m("epub", SAMPLE, "-o", str(tmp_path), "--slug", "guide")
    assert r.returncode == 0, r.stderr
    names = sorted(os.listdir(tmp_path / "guide"))
    assert names == [
        "01_chapter-1-text-is-not-text.md",
        "02_chapter-2-measuring-what-survives.md",
        "03_chapter-3-keeping-the-page.md",
    ]
    assert "3 files ->" in r.stdout


def test_converting_a_pdf_exits_zero_and_splits_on_the_outline(tmp_path) -> None:
    sentence = "Page %d says something of its own about the subject at hand."
    pages = [[(sentence % n, {})] * 6 for n in range(16)]
    path = make_pdf(tmp_path / "b.pdf", pages, toc=[[1, "Chapter One", 1], [1, "Chapter Two", 9]])
    r = h2m("pdf", path, "-o", str(tmp_path / "out"), "--slug", "b")
    assert r.returncode == 0, r.stderr
    assert sorted(os.listdir(tmp_path / "out" / "b")) == ["00_chapter-one.md", "01_chapter-two.md"]


def test_verify_on_the_bundled_example_reports_no_paragraph_sized_gap() -> None:
    r = h2m("verify", SAMPLE, SAMPLE_OUT)
    assert r.returncode == 0, r.stderr
    assert "gaps of 300+ chars: 0" in r.stdout
    assert "contents.xhtml" in r.stdout  # the dropped contents page is named, not hidden


def test_a_missing_input_file_exits_one_with_a_message_and_no_traceback(tmp_path) -> None:
    r = h2m("epub", str(tmp_path / "absent.epub"), "-o", str(tmp_path))
    assert r.returncode == 1
    assert "cannot read input" in r.stderr
    assert "Traceback" not in r.stderr


def test_a_file_that_is_not_a_pdf_exits_one(tmp_path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_text("this is not a PDF")
    r = h2m("pdf", str(bad), "-o", str(tmp_path / "out"))
    assert r.returncode == 1
    assert "cannot read input" in r.stderr


ONE_DOC = [("c1.xhtml", "One", "<h1>Chapter One</h1><p>Some words of the chapter.</p>")]


def test_an_epub_with_no_package_file_exits_one_for_both_commands(tmp_path) -> None:
    # A zip that is not a book: the .opf, which lists the spine, is missing.
    book = make_epub(tmp_path / "b.epub", ONE_DOC, package=False)
    for args in (("epub", book, "-o", str(tmp_path / "out")), ("verify", book, SAMPLE_OUT)):
        r = h2m(*args)
        assert r.returncode == 1, r.stderr
        assert "Traceback" not in r.stderr
        assert r.stderr.count("\n") == 1 and ".opf" in r.stderr, r.stderr


def test_an_unknown_command_is_a_usage_error(capsys) -> None:
    assert main(["docx", "book.docx"]) == 2
    assert "unknown command" in capsys.readouterr().err


def test_a_missing_required_flag_is_a_usage_error(tmp_path) -> None:
    r = h2m("epub", SAMPLE)  # no -o
    assert r.returncode == 2
    assert "-o/--out" in r.stderr


def test_no_arguments_prints_usage_and_exits_zero(capsys) -> None:
    assert main([]) == 0
    assert "usage: h2m" in capsys.readouterr().out


def test_verify_against_a_directory_with_no_markdown_exits_one(tmp_path) -> None:
    # Otherwise a typo in the output path reads as "0% recovered", which looks
    # like a catastrophic conversion rather than a wrong argument.
    r = h2m("verify", SAMPLE, str(tmp_path / "nowhere"))
    assert r.returncode == 1
    assert "no .md files" in r.stderr

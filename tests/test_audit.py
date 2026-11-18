"""`bin/audit.py`: the structural gate for a directory of converted books."""

from __future__ import annotations

import importlib.util
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_audit():
    spec = importlib.util.spec_from_file_location("audit", os.path.join(ROOT, "bin", "audit.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_bundled_example_has_no_structural_faults(capsys) -> None:
    assert load_audit().main(os.path.join(ROOT, "examples", "output")) == 0
    assert "No structural faults" in capsys.readouterr().out


def test_an_unclosed_code_fence_fails_the_audit(tmp_path, capsys) -> None:
    book = tmp_path / "book"
    shutil.copytree(os.path.join(ROOT, "examples", "output", "field-guide"), book)
    victim = sorted(book.glob("*.md"))[0]
    victim.write_text(victim.read_text() + "\n```\nnever closed\n")
    assert load_audit().main(str(tmp_path)) == 1
    assert "odd code fences" in capsys.readouterr().out


def test_an_image_link_with_no_file_fails_the_audit(tmp_path, capsys) -> None:
    book = tmp_path / "book"
    shutil.copytree(os.path.join(ROOT, "examples", "output", "field-guide"), book)
    victim = sorted(book.glob("*.md"))[0]
    victim.write_text(victim.read_text() + "\n![a chart](images/missing.png)\n")
    assert load_audit().main(str(tmp_path)) == 1
    assert "image link with no file" in capsys.readouterr().out

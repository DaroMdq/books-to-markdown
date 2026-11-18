"""The bundled example is evidence, so it has to stay true.

`examples/field-guide.epub` is rebuilt from `examples/build_sample.py`, and
`examples/output/` is what the converter makes of it. If either drifts from the
code, these fail: a committed sample that the current code no longer produces
would be a claim nobody re-checked.
"""

from __future__ import annotations

import filecmp
import importlib.util
import os

from h2m.epub import main as convert_epub

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
SAMPLE = os.path.join(EXAMPLES, "field-guide.epub")
COMMITTED = os.path.join(EXAMPLES, "output", "field-guide")


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_sample", os.path.join(EXAMPLES, "build_sample.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_sample_epub_is_exactly_what_its_build_script_produces(tmp_path) -> None:
    rebuilt = load_builder().build(str(tmp_path / "field-guide.epub"))
    with open(rebuilt, "rb") as a, open(SAMPLE, "rb") as b:
        assert a.read() == b.read(), "run: python examples/build_sample.py"


def test_the_committed_output_is_exactly_what_the_converter_produces(tmp_path) -> None:
    # The same command the README shows, pointed at a scratch directory.
    convert_epub([SAMPLE, "-o", str(tmp_path), "--slug", "field-guide", "--code-lang", "python"])
    fresh = str(tmp_path / "field-guide")
    assert sorted(os.listdir(fresh)) == sorted(os.listdir(COMMITTED))
    _, mismatch, errors = filecmp.cmpfiles(
        COMMITTED, fresh, sorted(os.listdir(COMMITTED)), shallow=False
    )
    assert not mismatch and not errors, "regenerate examples/output (see examples/README.md)"

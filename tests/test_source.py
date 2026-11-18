"""The source itself: properties no single module's tests would notice.

The converters use C0 control characters as sentinels. Written as raw bytes
they are invisible in an editor, a diff and a terminal, and retyping the line
around one drops it without any visible change. They are written as named
escape sequences instead, and this keeps it that way.
"""

from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

# Every C0 control and DEL, except tab and newline.
RAW_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def test_no_source_file_contains_a_raw_control_character() -> None:
    found = []
    for dirpath, _, filenames in os.walk(SRC):
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    for m in RAW_CONTROL.finditer(line):
                        found.append("%s:%d: %r" % (os.path.relpath(path, ROOT), n, m.group()))
    assert not found, "write these as named escape sequences:\n" + "\n".join(found)

"""What both converters write their output with: filename slugs and YAML scalars."""

from __future__ import annotations

import re
import unicodedata


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

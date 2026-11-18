---
book: "A Field Guide to Plain Text"
author: "Sample Author"
identifier: "urn:uuid:5b0a6c1e-0000-4000-8000-000000000001"
published: "2026-01-01"
language: "en"
chapter: 2
title: "Measuring What Survives"
sections: 1
source_file: "chapter02.xhtml"
source_epub: "field-guide.epub"
words: 175
equations: 3
tables: 0
figures: 0
code_blocks: 1
code_lines: 4
pages: "3-4"
---
<!-- page 3 -->

# Chapter 2: Measuring What Survives

A conversion that looks right can still be short. The only way to know is
to compare the output against the source, character by character, after
removing everything that is allowed to change.

## The recovery figure

Write $S$ for the number of letters and digits in the
source and $M$ for the number that have no counterpart
in the output. The recovery figure is then

$$
R = 1 - \frac{M}{S}
$$

and it is a band rather than a grade, because page numbers and running
heads are removed on purpose and count as missing.

 <!-- page 4 -->

## Normalising both sides

Reflowing a paragraph moves spaces; healing a hyphenated word removes a
hyphen. Neither loses a letter, so both sides are reduced to letters and
digits before they are compared:

```python
import re

def normalise(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())
```

A gap of a few characters per page is a running head. A gap the size of a
paragraph is a bug.

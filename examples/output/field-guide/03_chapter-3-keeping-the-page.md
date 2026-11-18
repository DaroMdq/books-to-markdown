---
book: "A Field Guide to Plain Text"
author: "Sample Author"
identifier: "urn:uuid:5b0a6c1e-0000-4000-8000-000000000001"
published: "2026-01-01"
language: "en"
chapter: 3
title: "Keeping the Page"
sections: 1
source_file: "chapter03.xhtml"
source_epub: "field-guide.epub"
words: 143
equations: 0
tables: 0
figures: 0
code_blocks: 0
code_lines: 0
pages: "5-6"
---
<!-- page 5 -->

# Chapter 3: Keeping the Page

A citation points at a printed page. If the page numbers are thrown away
during conversion, every quotation taken from the output becomes impossible to
check against the book.1

## Markers that cost nothing

Each page break becomes an HTML comment. It is invisible when the Markdown
is rendered and easy to find with a search when a passage needs a page.

> Keep what the author wrote. Drop what the layout added. Say so
> when you cannot tell the difference.

## Checklist

- Convert the book.
- Run the verifier against the source.
- Read the longest gaps before trusting the percentage.

 <!-- page 6 -->

1. Some sources carry no page
markers at all. For those, the output simply has none, and the verifier says
so instead of inventing them.

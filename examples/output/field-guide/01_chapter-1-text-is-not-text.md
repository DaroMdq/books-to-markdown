---
book: "A Field Guide to Plain Text"
author: "Sample Author"
identifier: "urn:uuid:5b0a6c1e-0000-4000-8000-000000000001"
published: "2026-01-01"
language: "en"
chapter: 1
title: "Text Is Not Text"
sections: 1
source_file: "chapter01.xhtml"
source_epub: "field-guide.epub"
words: 240
equations: 0
tables: 1
figures: 0
code_blocks: 0
code_lines: 0
pages: "1-2"
---
<!-- page 1 -->

# Chapter 1: Text Is Not Text

A book on a screen looks like text. Underneath, it rarely is. A PDF stores
glyphs at coordinates and has no idea where a paragraph begins. An EPUB stores
markup, but each publishing tool writes its own dialect of it, and the dialect
decides what a program can recover.

## Three kinds of source

Most technical books arrive in one of three shapes. Each one hides its
structure in a different place.

| Source | Where structure lives | Typical trap |
| --- | --- | --- |
| Publisher EPUB | Tags and class names | Formulas shipped as images |
| Typeset PDF | Font sizes and positions | Running heads mixed into the text |
| PDF-derived EPUB | Almost nowhere | Every section is a top-level heading |

## What a reader needs

A person skims past a running head without noticing it. A language model
does not: it reads the header on every page as part of the argument. The job
of a converter is to keep what the author wrote and drop what the layout
added, and to say so when it cannot tell the two apart.

 <!-- page 2 -->

### A note on headings

Headings carry the outline of the book. When they are lost, a chapter
becomes one long paragraph and the reader loses the map along with it.

# Example

`field-guide.epub` is a three-chapter sample book written for this repository (original text, no third-party content). It is built by `build_sample.py` and carries the shapes the converter exists for: a heading hierarchy, page-break markers, a table, a code listing, MathML, a footnote, a block quote, and a contents page that is dropped as navigation.

`output/field-guide/` is what the converter makes of it:

```bash
python examples/build_sample.py      # rebuilds field-guide.epub, byte-identical
rm -rf examples/output
h2m epub examples/field-guide.epub -o examples/output --slug field-guide --code-lang python
h2m verify examples/field-guide.epub examples/output/field-guide
```

`tests/test_examples.py` fails if either file drifts from what the code produces.

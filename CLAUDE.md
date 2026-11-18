# CLAUDE.md

This repository is developed with AI coding agents (Claude Code) working under the rules below, with a human reviewing and committing. The file is written for the agent; it is kept in the repository because it is an honest description of how the code was made.

Read `README.md` for what the tool does, `docs/ARCHITECTURE.md` for where things live, and `docs/DECISIONS.md` before changing anything that looks arbitrary: its reason is there, numbered.

## The one rule

```bash
bin/check     # ruff check, ruff format --check, pytest
```

Green before committing. There is no "mostly green", and no explaining around a failure. Paste the output; do not summarise it.

## The failure mode this project is built around

Every real bug in this converter's history produced plausible output: a chapter 6,000 words short, an equation rendered as `M^'`, code listings flattened to one leading space, printed pages that could not be cited. None raised an error and all of them survived a read-through. So:

- **A word count is not evidence.** Compare against the source: `h2m verify BOOK OUT/SLUG`, and read the gaps, not just the percentage.
- **A test is not evidence until it has been watched failing.** Write the test first, watch it fail, then fix. For a guard, add a row to the mutation table in `docs/ROADMAP.md`: break the guard, watch the named test go red, revert.
- **A diff in converted output is not automatically a regression, but it must be explained** before it is committed.

## How work is done here

- Test first (`tests/conftest.py` builds synthetic EPUBs and PDFs in a publisher's *shape*; add a fixture rather than a real book).
- Debug a red test before proposing a fix: find the cause, not a patch that turns it green.
- Changes that affect output regenerate `examples/output/` (`h2m epub examples/field-guide.epub -o examples/output --slug field-guide --code-lang python`) and say why it changed; `tests/test_examples.py` fails until they do.
- No large refactors without the mutation table run around them.

## Conventions

- Commit messages in English, one line, imperative, saying what the system gains. History is linear.
- The source uses `%`-formatting and `l` for a `Line`. Both are deliberate and listed in `pyproject.toml`'s ruff ignore list with the reason attached. Anything added to that list gets a reason too.
- **The converters use control characters as sentinels.** In `epub.py`, `MARK` (`\x01`) delimits the placeholders for page markers, block equations, images, captions and parked code fences, and `BR` (`\x02`) stands for a `<br/>` inside a heading; `pdf.py` parks its code fences behind `\x01` the same way. They are always written as escape sequences, never as raw bytes, which are invisible in an editor, a diff and a terminal. `tests/test_source.py` fails if a raw control character other than tab or newline appears anywhere under `src/`.
- `bin/check` purges `__pycache__` before every run on purpose: CPython validates cached bytecode by mtime in whole seconds plus size, and a mutation pass produces exactly the same-size, sub-second edits that defeat that check.
- Never commit a real book or its converted output (`.gitignore` blocks `*.epub`, `*.pdf` and `out/`; the original sample in `examples/` is the one exception).

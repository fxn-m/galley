"""Small real Markdown documents for behavioural inspect tests."""

import json
import subprocess
from pathlib import Path
from typing import Any

RETAINED_EVIDENCE = """---
title: Retained Evidence
author: Ada Lovelace
---

# Heading One

Hello *world* with an ![alt fallback](figure.png) image.

> A quoted line.

- first item
- second item
"""

RETAINED_EVIDENCE_BASELINE = (
    "Heading One\n"
    "Hello world with an alt fallback image.\n"
    "A quoted line.\n"
    "first item\n"
    "second item\n"
)

UNTITLED = "Just one paragraph and nothing else.\n"

# An image alone on its own line, carrying a footnote in the words the author wrote. Pandoc's
# implicit figures turn those words into a caption; the note rides along with them. This route
# keeps implicit figures enabled, so both are reader-visible.
CAPTIONED_FIGURE = """---
title: A Captioned Figure
---

# A Captioned Figure

Ordinary prose before the picture, long enough to read as a real document rather than a fragment.

![A diagram of the loom[^n]](figure.png)

[^n]: The loom is the whole comparison.
"""

# Plain Markdown: headings and prose, carrying nothing the link, note, image or cover transforms
# would act on. The nested section exists so the profile's navigation depth is visible in the
# artifact: at the depth of one this shipped with it was excluded, and at three it is listed.
PLAIN_BOOK = """---
title: A Plain Book
author: Ada Lovelace
---

# Chapter One

Prose in the first chapter.

## A section inside it

More prose under the section.

# Chapter Two

Prose in the second chapter.
"""

# Pandoc closes the division implicitly and says so. The finished AST shows a closed division, so
# nothing in it records that the source never closed one.
UNCLOSED_DIVISION = "Body text.\n\n<div>\n\nStill inside.\n"

# Every constructor Pandoc's Markdown reader can produce that sits outside the Modelled Set:
# Table, Strikeout, Math, RawInline, RawBlock, LineBlock, Cite and Underline.
OUTSIDE_THE_MODELLED_SET = """# Carried Through

| a | b |
|---|---|
| 1 | 2 |

Prose with ~~strikeout~~, $E=mc^2$, [@knuth1984] and [underlined]{.underline}
alongside <em>raw</em> markup.

| line one
| line two

<table><tr><td>raw block</td></tr></table>
"""


# Every constructor the Modelled Set names. The survey proves each one is present; the words below
# prove that those carrying text reach the Preservation Baseline rather than falling through the
# reader in silence. Space, SoftBreak, LineBreak and HorizontalRule carry no word of their own.
INSIDE_THE_MODELLED_SET = """# Headingword

Paraword with *emphword*, **strongword**, ^superword^, ~subword~,
[smallword]{.smallcaps}, "quotedword", `codeword`, [linkword](https://e.com),
[spanword]{#anchor} and a noteword.[^1] A break\\
lands here.

[^1]: Footword in the note.

> Quoteword in a block.

- Bulletword

1. Orderword

Termword
:   Definitionword.

```
Blockword
```

---

::: {.divclass}
Divword inside a division.
:::

![Figureword](figure.png)
"""

MODELLED_WORDS = (
    "Headingword",
    "Paraword",
    "emphword",
    "strongword",
    "superword",
    "subword",
    "smallword",
    "quotedword",
    "codeword",
    "linkword",
    "spanword",
    "noteword",
    "Footword",
    "Quoteword",
    "Bulletword",
    "Orderword",
    "Termword",
    "Definitionword.",
    "Blockword",
    "Divword",
    "Figureword",
)


# Pandoc's writers put metadata on the page, so a struck-through title reaches the book exactly
# as a struck-through paragraph does.
STRUCK_THROUGH_TITLE = """---
title: A ~~struck~~ title
---

Ordinary body text.
"""


# Two recorded in-book links in one block, one excluded scheme, a note carrying its own link, an
# identifier, an image and a long in-book target.
PROJECTED_NAVIGATION = """# Linked {#top}

A paragraph with [one](#top), [two](chapter-two.xhtml#a-fairly-long-fragment-name-here) and
[three](https://example.com/outside) plus an ![alt](x.png) image and a note.[^n]

[^n]: The note has [its own link](#top).
"""

# One document reaching all five Link Kinds. It carries a note, so its Footnote Apparatus is
# recognised: the marked reference is a footnote reference and everything else may be stripped.
MIXED_LINKS = """# Linked {#top}

A paragraph with [inbound](#top), [broken](chapter-two.xhtml#absent) and
[outbound](https://example.com/outside) plus a note.[^n]

An [](#top) empty anchor beside a [notelike](#top){role="doc-noteref"} reference
and a [labelled](#top){#anchored} cross-reference.

[^n]: The note carries [its own link](#top).
"""

# The same link shapes with no note anywhere. Nothing distinguishes a hidden footnote reference
# from an ordinary cross-reference here, which is the state the link interlock exists for.
NOTELIKE_WITHOUT_NOTES = """# Anchored {#top}

A [notelike](#top){role="doc-noteref"} reference and a [plain](#top) cross-reference,
beside [outbound](https://example.com/away) and [broken](missing.xhtml#gone).
"""

# One note in every block structure Pandoc's Markdown reader can put one in, including a figure
# caption, which the AST duplicates into the image description. The second note is multi-paragraph.
NOTE_POSITIONS = """# Head with a note[^h]

Para note.[^p]

> Quote note.[^q]

- Item note.[^i]

Termword[^t]
:   Definition note.[^d]

| a | b |
|---|---|
| Cell note.[^c] | x |

![Figure caption note.[^f]](figure.png)

::: {.wrap}
Div note.[^v]
:::

[^h]: Headword body.
[^p]: Paraword body.

    Second paragraph of the note.
[^q]: Quoteword body.
[^i]: Itemword body.
[^t]: Termword body.
[^d]: Definitionword body.
[^c]: Cellword body.
[^f]: Figureword body.
[^v]: Divword body.
"""

# A list that restarts and a list that is not decimal; both carry numbering a bare list loses.
RENUMBERED_LISTS = """Intro.

7. seven
8. eight

Between.

i. first roman
ii. second roman
"""

# One codepoint the profile names as unrenderable, and two elements marked as page breaks.
MARKED_CONTENT = """Return arrow \u21a9 and a box \u251c drawing.

::: {.pagebreak}
Content inside a page break.
:::

[marker]{epub:type="pagebreak"}
"""

# One of each construct CrossPoint destroys — strikeout (A5), code block (A4), table (A3) — with
# the title struck as well as the prose, since `meta` reaches the panel as the body does.
DESTROYED_STRUCTURE = """---
title: A ~~Retracted~~ Price
---

# Retracted

~~Ninety-nine~~ seventy-nine is the price, and the retraction is the whole point.

```python
def cache(request):
    return request
```

| Fruit | Colour |
|-------|--------|
| Apple | Green  |
"""


def blocked_links(count: int, *, note: bool = False) -> str:
    """One paragraph carrying `count` recorded in-book links, for the block ceiling.

    Every link resolves to an anchor the document already carries, so nothing here is a dead link.
    Adding a note gives the document a Footnote Apparatus, which makes preparation strip
    cross-references and removes the projection's floor.
    """

    links = " ".join(f"[l{index}](#top)" for index in range(count))
    apparatus = "\nA paragraph with a note.[^n]\n\n[^n]: The note body.\n" if note else ""
    return f"# Anchored {{#top}}\n\nPara with {links} inside.\n{apparatus}"


def write_markdown(path: Path, text: str = RETAINED_EVIDENCE) -> Path:
    """Write one UTF-8 Markdown source and return its path."""

    _ = path.write_text(text, encoding="utf-8")
    return path


def native_ast(source: Path) -> Any:
    """Parse one source with the same pinned Pandoc, independently of Galley."""

    completed = subprocess.run(
        ["pandoc", "--from", "markdown", "--to", "json", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)

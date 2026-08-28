"""Stop printing the figure caption Pandoc derived from an alt the document already repeats.

An image alone in a paragraph becomes one of Pandoc's implicit figures, and the writer copies the
image's alt text into a `<figcaption aria-hidden="true">`. The `aria-hidden` keeps a screen reader
from hearing the words twice, having already had them as the alt; it does nothing for a panel,
which renders the caption and then renders the document's own paragraph saying the same thing
directly beneath it. `The Scaling Hypothesis` prints every one of its nine figures that way, and a
reader on the device saw it before any measurement did.

The alt attribute is untouched, so nothing an assistive technology reads changes -- and that is
also why Text Preservation does not move. A built book's reader-visible text counts an image's alt
as the fallback the device shows in its place, and `document/baseline.py` already declines to count
Pandoc's derived caption for the same reason this pass declines to print it. Both sides hold the
words twice before, and both hold them twice after; only the third copy on the panel goes.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

from galley.document.baseline import block_segments, inline_text
from galley.json_reading import mapping, sequence, text
from galley.report.quantities import quantity

DUPLICATE_CAPTIONS = "duplicate-caption-suppression"
CAPTION_NOTE = (
    "Pandoc's implicit figures copy an image's alt text into the caption, and these documents "
    "already print those words as the paragraph that follows. Only the derived caption is "
    "suppressed, and only where caption, alt and that paragraph are the same text once "
    "whitespace is removed. The alt attribute is unchanged, and the words stay in the book."
)
# Pandoc's empty Caption: no short caption, no blocks. The writer then emits the figure with its
# image and no `figcaption` at all, rather than an empty one.
EMPTY_CAPTION: list[object] = [None, []]


@dataclass(frozen=True)
class Captions:
    """One suppression pass: the document it produced, and every caption it stopped printing."""

    ast: dict[str, object]
    suppressed: list[str] = field(default_factory=list[str])

    @property
    def fired(self) -> bool:
        return bool(self.suppressed)


def suppress_derived_captions(ast: dict[str, object]) -> Captions:
    """Rebuild the document with an empty caption on every figure the document repeats itself."""

    duplicates = _duplicates(ast)
    if not duplicates:
        return Captions(ast=ast)
    return Captions(
        ast=cast(dict[str, object], _rebuilt(ast, duplicates)),
        suppressed=sorted(duplicates.values()),
    )


def derived_figure_captions(blocks: Sequence[object]) -> set[int]:
    """Index every figure in one block sequence whose caption the next paragraph already prints.

    Caption equal to alt says only that Pandoc derived the caption; the paragraph is what says
    the document already prints those words, and both clauses are needed. `Design Graveyard` has
    one figure that passes the first and fails the second -- a Pandoc caption over a paragraph
    saying something else -- and nothing but the caption carries its words.

    Whitespace is removed before comparing because the two copies reach the AST down different
    paths: one straight out of an attribute, one through an HTML-to-Markdown conversion that
    spaced its inline elements, so gwern.net writes `(LeCun 2019)` in the alt and `( LeCun 2019 )`
    in the prose. Nothing else is relaxed. This is equality rather than similarity, so a caption
    the paragraph merely begins, or repeats but for one word, is text the document does not carry
    twice.
    """

    printed: set[int] = set()
    for index, block in enumerate(blocks):
        node = mapping(block)
        following = mapping(blocks[index + 1]) if index + 1 < len(blocks) else {}
        if text(node.get("t")) != "Figure" or text(following.get("t")) != "Para":
            continue
        content = sequence(node.get("c"))
        images = _compact(block_segments(sequence(content[2])))
        caption = _compact(block_segments(sequence(sequence(content[1])[1])))
        paragraph = _compact([inline_text(sequence(following.get("c")))])
        if images and images == caption == paragraph:
            printed.add(index)
    return printed


def _compact(segments: Sequence[str]) -> str:
    """Join one rendering with every whitespace character removed, ready to compare exactly."""

    return "".join("".join(segments).split())


def _duplicates(value: object) -> dict[int, str]:
    """Name every figure in the tree whose caption the next paragraph prints, by node identity.

    The rule reads one block sequence at a time, and a figure is a duplicate only of the sibling
    that follows it -- a paragraph outside the figure's own container is a different part of the
    document, whatever it says. Walking by identity rather than by index is what lets one pass
    find figures at every depth and still rebuild exactly those nodes.
    """

    if isinstance(value, list):
        items = cast(list[object], value)
        # The figure's own baseline rendering is its alt text, and the caption is Pandoc's
        # verbatim copy of that, so this is the line that stopped being printed.
        found = {
            id(items[index]): "".join(block_segments([items[index]]))
            for index in derived_figure_captions(items)
        }
        return found | {
            identity: caption for item in items for identity, caption in _duplicates(item).items()
        }
    if not isinstance(value, dict):
        return {}
    return {
        identity: caption
        for item in cast(dict[str, object], value).values()
        for identity, caption in _duplicates(item).items()
    }


def _rebuilt(value: object, duplicates: dict[int, str]) -> object:
    """Rebuild the tree, emptying the caption of each figure the pass named."""

    if isinstance(value, list):
        return [_rebuilt(item, duplicates) for item in cast(list[object], value)]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    if id(node) not in duplicates:
        return {key: _rebuilt(item, duplicates) for key, item in node.items()}
    content = sequence(node.get("c"))
    emptied: list[object] = [content[0], EMPTY_CAPTION, _rebuilt(content[2], duplicates)]
    return {**node, "c": emptied}


def caption_transform(captions: Captions) -> dict[str, object]:
    """State how many derived captions stopped being printed, and what each of them said.

    Named rather than counted, for the same reason a dropped raw payload is: a reader who finds a
    caption missing needs to be able to check that the one that went is the one the paragraph
    beneath the image already carried.
    """

    return {
        "name": DUPLICATE_CAPTIONS,
        "fired": captions.fired,
        "suppressed": quantity(len(captions.suppressed), "captions"),
        "captions": list(captions.suppressed),
        "note": CAPTION_NOTE,
    }

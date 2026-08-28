"""Give a callout's title back the prominence Defuddle's normalisation took off it.

jxnl.co is MkDocs Material, and the page carries its admonition titles as
`<p class="admonition-title">`. Pandoc would have carried that paragraph through. Defuddle
rewrites it -- the pinned extractor turns twelve admonitions into twelve `callout` divs and zero
admonitions -- and what it writes instead is bare nested `<div>`s, which Pandoc's EPUB writer
renders as nothing at all. So the title arrives on the panel as a line of body text sitting above
other body text, and every bit of its standing was in a stylesheet the book does not carry.

`callout` is therefore not a vendor's class name. It is the pinned extractor's own normalised
output, the same contract Galley already reads for `content`, `title`, `author` and `language`,
and matching it is no more a guess than matching any of those.

The title becomes a paragraph with a `Strong` in it, which is almost exactly what the page carried
before the extractor touched it. Never a `Header`: `nav-membership-drives-pagination` is a
device-test claim at firmware 1.4.1, page breaks follow navigation membership, and twelve titles
promoted to headings would put twelve page breaks into one book. Never a blockquote either --
real quotations in that document already are blockquotes and render correctly, so borrowing their
indentation would make two different things look identical.
"""

from dataclasses import dataclass, field
from typing import cast

from galley.document.baseline import inline_text
from galley.json_reading import mapping, sequence, text
from galley.report.quantities import quantity

CALLOUT_TITLES = "callout-title-emphasis"
TITLE = "callout-title"
INNER = "callout-title-inner"
CALLOUT_NOTE = (
    "A callout's title reaches Galley as bare nested divs, which an EPUB writer renders as "
    "nothing and a panel shows as ordinary body text. Each one named here became a paragraph "
    "holding a Strong. No heading is emitted, because page breaks on this device follow "
    "navigation membership, and no blockquote, because real quotations already are blockquotes."
)


@dataclass(frozen=True)
class Callouts:
    """One emphasis pass: the document it produced, and every title it gave standing back to."""

    ast: dict[str, object]
    emphasised: list[str] = field(default_factory=list[str])

    @property
    def fired(self) -> bool:
        return bool(self.emphasised)


def emphasise_callout_titles(ast: dict[str, object]) -> Callouts:
    """Rebuild the document with every recognised callout title as an emphasised paragraph."""

    titles = _titles(ast)
    if not titles:
        return Callouts(ast=ast)
    return Callouts(
        ast=cast(dict[str, object], _rebuilt(ast, titles)),
        emphasised=sorted(titles.values()),
    )


def title_inlines(node: dict[str, object]) -> list[object] | None:
    """Read the one line of inline content a recognised callout title holds, or nothing.

    The shape is matched exactly and nothing near it is: a title holding no block, more than one
    block, or something other than a single `Plain` is a callout Galley has not seen, and a
    `callout-title-inner` standing on its own is not a title at all. Guessing at any of those
    would be reading a structure this extractor is not known to emit.
    """

    if TITLE not in _classes(node):
        return None
    blocks = sequence(_item(node.get("c"), 1))
    inner = mapping(blocks[0]) if len(blocks) == 1 else {}
    if INNER not in _classes(inner):
        return None
    held = sequence(_item(inner.get("c"), 1))
    line = mapping(held[0]) if len(held) == 1 else {}
    return sequence(line.get("c")) if text(line.get("t")) == "Plain" else None


def _classes(node: dict[str, object]) -> list[object]:
    """Name the classes one Div carries, and nothing for a node that is not one."""

    attr = _item(node.get("c"), 0)
    return list(sequence(_item(attr, 1))) if text(node.get("t")) == "Div" else []


def _item(content: object, index: int) -> object:
    items = sequence(content)
    return items[index] if index < len(items) else None


def _titles(value: object) -> dict[int, str]:
    """Name every recognised callout title in the tree, by node identity."""

    if isinstance(value, list):
        return {
            identity: title
            for item in cast(list[object], value)
            for identity, title in _titles(item).items()
        }
    if not isinstance(value, dict):
        return {}
    node = cast(dict[str, object], value)
    inlines = title_inlines(node)
    if inlines is not None:
        return {id(node): _rendered(inlines)}
    return {identity: title for item in node.values() for identity, title in _titles(item).items()}


def _rendered(inlines: list[object]) -> str:
    """Render one title as the words it says, for the Report to name it by."""

    return inline_text(inlines)


def _rebuilt(value: object, titles: dict[int, str]) -> object:
    """Rebuild the tree, replacing each named title with one emphasised paragraph."""

    if isinstance(value, list):
        return [_rebuilt(item, titles) for item in cast(list[object], value)]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    if id(node) not in titles:
        return {key: _rebuilt(item, titles) for key, item in node.items()}
    inlines = title_inlines(node) or []
    return {"t": "Para", "c": [{"t": "Strong", "c": inlines}]}


def callout_transform(callouts: Callouts) -> dict[str, object]:
    """State how many callout titles were given standing back, and what each of them says."""

    return {
        "name": CALLOUT_TITLES,
        "fired": callouts.fired,
        "emphasised": quantity(len(callouts.emphasised), "titles"),
        "titles": list(callouts.emphasised),
        "note": CALLOUT_NOTE,
    }

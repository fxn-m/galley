"""Namespace the source attributes an EPUB3 content document would not admit.

One observed page built a book EPUBCheck rejected: `<table width="100%">`, where `width` is legal
on an image and illegal on a table. Pandoc's HTML reader keeps a source element's unmodelled
attributes in the node's `Attr` key-values and its EPUB3 writer emits them, and the reader cannot
filter them because it does not know which element the writer will produce. So this is the only
place the join can be made.

Raw-HTML balancing does not reach it. This is a modelled `Table` rather than raw HTML, and the
chapter it produces is also perfectly
well-formed XML, so `malformed-content-document` cannot see it either. **Well-formed and invalid**
is the state nothing else here catches.

Nothing is dropped and nothing is decided. An attribute the element does not admit is emitted
under the format's own `data-` prefix, which is exactly what Pandoc already does for every name
its own list does not recognise — `align`, `cellpadding` and `bgcolor` off that same table all
arrive as `data-*`. Galley completes that rescue rather than choosing what is worth keeping.
"""

from dataclasses import dataclass, field
from typing import cast

from galley.json_reading import sequence, text
from galley.release_data import XHTML_ATTRIBUTES, ElementRule, attribute_rules
from galley.report.quantities import quantity

ATTRIBUTE_NAMESPACING = "attribute-namespacing"
DATA_PREFIX = "data-"
GLOBAL, PREFIXES, ELEMENTS = attribute_rules(XHTML_ATTRIBUTES)
NAMESPACING_NOTE = (
    "An EPUB3 content document is XHTML, so an attribute the profile does not admit on the "
    "element it lands on makes the book invalid. One that is not admitted is emitted under the "
    "format's own `data-` prefix rather than verbatim or not at all, so the source still states "
    "what it stated. An attribute carries no reader-visible text; Text Preservation proves it."
)


@dataclass(frozen=True)
class Namespacing:
    """One pass: the document it produced, and every attribute it had to rename to produce it."""

    ast: dict[str, object]
    renamed: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    """Each rename as the constructor it came off, the element that rejects it, and the name."""

    @property
    def fired(self) -> bool:
        return bool(self.renamed)


def namespace_attributes(ast: dict[str, object]) -> Namespacing:
    """Rebuild the document with every attribute the writer's element will actually admit."""

    renamed: list[dict[str, str]] = []
    rebuilt = cast(dict[str, object], _rebuilt(ast, renamed))
    return Namespacing(ast=rebuilt, renamed=renamed)


def _rebuilt(value: object, renamed: list[dict[str, str]]) -> object:
    if isinstance(value, list):
        return [_rebuilt(item, renamed) for item in cast(list[object], value)]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    walked = {key: _rebuilt(item, renamed) for key, item in node.items()}
    return _attributed(walked, renamed)


def _attributed(node: dict[str, object], renamed: list[dict[str, str]]) -> dict[str, object]:
    """Rename whatever one node's own `Attr` states that its element does not admit."""

    constructor = text(node.get("t")) or ""
    rule = ELEMENTS.get(constructor)
    content = sequence(node.get("c"))
    if rule is None or len(content) <= rule.position:
        return node
    attributes = sequence(content[rule.position])
    if len(attributes) != 3:
        return node
    pairs = [sequence(pair) for pair in sequence(attributes[2])]
    # A pair this walk cannot read is carried through untouched rather than dropped. Pandoc emits
    # nothing but `[name, value]`, so this cannot fire — but "nothing the source stated is lost"
    # has to hold for what the code does not understand as much as for what it does.
    replaced = [
        [_renamed(text(pair[0]) or "", rule, constructor, renamed), *pair[1:]]
        if len(pair) == 2
        else pair
        for pair in pairs
    ]
    if replaced == pairs:
        return node
    rebuilt: list[object] = [attributes[0], attributes[1], replaced]
    return {**node, "c": [*content[: rule.position], rebuilt, *content[rule.position + 1 :]]}


def _renamed(name: str, rule: ElementRule, constructor: str, renamed: list[dict[str, str]]) -> str:
    """Give one attribute the name the element will admit, recording it where it had to change."""

    if name in GLOBAL or name in rule.attributes or name.startswith(PREFIXES):
        return name
    renamed.append({"constructor": constructor, "element": rule.element, "attribute": name})
    return f"{DATA_PREFIX}{name}"


def attribute_transform(namespacing: Namespacing) -> dict[str, object]:
    """State every attribute that had to be namespaced, and the element that would not take it.

    Named rather than counted. A reader checking a book against its source needs to know which
    attribute moved off which element, and "one attribute was namespaced" cannot answer that.
    """

    return {
        "name": ATTRIBUTE_NAMESPACING,
        "fired": namespacing.fired,
        "renamed": list(namespacing.renamed),
        "count": quantity(len(namespacing.renamed), "attributes"),
        "note": NAMESPACING_NOTE,
    }

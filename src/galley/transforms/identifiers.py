"""Make the identifiers a book's own navigation points at complete, unique and short enough.

All three properties fail for the same reason: the section Pandoc's EPUB3 writer invents from the
stated title is named at write time, after everything Galley can see has already happened.

**Short enough.** CrossPoint truncates an over-long href, finds no anchor, and lands the reader at
the top of the chapter instead of at the thing they tapped — `footnote-href-length`, whose
rationale said Galley "stays under this by construction". It did not. A navigation entry is
`text/chNNN.xhtml#<identifier>` and the identifier was a slug of the heading, so an href's length
was a property of the document's own words.

**Complete.** The writer synthesises that section only when the document's first block is not a
wrapper. An extracted document arriving inside a `<div>` gets none, and where the profile's
navigation depth admits level-1 headings alone, the book's navigation document is an empty `<ol>`
— no entries, and on a device whose page breaks follow navigation membership, no page breaks.

**Unique.** When the writer does synthesise the section it slugs the title, after Pandoc's HTML
reader has already assigned and de-duplicated every other identifier in the document. It therefore
takes part in no de-duplication, and an article whose first heading repeats its title ends up with
two elements answering to one identifier.

Writing the heading here settles all three at once: the section always exists, its identifier is
Galley's rather than a slug of anybody's words, and both are inside the budget. A document that
already leads with a level-1 heading needs none of it — the writer synthesises nothing, and the
heading carries an identifier the bounding pass can reach.

Nothing here is reader-visible. An identifier is not a word: Text Preservation is what proves it.
"""

from dataclasses import dataclass, field
from hashlib import sha256
from typing import cast

from galley.json_reading import mapping, sequence, text
from galley.report.quantities import quantity

# Where each node type Pandoc gives an `Attr` keeps it. A document can carry an identifier on any
# of these and a link can point at any of them, so all of them are bounded rather than headings
# alone — the defect is the length of an href, not the kind of thing it reaches.
ATTRIBUTED = {
    "Header": 1,
    "Div": 0,
    "Span": 0,
    "CodeBlock": 0,
    "Code": 0,
    "Table": 0,
    "Figure": 0,
    "Image": 0,
    "Link": 0,
}
HEADER = "Header"
LINK = "Link"
# What the writer puts in front of an identifier, at its longest: `text/`, `ch`, five digits of
# chapter number, `.xhtml` and the `#`. Galley does not choose this — Pandoc's EPUB3 writer names
# its own content documents — so a test measures it against a built book rather than trusting it.
PATH_RESERVE = len("text/ch00000.xhtml#")
# How much of a bounded identifier is the disambiguating tail. Two identifiers whose text truncates
# alike would otherwise become one target, and a reader tapping either would reach whichever the
# writer wrote first.
DIGEST_LENGTH = 8
TITLE_PREFIX = "galley-"
IDENTIFIER_BOUNDING = "identifier-bounding"
BOUNDING_NOTE = (
    "Every identifier the writer receives fits the Device Profile's recorded href limit once the "
    "writer's own path prefix is allowed for, so the length of a navigation entry is a property "
    "of Galley's naming rather than of the document's words. An identifier carries no "
    "reader-visible text; Text Preservation is what proves the rewrite moved none."
)
BOUNDING_ABSENT = (
    "This Device Profile records no enforced href limit, so Galley bounds nothing and states no "
    "budget it did not get from profile data. The title heading is still written, because a book "
    "with no navigation entry is wrong under every profile."
)


@dataclass(frozen=True)
class Bounding:
    """One bounding pass: the document it produced, and what it had to change to produce it."""

    ast: dict[str, object]
    budget: int | None
    rewritten: dict[str, str] = field(default_factory=dict[str, str])
    titled: str | None = None
    """The identifier given to a heading the document did not carry, where one was needed."""

    @property
    def fired(self) -> bool:
        return bool(self.rewritten) or self.titled is not None


def bound_identifiers(ast: dict[str, object], *, limit: int | None, title: str) -> Bounding:
    """Rebuild the document with the identifiers the writer receives complete and inside budget.

    The title heading is written whatever the profile says, because a book with no navigation
    entry and a book with one identifier twice are wrong under every profile. Only the bounding
    pass needs a limit, and a profile that records none leaves Pandoc's own lengths to stand.
    """

    headed, titled = _titled(ast, title=title)
    if limit is None:
        return Bounding(ast=headed, budget=None, titled=titled)
    budget = limit - PATH_RESERVE
    rewritten = {
        identifier: _bounded(identifier, budget)
        for identifier in _identifiers(headed.get("blocks"))
        if len(identifier.encode("utf-8")) > budget
    }
    rebuilt = cast(dict[str, object], _rewritten(headed, rewritten)) if rewritten else headed
    return Bounding(ast=rebuilt, budget=budget, rewritten=rewritten, titled=titled)


def _titled(ast: dict[str, object], *, title: str) -> tuple[dict[str, object], str | None]:
    """Give the document the leading heading the writer would otherwise invent for itself.

    Wherever the document has none. The condition used to be "only where the title cannot fit",
    which left the writer to invent a section for every other book — and the section it invents is
    sometimes absent and never de-duplicated, which is two defects rather than a tolerable one.

    The identifier is Galley's namespace and a digest of the title rather than a slug, so it is
    not a name the document's own words can produce. That matters because the writer de-duplicates
    nothing it is handed: a slug computed here could collide with one Pandoc's reader already
    assigned, and neither Galley nor the writer would notice.
    """

    blocks = sequence(ast.get("blocks"))
    if _leading_header(blocks):
        return ast, None
    identifier = f"{TITLE_PREFIX}{sha256(title.encode('utf-8')).hexdigest()[:DIGEST_LENGTH]}"
    attributes: list[object] = [identifier, [], []]
    inlines: list[object] = [{"t": "Str", "c": title}]
    heading: dict[str, object] = {"t": HEADER, "c": [1, attributes, inlines]}
    return {**ast, "blocks": [heading, *blocks]}, identifier


def _leading_header(blocks: list[object]) -> bool:
    """Say whether the writer already has a level-1 heading to name the first section after."""

    first = mapping(blocks[0]) if blocks else {}
    return text(first.get("t")) == HEADER and sequence(first.get("c"))[:1] == [1]


def _bounded(identifier: str, budget: int) -> str:
    """Shorten one identifier to the budget, keeping enough of it to still read as itself."""

    tail = f"-{sha256(identifier.encode('utf-8')).hexdigest()[:DIGEST_LENGTH]}"
    if budget <= len(tail):
        return tail[1:][:budget]
    head = identifier.encode("utf-8")[: budget - len(tail)].decode("utf-8", "ignore")
    return f"{head}{tail}"


def _identifiers(value: object) -> list[str]:
    """Every identifier this tree carries, in reading order and without repetition."""

    found: list[str] = []
    for identifier in _walk(value):
        if identifier and identifier not in found:
            found.append(identifier)
    return found


def _walk(value: object) -> list[str]:
    if isinstance(value, list):
        return [found for item in cast(list[object], value) for found in _walk(item)]
    if not isinstance(value, dict):
        return []
    node = cast(dict[str, object], value)
    stated = _stated(node)
    nested = [found for item in node.values() for found in _walk(item)]
    return nested if stated is None else [stated, *nested]


def _stated(node: dict[str, object]) -> str | None:
    """Read one node's own identifier, wherever its type keeps its `Attr`."""

    position = ATTRIBUTED.get(text(node.get("t")) or "")
    content = sequence(node.get("c"))
    if position is None or len(content) <= position:
        return None
    attributes = sequence(content[position])
    return text(attributes[0]) if attributes else None


def _rewritten(value: object, rewritten: dict[str, str]) -> object:
    """Rebuild the tree with each bounded identifier replaced, and every link that reached it."""

    if isinstance(value, list):
        return [_rewritten(item, rewritten) for item in cast(list[object], value)]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    rebuilt = {key: _rewritten(item, rewritten) for key, item in node.items()}
    reidentified = _reidentified(rebuilt, rewritten)
    return _relinked(reidentified, rewritten) if text(node.get("t")) == LINK else reidentified


def _reidentified(node: dict[str, object], rewritten: dict[str, str]) -> dict[str, object]:
    """Replace one node's own identifier, leaving its classes and key-value pairs alone."""

    identifier = _stated(node)
    if identifier is None or identifier not in rewritten:
        return node
    position = ATTRIBUTED[text(node.get("t")) or ""]
    content = sequence(node.get("c"))
    replaced = [rewritten[identifier], *sequence(content[position])[1:]]
    return {**node, "c": [*content[:position], replaced, *content[position + 1 :]]}


def _relinked(node: dict[str, object], rewritten: dict[str, str]) -> dict[str, object]:
    """Point one same-document link at the identifier its target now carries."""

    content = sequence(node.get("c"))
    target = sequence(content[2]) if len(content) > 2 else []
    href = text(target[0]) if target else None
    if href is None or not href.startswith("#") or href[1:] not in rewritten:
        return node
    replaced = [f"#{rewritten[href[1:]]}", *target[1:]]
    return {**node, "c": [*content[:2], replaced, *content[3:]]}


def identifier_transform(bounding: Bounding) -> dict[str, object]:
    """State what the identifier budget was and every identifier that had to change to meet it.

    The rewritten identifiers are named rather than counted. A reader checking a book against its
    source needs to know which anchor became which, and "three identifiers were shortened" cannot
    answer that.
    """

    return {
        "name": IDENTIFIER_BOUNDING,
        "fired": bounding.fired,
        "budget": None if bounding.budget is None else quantity(bounding.budget, "bytes"),
        "rewritten": dict(bounding.rewritten),
        "title_heading": bounding.titled,
        "note": BOUNDING_ABSENT if bounding.budget is None else BOUNDING_NOTE,
    }

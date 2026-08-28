"""Measure a Canonical Document the way a reader meets it, before any profile transform.

Everything here is taken from the AST alone. It is what `inspect` can honestly know before an
EPUB exists, and it is the evidence both the projections and the source-side observations rest
on. Nothing in this module reads a Device Profile.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from galley.document.baseline import inline_text
from galley.json_reading import integer, mapping, sequence, text

# A reading block is a leaf block: the innermost thing a reader meets as one run of prose. Every
# other block contains blocks, and a Note's blocks become their own files under one-file-per-note.
LEAF_BLOCKS = frozenset({"CodeBlock", "Header", "LineBlock", "Para", "Plain"})
BLOCK_CONTENT = {"BlockQuote": None, "Div": 1}
ITEM_CONTENT = {"BulletList": None, "OrderedList": 1}
DECIMAL_STYLES = frozenset({"Decimal", "DefaultStyle"})
DEFAULT_START = 1
ATTRIBUTED = {"Div": 0, "Span": 0, "Header": 1, "Code": 0, "Image": 0, "Link": 0}


@dataclass(frozen=True)
class ReadingRule:
    """Everything a Device Profile states about how to read a source, gathered once.

    The link counting rule and page-break markers are device facts held in profile data; this
    module applies them and states none of its own.
    """

    excluded_schemes: frozenset[str]
    requires_visible_text: bool
    page_break_markers: frozenset[str]
    page_break_attributes: frozenset[str]


@dataclass(frozen=True)
class SourceLink:
    """One `Link` inline and what a Device Profile would do with its target."""

    target: str
    text: str
    href_bytes: int
    external: bool
    recorded: bool


@dataclass
class SourceMeasurement:
    """Everything one pass over a Canonical Document established."""

    links: list[SourceLink] = field(default_factory=list[SourceLink])
    recorded_per_block: list[int] = field(default_factory=list[int])
    identifiers: list[str] = field(default_factory=list[str])
    notes: int = 0
    images: int = 0
    heading_levels: list[int] = field(default_factory=list[int])
    ordered_lists: int = 0
    images_without_alt: int = 0
    page_breaks: list[str] = field(default_factory=list[str])
    renumbered_lists: list[str] = field(default_factory=list[str])

    @property
    def blocks(self) -> int:
        return len(self.recorded_per_block)

    @property
    def max_recorded_per_block(self) -> int:
        return max(self.recorded_per_block, default=0)

    @property
    def recorded(self) -> list[SourceLink]:
        return [link for link in self.links if link.recorded]

    @property
    def max_recorded_href_bytes(self) -> int:
        return max((link.href_bytes for link in self.recorded), default=0)

    @property
    def unresolved_recorded(self) -> list[SourceLink]:
        """Recorded links whose target this document cannot be shown to satisfy.

        A dead link is stripped unconditionally, so an unresolved recorded link is exactly the
        case where the built artifact carries fewer links than the source.
        """

        known = frozenset(self.identifiers)
        return [link for link in self.recorded if not resolves_in_document(link.target, known)]


def measure_source(ast: dict[str, object], rule: ReadingRule) -> SourceMeasurement:
    """Walk one AST's blocks, recording each reading block and everything inside it."""

    measurement = SourceMeasurement()
    _blocks(sequence(ast.get("blocks")), "/blocks", measurement, rule)
    return measurement


def resolves_in_document(target: str, known: frozenset[str]) -> bool:
    """Say whether a target certainly names something this document already carries.

    One definition serves both the reading that projects and the transform that strips, so a
    link cannot be counted as resolving by one and as dead by the other.
    """

    path, _, fragment = target.strip().partition("#")
    return not path and bool(fragment) and fragment in known


def _blocks(
    blocks: Sequence[object], pointer: str, measurement: SourceMeasurement, rule: ReadingRule
) -> None:
    for index, value in enumerate(blocks):
        _block(mapping(value), f"{pointer}/{index}", measurement, rule)


def _block(
    node: dict[str, object], pointer: str, measurement: SourceMeasurement, rule: ReadingRule
) -> None:
    kind = text(node.get("t")) or ""
    content = node.get("c")
    _attributes(kind, node, pointer, measurement, rule)
    if kind == "Header":  # the level, not the count: extraction demotes headings routinely
        measurement.heading_levels.append(integer(_at(content, 0)) or 0)
    if kind in LEAF_BLOCKS:
        _reading_block(kind, content, pointer, measurement, rule)
        return
    if kind in BLOCK_CONTENT:
        _blocks(sequence(_at(content, BLOCK_CONTENT[kind])), f"{pointer}/c", measurement, rule)
        return
    if kind == "Figure":
        # A Figure holds blocks in two places, and its caption is as readable as its content.
        _blocks(sequence(_at(_at(content, 1), 1)), f"{pointer}/c/1/1", measurement, rule)
        _blocks(sequence(_at(content, 2)), f"{pointer}/c/2", measurement, rule)
        return
    if kind in ITEM_CONTENT:
        _items(_at(content, ITEM_CONTENT[kind]), f"{pointer}/c", measurement, rule)
        if kind == "OrderedList":
            measurement.ordered_lists += 1
            _numbering(content, pointer, measurement)
        return
    if kind == "DefinitionList":
        _definitions(content, f"{pointer}/c", measurement, rule)
        return
    if kind == "Table":
        _blocks(_nested_blocks(content), f"{pointer}/c", measurement, rule)


def _reading_block(
    kind: str,
    content: object,
    pointer: str,
    measurement: SourceMeasurement,
    rule: ReadingRule,
) -> None:
    """Record one leaf block and every inline it carries, notes included as their own blocks."""

    inlines, base = _inlines(kind, content, pointer)
    recorded = 0
    for index, value in enumerate(inlines):
        recorded += _inline(mapping(value), f"{base}/{index}", measurement, rule)
    measurement.recorded_per_block.append(recorded)


def _inlines(kind: str, content: object, pointer: str) -> tuple[list[object], str]:
    """Take a leaf block's inline content and the pointer prefix its children sit under."""

    if kind in {"Para", "Plain"}:
        return sequence(content), f"{pointer}/c"
    if kind == "Header":
        return sequence(_at(content, 2)), f"{pointer}/c/2"
    if kind == "LineBlock":
        return [inline for line in sequence(content) for inline in sequence(line)], f"{pointer}/c"
    return [], f"{pointer}/c"


def _inline(
    node: dict[str, object], pointer: str, measurement: SourceMeasurement, rule: ReadingRule
) -> int:
    kind = text(node.get("t")) or ""
    content = node.get("c")
    _attributes(kind, node, pointer, measurement, rule)
    if kind == "Link":
        measurement.links.append(_link(content, rule))
        return 1 if measurement.links[-1].recorded else 0
    if kind == "Image":
        measurement.images += 1
        if not inline_text(sequence(_at(content, 1))).strip():
            measurement.images_without_alt += 1
        return 0
    if kind == "Note":
        measurement.notes += 1
        _blocks(sequence(content), f"{pointer}/c", measurement, rule)
        return 0
    return sum(
        _inline(mapping(value), f"{pointer}/c/{index}", measurement, rule)
        for index, value in enumerate(_children(kind, content))
    )


def _children(kind: str, content: object) -> list[object]:
    values = sequence(content)
    if not values:
        return []
    nested = sequence(values[1]) if len(values) > 1 else []
    return nested if kind in {"Cite", "Quoted", "Span"} else values


def _link(content: object, rule: ReadingRule) -> SourceLink:
    target = text(_at(sequence(_at(content, 2)), 0)) or ""
    visible = inline_text(sequence(_at(content, 1))).strip()
    external = urlsplit(target.strip()).scheme.lower() in rule.excluded_schemes
    return SourceLink(
        target=target,
        text=visible,
        href_bytes=len(target.encode("utf-8")),
        external=external,
        recorded=not external and (bool(visible) or not rule.requires_visible_text),
    )


def _attributes(
    kind: str,
    node: dict[str, object],
    pointer: str,
    measurement: SourceMeasurement,
    rule: ReadingRule,
) -> None:
    """Read one node's Attr, which carries both its identifier and its page-break marking."""

    index = ATTRIBUTED.get(kind)
    if index is None:
        return
    attributes = sequence(_at(node.get("c"), index))
    identifier = text(_at(attributes, 0))
    if identifier:
        measurement.identifiers.append(identifier)
    named = rule.page_break_attributes
    tokens: set[str] = set()
    if "class" in named:
        tokens |= {str(value).lower() for value in sequence(_at(attributes, 1))}
    tokens |= {
        str(_at(pair, 1)).lower()
        for pair in sequence(_at(attributes, 2))
        if str(_at(pair, 0)).lower() in named
    }
    if tokens & rule.page_break_markers:
        measurement.page_breaks.append(pointer)


def _numbering(content: object, pointer: str, measurement: SourceMeasurement) -> None:
    """Note an ordered list whose own numbering carries meaning a bare list would lose."""

    attributes = sequence(_at(content, 0))
    start = _at(attributes, 0)
    style = text(mapping(_at(attributes, 1)).get("t")) or ""
    restarted = isinstance(start, int) and not isinstance(start, bool) and start != DEFAULT_START
    if restarted or (style and style not in DECIMAL_STYLES):
        measurement.renumbered_lists.append(pointer)


def _items(value: object, pointer: str, measurement: SourceMeasurement, rule: ReadingRule) -> None:
    for index, item in enumerate(sequence(value)):
        _blocks(sequence(item), f"{pointer}/{index}", measurement, rule)


def _definitions(
    content: object, pointer: str, measurement: SourceMeasurement, rule: ReadingRule
) -> None:
    for index, entry in enumerate(sequence(content)):
        _reading_block("Plain", _at(entry, 0), f"{pointer}/{index}/0", measurement, rule)
        _items(_at(entry, 1), f"{pointer}/{index}/1", measurement, rule)


def _nested_blocks(content: object) -> list[object]:
    """Collect a table's blocks wherever they sit in its caption, head, bodies and foot."""

    found: list[object] = []
    _collect(sequence(content)[1:], found)
    return found


def _collect(value: object, found: list[object]) -> None:
    items = sequence(value)
    if items:
        for item in items:
            _collect(item, found)
        return
    node = mapping(value)
    if text(node.get("t")) is not None:
        found.append(node)


def _at(content: object, index: int | None) -> object:
    if index is None:
        return content
    values = sequence(content)
    return values[index] if index < len(values) else None

"""Replace every Pandoc `Note` with one numbered reference and one dedicated note document.

Pandoc's default representation misdirected on CrossPoint 1.4.1: notes collected into one section
in the same file as their references, and following note 3 of 6 landed on a page
showing notes one and two, silently. One file per note was read on the same firmware and preferred
outright, because the unit of the reading action is one note.

The transform is an AST rewrite, not EPUB surgery. Pandoc's stock split level already gives one
XHTML spine item per top-level heading and rewrites intra-file anchors into cross-file anchors in
both directions, so this module only has to produce the headings and the references.
"""

from dataclasses import dataclass, field
from typing import cast

from galley.json_reading import sequence, text
from galley.profile.loading import activation_entry
from galley.report.quantities import quantity

NOTE = "Note"
IMAGE = "Image"
LINK = "Link"
HEADER = "Header"
PARA = "Para"
PLAIN = "Plain"
STR = "Str"
SPACE = "Space"

ONE_FILE_PER_NOTE = "one_file_per_note"
FOOTNOTE_BACKLINKS = "footnote_backlinks"
NOTE_CONVERSION = "note-conversion"

REFERENCE_PREFIX = "fnref-"
NOTE_PREFIX = "fn-"
FOOTNOTES_HEADING = "Footnotes"
NOTE_LABEL = "Footnote"
UNLISTED = "unlisted"
REFERENCE_CLASS = "footnote-ref"
BACKLINK_CLASS = "footnote-back"
NOTEREF_MARKING = [["epub:type", "noteref"], ["role", "doc-noteref"]]
BACKLINK_MARKING = [["epub:type", "backlink"], ["role", "doc-backlink"]]
# Pandoc splits into one spine item per top-level heading, so a note section is a level-1 heading.
NOTE_LEVEL = 1
INLINE_BLOCKS = frozenset({PARA, PLAIN})

NOTES_CONVERTED = (
    "Every Note became one numbered reference and one dedicated note document, whose body leads "
    "with its own number. The first note heading is the only listed Footnotes entry and every "
    "later one is blank and unlisted, so the navigation carries one flat entry."
)
NOTES_ABSENT = (
    "This Device Profile asks for one file per note, and the Canonical Document carries no Note. "
    "Nothing was converted because there was nothing to convert."
)
NOTES_INACTIVE = (
    "This Device Profile does not ask for one file per note, so the writer's own footnote "
    "representation stands and no Note was converted."
)
BACKLINKS_ABSENT = (
    "No in-text back-link is emitted. A device read reversed that decision: the hardware Back "
    "button already returns the reader, and a back-link is a Recorded Link that would spend one "
    "of the scarce per-screen footnote slots on it. The unused fnref-N ids stay on the references."
)
BACKLINKS_PRESENT = (
    "This Device Profile activates in-text back-links, so each note body ends with one labelled "
    "by the note's own number."
)


@dataclass(frozen=True)
class Conversion:
    """One note conversion: the working copy it produced and what it counted."""

    ast: dict[str, object]
    notes: int
    sections: int
    activated: bool
    backlinks: bool


@dataclass
class _Sections:
    """Note bodies collected while the walk runs, kept in the order their references appear."""

    bodies: dict[int, list[object]] = field(default_factory=dict[int, list[object]])
    next_number: int = 1

    def claim(self) -> int:
        number = self.next_number
        self.next_number += 1
        return number


def convert_notes(ast: dict[str, object], *, activated: bool, backlinks: bool) -> Conversion:
    """Convert every `Note` this document carries, wherever in its structure it sits.

    A profile that does not ask for one file per note leaves Pandoc's own representation, and the
    document is returned untouched rather than half-converted. Galley never ships a mixture of
    working and known-misdirecting notes inside one book.
    """

    if not activated:
        return Conversion(ast=ast, notes=0, sections=0, activated=False, backlinks=backlinks)
    sections = _Sections()
    working = cast(dict[str, object], _value(ast, sections, backlinks))
    blocks = sequence(working.get("blocks"))
    generated = 0
    for number in sorted(sections.bodies):
        blocks.extend(_section(number, sections.bodies[number]))
        generated += 1
    working["blocks"] = blocks
    return Conversion(
        ast=working,
        notes=len(sections.bodies),
        sections=generated,
        activated=True,
        backlinks=backlinks,
    )


def note_transform(profile: dict[str, object], conversion: Conversion) -> dict[str, object]:
    """State how many Notes became note documents, and whether they gained back-links."""

    representation = activation_entry(profile, ONE_FILE_PER_NOTE)
    backlinks = activation_entry(profile, FOOTNOTE_BACKLINKS)
    return {
        "name": NOTE_CONVERSION,
        "fired": conversion.notes > 0,
        "activation": ONE_FILE_PER_NOTE,
        "device_judged": representation.get("device_judged") is True,
        "justified_by": representation.get("justified_by"),
        "backlinks": {
            "activation": FOOTNOTE_BACKLINKS,
            "device_judged": backlinks.get("device_judged") is True,
            "emitted": conversion.backlinks,
            "justified_by": backlinks.get("justified_by"),
            "note": BACKLINKS_PRESENT if conversion.backlinks else BACKLINKS_ABSENT,
        },
        "notes": quantity(conversion.notes, "notes"),
        "note_documents": quantity(conversion.sections, "documents"),
        "note": _note_note(conversion),
    }


def _value(value: object, sections: _Sections, backlinks: bool) -> object:
    """Rebuild one AST value, converting each `Note` in the order the reader would meet it.

    The whole document is walked rather than a named set of containers, so a note in a heading, a
    table cell, a figure caption or another note's body is reached by the same rule. An `Image`'s
    description is the one place skipped: Pandoc flattens it to an `alt` attribute and drops any
    note inside it, so converting Pandoc's own copy of a figure caption there would number one
    source note twice.
    """

    if isinstance(value, list):
        return [_value(item, sections, backlinks) for item in cast(list[object], value)]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    kind = text(node.get("t"))
    if kind == NOTE:
        return _reference(node, sections, backlinks)
    if kind == IMAGE:
        return node
    return {key: _value(item, sections, backlinks) for key, item in node.items()}


def _reference(node: dict[str, object], sections: _Sections, backlinks: bool) -> dict[str, object]:
    """Claim this note's number, convert its own body, and leave one numbered reference behind."""

    number = sections.claim()
    blocks = sequence(_value(sequence(node.get("c")), sections, backlinks))
    sections.bodies[number] = _labelled(blocks, number, backlinks)
    return {
        "t": LINK,
        "c": [
            [f"{REFERENCE_PREFIX}{number}", [REFERENCE_CLASS], _copy(NOTEREF_MARKING)],
            [{"t": STR, "c": str(number)}],
            [f"#{NOTE_PREFIX}{number}", ""],
        ],
    }


def _labelled(blocks: list[object], number: int, backlinks: bool) -> list[object]:
    """Lead the note body with `Footnote N.`, and return from it only where a profile asks to.

    The number lives in body text because every note heading after the first is blank: a note page
    whose only label is a bare digit reads as an orphan. The back-link was reversed by
    a device read — the X4 has a hardware Back button, and the link spent a scarce footnote slot on
    a function the chassis already provides.
    """

    label: list[object] = [
        {"t": STR, "c": NOTE_LABEL},
        {"t": SPACE},
        {"t": STR, "c": f"{number}."},
        {"t": SPACE},
    ]
    led = _prefixed(blocks, label)
    return _returned(led, number) if backlinks else led


def _prefixed(blocks: list[object], label: list[object]) -> list[object]:
    """Put the label inside the note's first paragraph, or in one of its own where it has none."""

    first = cast(dict[str, object], blocks[0]) if blocks else {}
    if text(first.get("t")) not in INLINE_BLOCKS:
        return [{"t": PARA, "c": label}, *blocks]
    return [{**first, "c": [*label, *sequence(first.get("c"))]}, *blocks[1:]]


def _returned(blocks: list[object], number: int) -> list[object]:
    """Append the back-link a profile activating one asks for, labelled with the note's number."""

    link: dict[str, object] = {
        "t": LINK,
        "c": [
            ["", [BACKLINK_CLASS], _copy(BACKLINK_MARKING)],
            [{"t": STR, "c": str(number)}],
            [f"#{REFERENCE_PREFIX}{number}", ""],
        ],
    }
    last = cast(dict[str, object], blocks[-1])
    if text(last.get("t")) not in INLINE_BLOCKS:
        return [*blocks, {"t": PARA, "c": [link]}]
    return [*blocks[:-1], {**last, "c": [*sequence(last.get("c")), {"t": SPACE}, link]}]


def _section(number: int, blocks: list[object]) -> list[object]:
    """Head one note document, listing only the first so navigation carries one `Footnotes` entry.

    Every later heading is blank and `.unlisted`: it still splits into its own spine item, but it
    stays out of the navigation document and does not duplicate the running header.
    """

    first = number == 1
    heading: dict[str, object] = {
        "t": HEADER,
        "c": [
            NOTE_LEVEL,
            [f"{NOTE_PREFIX}{number}", [] if first else [UNLISTED], []],
            [{"t": STR, "c": FOOTNOTES_HEADING}] if first else [],
        ],
    }
    return [heading, *blocks]


def _copy(marking: list[list[str]]) -> list[object]:
    """Give each reference its own attribute pairs, so no two nodes share one mutable list."""

    return [list(pair) for pair in marking]


def _note_note(conversion: Conversion) -> str:
    if not conversion.activated:
        return NOTES_INACTIVE
    return NOTES_CONVERTED if conversion.notes else NOTES_ABSENT

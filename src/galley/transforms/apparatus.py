"""Recover a Footnote Apparatus from extracted HTML by relabelling it, never by inferring one.

Defuddle normalises roughly thirty reference conventions into one canonical shape and keeps every
note intact. Pandoc's HTML reader ignores it because the reference anchor lacks
`role="doc-noteref"`. The apparatus was never lost, only unlabelled, so recovery is a relabel
with two required halves — the role on each reference, and the definition list wrapped in a
`section[role="doc-endnotes"]`; with only the first, every note comes out empty.

**Emptiness is not decided here.** Markup that plainly carries text can still parse to nothing, so
the refusal is decided from the parsed result in `transforms/recovery.py`.

Recognition reads the markup; the rewrite splices the original string at the offsets recognition
found. Nothing is re-serialised, so a document outside the convention is carried forward
byte-for-byte, and one inside it matches everywhere except the two places the relabel touches.
This pass performs no publisher- or site-specific cleanup: it recognises one standard shape.
"""

from dataclasses import dataclass, replace
from html.parser import HTMLParser

from galley.report.quantities import quantity

CONVENTION = "doc-noteref-endnotes"
CONTAINER_ID = "footnotes"
REFERENCE_PREFIX = "fnref:"
DEFINITION_PREFIX = "fn:"
ANCHOR_OPEN = "<a"
NOTEREF_ROLE = ' role="doc-noteref"'
ENDNOTES_OPEN = '<section role="doc-endnotes">'
ENDNOTES_CLOSE = "</section>"

RECOVERED = "recovered"
SKIPPED = "skipped"
NOT_RECOGNISED = "not-recognised"
EMPTY_NOTE = "empty-note"

REASONS = {
    "no-apparatus": "the extracted content carries no recognised reference or endnote container",
    "no-references": "an endnote container exists but no reference points into it",
    "no-definitions": "references exist but extraction left no endnote container behind them",
    "reference-definition-mismatch": "the references and the endnotes do not pair exactly",
    "duplicate-target": "one endnote identifier is defined more than once",
    "unclosed-container": "the endnote container is never closed, so its extent cannot be found",
    EMPTY_NOTE: "an endnote carries no reader-visible text, and a blank note is worse than none",
}


@dataclass(frozen=True)
class Recovery:
    """One relabelling attempt: the content to carry forward, and what was made of the markup."""

    content: str
    outcome: str
    reason: str | None = None
    references: int = 0
    definitions: int = 0
    recovered: int = 0
    empty: int = 0
    unpaired: int = 0
    """References and endnotes that found no partner, by identifier rather than by count.

    Counting alone cannot see a mismatch between equal-sized sides, and reporting a difference of
    zero beside a mismatch reason would contradict itself.
    """

    def undone(self, original: str, *, empty: int) -> "Recovery":
        """Carry the document forward unrelabelled, once the parse showed a note came out empty.

        The original content is handed in rather than retained, because a recovery that never ran
        has no other version of the document to name and should not pretend to.
        """

        return replace(
            self,
            content=original,
            outcome=SKIPPED,
            reason=EMPTY_NOTE,
            recovered=0,
            empty=empty,
        )

    @property
    def facts(self) -> dict[str, object]:
        """Name the convention, the counts on both sides, and why recovery did or did not run."""

        return {
            "basis": "measured",
            "convention": None if self.outcome == NOT_RECOGNISED else CONVENTION,
            "definitions": quantity(self.definitions, "definitions"),
            "detail": None if self.reason is None else REASONS[self.reason],
            "empty_notes": quantity(self.empty, "notes"),
            "mismatch": quantity(self.unpaired, "identifiers"),
            "outcome": self.outcome,
            "reason": self.reason,
            "recovered_notes": quantity(self.recovered, "notes"),
            "references": quantity(self.references, "references"),
        }


@dataclass
class _Found:
    """One recognised part of the apparatus, and where it sits in the original string."""

    identifier: str
    start: int
    end: int = 0


def recover_apparatus(content: str) -> Recovery:
    """Relabel one extracted document's Footnote Apparatus, all-or-nothing.

    A document whose apparatus cannot be paired exactly is carried forward exactly as it arrived.
    This deliberately costs real recoveries: a reader who follows a reference to a
    blank page has no way to know the note text is sitting further down the book.
    """

    reader = _ApparatusReader()
    reader.read(content)
    references, definitions, container = reader.references, reader.definitions, reader.container
    counts = {
        "references": len(references),
        "definitions": len(definitions),
        "unpaired": _unpaired(references, definitions),
    }
    reason = _refusal(references, definitions, container)
    if container is None or reason is not None:
        outcome = NOT_RECOGNISED if reason == "no-apparatus" else SKIPPED
        return Recovery(content, outcome, reason, **counts)
    return Recovery(
        _relabelled(content, references, container),
        RECOVERED,
        None,
        **counts,
        recovered=len(references),
    )


def _refusal(
    references: list[_Found], definitions: list[_Found], container: _Found | None
) -> str | None:
    """Name the first condition that stops recovery, or nothing where every one is satisfied."""

    if not references and container is None:
        return "no-apparatus"
    if container is None:
        return "no-definitions"
    if not references:
        return "no-references"
    if container.end == 0:
        return "unclosed-container"
    identifiers = [definition.identifier for definition in definitions]
    if len(set(identifiers)) != len(identifiers):
        return "duplicate-target"
    if sorted(reference.identifier for reference in references) != sorted(identifiers):
        return "reference-definition-mismatch"
    return None


def _unpaired(references: list[_Found], definitions: list[_Found]) -> int:
    """Count the identifiers named on one side of the apparatus and not the other."""

    referenced = {reference.identifier for reference in references}
    defined = {definition.identifier for definition in definitions}
    return len(referenced ^ defined)


def _relabelled(content: str, references: list[_Found], container: _Found) -> str:
    """Splice both halves of the relabel into the original string, latest offset first.

    Descending order keeps every offset recognition recorded valid: an insertion never moves the
    text before it, so no position needs adjusting as the splices are applied.
    """

    insertions = [
        (container.end, ENDNOTES_CLOSE),
        (container.start, ENDNOTES_OPEN),
        *((reference.start + len(ANCHOR_OPEN), NOTEREF_ROLE) for reference in references),
    ]
    spliced = content
    for offset, text in sorted(insertions, reverse=True):
        spliced = spliced[:offset] + text + spliced[offset:]
    return spliced


class _ApparatusReader(HTMLParser):
    """Read extracted HTML for the one recognised shape, recording where each part sits.

    Character references are left unconverted so every offset recorded here indexes the original
    string, which is what lets the rewrite be a splice rather than a re-serialisation.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.references: list[_Found] = []
        self.definitions: list[_Found] = []
        self.container: _Found | None = None
        self._starts: list[int] = [0]
        self._container_tag = ""
        self._depth = 0
        self._reference: str | None = None
        self._definition: _Found | None = None
        self._nesting = 0

    def read(self, content: str) -> None:
        """Read one document from the beginning, resolving positions against its own lines."""

        self._starts = _line_starts(content)
        self.feed(content)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        start = self._offset()
        if self._open and tag == self._container_tag:
            self._depth += 1
        if tag == "sup" and values.get("id", "").startswith(REFERENCE_PREFIX):
            self._reference = values["id"][len(REFERENCE_PREFIX) :]
        elif tag == "a" and self._reference is not None:
            self._anchor(values, start)
        elif values.get("id") == CONTAINER_ID and self.container is None:
            self.container = _Found(CONTAINER_ID, start)
            self._container_tag = tag
            self._depth = 1
        elif tag == "li" and self._inside:
            self._nesting += 1
            if self._definition is None:
                self._definition = _Found(_identifier(values.get("id", "")), start)
                self._nesting = 1

    @property
    def _open(self) -> bool:
        """Say whether a container has been seen and not yet closed."""

        return self.container is not None and self.container.end == 0

    @property
    def _inside(self) -> bool:
        """Say whether reading is currently within the endnote container's own extent.

        "After the container started" is not the same thing: a list that follows a closed
        container is ordinary page content, and treating its items as endnotes would invent
        definitions the apparatus never had.
        """

        return self._open and self._depth > 0

    def _anchor(self, values: dict[str, str], start: int) -> None:
        """Record a reference anchor by the identifier its own href names.

        References pair on what they point at, not on the `id` the wrapping element happens to
        carry.
        """

        target = values.get("href", "")
        if target.startswith(f"#{DEFINITION_PREFIX}"):
            self.references.append(_Found(_identifier(target[1:]), start))

    def handle_endtag(self, tag: str) -> None:
        if tag == "sup":
            self._reference = None
        elif tag == "li" and self._definition is not None:
            self._close_definition()
        container = self.container
        if container is not None and container.end == 0 and tag == self._container_tag:
            self._depth -= 1
            if self._depth == 0:
                container.end = self._offset() + len(f"</{tag}>")

    def _close_definition(self) -> None:
        """Close one endnote at its own end tag, not at the first end tag inside it.

        A note carrying its own list would otherwise finish at that list's first item, and the
        definitions this pairs on would then name a fragment rather than the note.
        """

        self._nesting -= 1
        if self._nesting == 0 and self._definition is not None:
            self.definitions.append(self._definition)
            self._definition = None

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._starts[line - 1] + column


def _identifier(value: str) -> str:
    """Take the identifier a `fn:` reference or target names, whichever side stated it."""

    return value[len(DEFINITION_PREFIX) :] if value.startswith(DEFINITION_PREFIX) else value


def _line_starts(content: str) -> list[int]:
    """Index where each line begins, so a parser position becomes an absolute offset."""

    starts = [0]
    for index, character in enumerate(content):
        if character == "\n":
            starts.append(index + 1)
    return starts

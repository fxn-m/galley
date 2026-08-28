"""What the source reader discarded before the Canonical Document existed.

The Preservation Baseline is rendered from the Pandoc AST, so it is taken *after* the reader has
run. Everything Galley is handed does survive, but a claim scoped to that can mislead: a source
with 42 footnote definitions and only 40 references loses the two unreferenced notes before the
AST exists.

The reader is the only witness to its own discards. Its messages are already captured verbatim,
but a string joined to nothing cannot qualify a claim, so the shapes Galley recognises as discards
are named here and become facts the preservation record can read — and are reported inside it,
beside the claim they qualify. They do not belong in `canonical_document`, which is a pure
function of the AST; a discard is exactly what the AST cannot show.

A message Galley does not recognise stays a warning and qualifies nothing. Under-claiming is the
safe direction here — a message that is not a discard must not suppress a true claim — and if
Pandoc rewords one of these, the behavioural tests notice it loudly and in one place.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from galley.report.quantities import quantity

UNREFERENCED_NOTE = "unreferenced-note"
# Pandoc's Markdown reader on a note definition nothing points at. The note's text is not in the
# AST that follows, so no measurement taken from that AST can see that it is gone.
NOTE_OPENING = "Note with key '"
NOTE_CLOSING = "' defined at "
NOTE_ENDING = "but not used"
KINDS = {
    UNREFERENCED_NOTE: (
        "the source defines this note and nothing references it, so the reader dropped its text "
        "before the Canonical Document existed"
    )
}
DISCARD_NOTE = (
    "What the source reader reported dropping while reading the source. The Preservation Baseline "
    "is rendered from what the reader produced, so a discard recorded here is loss no measurement "
    "taken from the Canonical Document can see. It is why a run carrying one makes no Text "
    "Preservation claim."
)


@dataclass(frozen=True)
class Discard:
    """One thing the reader said it dropped, and the message it said it in."""

    kind: str
    identifier: str
    message: str

    @property
    def facts(self) -> dict[str, object]:
        """Name what was dropped, which of it, why it matters, and the reader's own words."""

        return {
            "detail": KINDS[self.kind],
            "identifier": self.identifier,
            "kind": self.kind,
            "message": self.message,
        }


def reader_discards(messages: Sequence[str]) -> list[Discard]:
    """Read one parse's messages for the shapes that mean content did not reach the AST."""

    return [
        Discard(UNREFERENCED_NOTE, identifier, message)
        for message in messages
        if (identifier := _unreferenced_note(message)) is not None
    ]


def _unreferenced_note(message: str) -> str | None:
    """Take the note key out of Pandoc's "defined ... but not used", or nothing where it is not."""

    opening = message.find(NOTE_OPENING)
    if opening < 0 or not message.rstrip().rstrip(".").endswith(NOTE_ENDING):
        return None
    start = opening + len(NOTE_OPENING)
    closing = message.find(NOTE_CLOSING, start)
    return None if closing < 0 else message[start:closing]


def discard_facts(discards: Sequence[Discard]) -> dict[str, object]:
    """State what the reader dropped, including when it dropped nothing.

    Always stated. Silence and "nothing was dropped" are the same absence to a reader of the
    Report, and this is the field a Text Preservation claim now rests on.
    """

    return {
        "basis": "measured",
        "count": quantity(len(discards), "items"),
        "items": [discard.facts for discard in discards],
        "note": DISCARD_NOTE,
    }

"""Decide whether a Recovered Footnote Apparatus survived the parse that read it.

Recovery is refused entirely where any note would come out empty, because a blank footnote is
worse than no footnote: the reader follows a reference, arrives at an empty page, and has no way
to know the text is sitting further down the book. That rule was evaluated against the extracted
*markup*, and markup is not where a note becomes empty.

One observed article showed the difference. All seventeen definitions plainly carried text in the
HTML the relabeller read; one also carried a stray `<li>` inside its `<p>`, and Pandoc's HTML5
parser restructured the list around it so that **every** note came out empty —
including the sixteen that were well-formed. Galley shipped seventeen blank footnote pages with
their text left inline at the end of the first chapter, which is the exact damage the rule exists
to prevent.

So emptiness is decided here, on the Notes the pipeline actually produced. Two parsers reading the
same bytes are entitled to disagree; asking one of them about the other's result is answering the
wrong question, whatever document it meets.
"""

from typing import cast

from galley.document.baseline import block_segments
from galley.json_reading import sequence, text
from galley.transforms.apparatus import RECOVERED, Recovery

NOTE = "Note"
LINK = "Link"
# A back-link's arrow is markup the apparatus carries for navigation, not note text, so a note
# holding nothing else is one the reader arrives at to find a return arrow and no words.
BACKREF_CLASS = "footnote-backref"


def settled_recovery(recovery: Recovery, original: str, ast: dict[str, object]) -> Recovery | None:
    """Hold a recovery to the notes it produced, or nothing where it needs no holding.

    Nothing, rather than the recovery back: the caller has to re-read the document when a recovery
    is undone, and "did this change?" answered by comparing objects is a convention two modules
    would have to agree on without saying so. Only a recovery that ran can be undone.
    """

    if recovery.outcome != RECOVERED:
        return None
    empty = empty_notes(ast)
    return recovery.undone(original, empty=empty) if empty else None


def empty_notes(ast: dict[str, object]) -> int:
    """Count the Notes this document carries that a reader would find nothing on.

    Emptiness is measured as reader-visible text, by the same rendering the Preservation Baseline
    is made of, so "the node has no children" and "the note says nothing" cannot drift apart.
    """

    return sum(1 for note in _notes(ast.get("blocks")) if not _visible(note.get("c")))


def _visible(content: object) -> str:
    """Render one Note's reader-visible text, with its own navigation markup taken out first."""

    return "".join(block_segments(sequence(_without_backrefs(content)))).strip()


def _without_backrefs(value: object) -> object:
    """Rebuild one subtree without the back-links the apparatus carries for navigation."""

    if isinstance(value, list):
        return [_without_backrefs(item) for item in cast(list[object], value) if not _backref(item)]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    return {key: _without_backrefs(item) for key, item in node.items()}


def _backref(item: object) -> bool:
    """Say whether one inline is a footnote back-link rather than part of the note."""

    if not isinstance(item, dict) or text(cast(dict[str, object], item).get("t")) != LINK:
        return False
    content = sequence(cast(dict[str, object], item).get("c"))
    classes = sequence(sequence(content[0])[1]) if content else []
    return BACKREF_CLASS in [text(entry) for entry in classes]


def _notes(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [found for item in cast(list[object], value) for found in _notes(item)]
    if not isinstance(value, dict):
        return []
    node = cast(dict[str, object], value)
    nested = _notes(node.get("c"))
    return [node, *nested] if text(node.get("t")) == NOTE else nested

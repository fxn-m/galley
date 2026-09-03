"""What a stated author's occurrence in the document's own text does and does not establish."""

from galley.document.authorship import author_occurrence
from galley.json_reading import integer, mapping, text


def test_an_absent_author_reports_nothing() -> None:
    assert author_occurrence(None, "Any text at all.") is None


def test_an_author_absent_from_the_text_is_reported_as_absent_rather_than_omitted() -> None:
    occurrence = author_occurrence("Ada Lovelace", "A document that never names her.")

    assert occurrence == {
        "occurrences": {"basis": "measured", "unit": "occurrences", "value": 0},
        "stated": "Ada Lovelace",
    }


def test_a_fragment_lifted_from_the_body_is_quoted_in_the_sentence_it_came_from() -> None:
    baseline = (
        "A typical task requires around 50 tool calls on average.\n"
        "By constantly rewriting the todo list, Manus is reciting its objectives into the end "
        "of the context.\n"
    )

    occurrence = author_occurrence("constantly rewriting the todo list, Manus is", baseline)

    assert occurrence is not None
    assert occurrence["context"] == (
        "By constantly rewriting the todo list, Manus is reciting its objectives into the end "
        "of the context."
    )


def test_a_correct_author_who_writes_their_own_name_is_reported_the_same_way() -> None:
    """The point of the fact: it does not separate a byline from a fragment, and must not claim to.

    Gwern, Eliezer S. Yudkowsky and the Department for Business and Trade all occur in their own
    prose. A rule that discarded the Manus clause on this evidence would discard them too.
    """

    baseline = "This graveyard page compiles post-mortems of things I tried on Gwern.net.\n"

    occurrence = author_occurrence("Gwern", baseline)

    assert occurrence is not None
    assert _count(occurrence) == 1
    assert "Gwern.net" in cast_str(occurrence["context"])


def test_every_occurrence_is_counted_not_only_the_first() -> None:
    occurrence = author_occurrence("Gwern", "Gwern wrote it. Gwern published it on Gwern.net.\n")

    assert occurrence is not None
    assert _count(occurrence) == 3


def test_the_quoted_sentence_is_bounded_so_a_long_paragraph_stays_readable() -> None:
    baseline = "x" * 400 + " Ada Lovelace " + "y" * 400

    occurrence = author_occurrence("Ada Lovelace", baseline)

    assert occurrence is not None
    assert len(cast_str(occurrence["context"])) < 400


def test_a_baseline_that_was_never_produced_reports_nothing() -> None:
    """A parse that failed has no reader-visible text, so there is nothing to have looked in."""

    assert author_occurrence("Ada Lovelace", "") is None


def cast_str(value: object) -> str:
    return text(value) or ""


def _count(occurrence: dict[str, object]) -> int:
    return integer(mapping(occurrence.get("occurrences")).get("value")) or 0

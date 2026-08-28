"""Branches no bundled profile and no Markdown source can reach, specified directly on the AST."""

import json
from typing import Any, cast

from galley.images.preparation import ImagePreparation
from galley.transforms.notes import convert_notes
from galley.report.quantities import quantity
from galley.transforms.working_copy import WorkingCopy, note_mismatch

NO_IMAGES = ImagePreparation(ast={})


def note(*blocks: object) -> dict[str, object]:
    return {"t": "Note", "c": list(blocks)}


def para(*inlines: object) -> dict[str, object]:
    return {"t": "Para", "c": list(inlines)}


def word(value: str) -> dict[str, object]:
    return {"t": "Str", "c": value}


# Pandoc's Markdown reader does not nest notes, but the AST permits it and an HTML source may
# produce it, so the recursion is specified here rather than left to a source that cannot make one.
NESTED: dict[str, object] = {
    "blocks": [para(word("outer"), note(para(word("inner"), note(para(word("deep"))))))],
    "meta": {},
}
LINKED: dict[str, object] = {"blocks": [para(word("body"), note(para(word("note"))))], "meta": {}}


def copy_of(notes: int) -> WorkingCopy:
    return WorkingCopy(ast={}, transforms=[], notes=notes, converted=True, images=NO_IMAGES)


def artifact_facts(*, total: int, unresolved: int, documents: int) -> dict[str, object]:
    return {
        "links": {
            "footnote_references": {
                "target_documents": quantity(documents, "documents"),
                "total": quantity(total, "links"),
                "unresolved": quantity(unresolved, "links"),
            }
        }
    }


def test_a_note_inside_another_note_is_converted_by_recursion() -> None:
    conversion = convert_notes(NESTED, activated=True, backlinks=False)

    assert (conversion.notes, conversion.sections) == (2, 2)
    rendered = json.dumps(conversion.ast)
    assert '"#fn-1"' in rendered and '"#fn-2"' in rendered
    assert '"t": "Note"' not in rendered
    assert "deep" in rendered


def test_a_profile_not_asking_for_one_file_per_note_leaves_the_document_alone() -> None:
    conversion = convert_notes(LINKED, activated=False, backlinks=False)

    assert (conversion.notes, conversion.sections) == (0, 0)
    assert conversion.ast is LINKED
    assert '"t": "Note"' in json.dumps(conversion.ast)


def test_a_profile_activating_backlinks_gets_one_labelled_by_the_notes_number() -> None:
    """The fnref-N ids let a back-link be restored without another AST pass."""

    conversion = convert_notes(LINKED, activated=True, backlinks=True)

    blocks = cast(list[Any], conversion.ast["blocks"])
    body = cast(list[Any], blocks[-1]["c"])
    link = body[-1]
    assert link["t"] == "Link"
    assert link["c"][2][0] == "#fnref-1"
    assert link["c"][1] == [word("1")]
    assert "doc-backlink" in json.dumps(link)


def test_a_book_that_agrees_with_its_conversion_is_not_refused() -> None:
    facts = artifact_facts(total=3, unresolved=0, documents=3)

    assert note_mismatch(facts, copy_of(3), 3) is None


def test_a_profile_that_converted_nothing_is_never_asked_to_agree() -> None:
    untouched = WorkingCopy(ast={}, transforms=[], notes=0, converted=False, images=NO_IMAGES)

    assert note_mismatch(artifact_facts(total=4, unresolved=1, documents=1), untouched, 4) is None


def test_a_reference_the_source_carried_through_is_not_a_missing_note() -> None:
    """The link interlock retains markings it cannot classify, and those are not lost notes."""

    extra = artifact_facts(total=4, unresolved=0, documents=4)

    assert note_mismatch(extra, copy_of(3), 3) is None


def test_every_way_the_built_book_can_disagree_is_named() -> None:
    shared = note_mismatch(artifact_facts(total=3, unresolved=0, documents=1), copy_of(3), 3)
    broken = note_mismatch(artifact_facts(total=3, unresolved=1, documents=3), copy_of(3), 3)
    lost = note_mismatch(artifact_facts(total=2, unresolved=0, documents=2), copy_of(3), 3)
    disputed = note_mismatch(artifact_facts(total=3, unresolved=0, documents=3), copy_of(3), 2)

    assert shared is not None and shared["disagreements"] == ["shared-note-documents"]
    assert broken is not None and broken["disagreements"] == ["unresolved-references"]
    assert lost is not None and lost["disagreements"] == [
        "missing-references",
        "shared-note-documents",
    ]
    assert disputed is not None and disputed["disagreements"] == ["source-count-disagreement"]
    assert disputed["source_notes"] == quantity(2, "notes")

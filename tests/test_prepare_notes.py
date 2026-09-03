from pathlib import Path
from typing import Any

from tests.image_fixtures import grayscale_png
from tests.markdown_fixtures import NOTE_POSITIONS, PLAIN_BOOK, write_markdown
from tests.prepared_epub import PreparedEpub
from tests.public_cli import run_cli, prepare

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
NOTES = 9
BODIES = (
    "Headword",
    "Paraword",
    "Quoteword",
    "Itemword",
    "Termword",
    "Definitionword",
    "Cellword",
    "Figureword",
    "Divword",
)


def conversion(report: Any) -> Any:
    return next(
        entry for entry in report["preparation"]["transforms"] if entry["name"] == "note-conversion"
    )


def note_documents(book: PreparedEpub) -> list[str]:
    """Name the spine documents carrying a note target, in reading order.

    Read straight from the archive rather than through Galley's own EPUB reader, so the assertion
    is evidence about the book rather than a restatement of what preparation believes.
    """

    return [
        href
        for href, identifiers in book.document_identifiers().items()
        if any(identifier.startswith("fn-") for identifier in identifiers)
    ]


def test_preparation_preserves_notes_as_navigable_back_matter(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", NOTE_POSITIONS)
    _ = grayscale_png(tmp_path / "figure.png")
    journey = prepare(tmp_path, prepared_source)
    output, report = journey.output, journey.report

    entry = conversion(report)
    assert entry["fired"] is True
    assert entry["notes"]["value"] == NOTES
    assert entry["note_documents"]["value"] == NOTES
    assert report["canonical_document"]["reading"]["notes"]["value"] == NOTES
    book = PreparedEpub(output)
    assert len(note_documents(book)) == NOTES
    references = [
        (document, href) for document, href, _ in book.content_anchors() if "#fn-" in href
    ]
    assert len(references) == NOTES
    targets = {href.split("#")[0] for _, href in references}
    assert len(targets) == NOTES
    assert all(document != href.split("#")[0] for document, href in references)
    texts = book.document_texts()
    for position, document in enumerate(note_documents(book), start=1):
        body = texts[document].removeprefix("Footnotes ")
        assert body.startswith(f"Footnote {position}.")
    assert report["artifact"]["links"]["footnote_references"] == {
        "target_documents": {"basis": "measured", "unit": "documents", "value": NOTES},
        "total": {"basis": "measured", "unit": "links", "value": NOTES},
        "unresolved": {"basis": "measured", "unit": "links", "value": 0},
    }

    assert book.navigation_entries().count("Footnotes") == 1
    documents = note_documents(book)
    note_headings = [
        (text, classes) for document, text, classes in book.headings() if document in documents
    ]
    assert note_headings[0] == ("Footnotes", [])
    assert all(text == "" and "unlisted" in classes for text, classes in note_headings[1:])

    identifiers = [identifier for identifier, href in book.anchor_identifiers() if "#fn-" in href]
    assert identifiers == [f"fnref-{number}" for number in range(1, NOTES + 1)]
    assert not [href for _, href, _ in book.content_anchors() if "#fnref-" in href]
    assert conversion(report)["backlinks"]["emitted"] is False
    assert conversion(report)["backlinks"]["activation"] == "footnote_backlinks"
    assert conversion(report)["backlinks"]["justified_by"] == "hardware-back-button"

    texts = book.document_texts()
    joined = " ".join(texts.values())
    for body in BODIES:
        assert f"{body} body." in joined
    multi = next(text for text in texts.values() if "Paraword body." in text)
    assert "Second paragraph of the note." in multi

    markup = "".join(book.member(href).decode("utf-8") for href in book.spine_documents())
    assert 'epub:type="footnote"' not in markup
    assert 'class="footnotes' not in markup
    assert markup.count('epub:type="noteref"') == NOTES
    assert report["artifact"]["conformance"]["counts"]["error"]["value"] == 0
    assert not report["artifact"]["problems"]
    assert len(book.body_documents()) == NOTES + 2


def test_human_output_names_the_back_matter_one_file_per_note_produced(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "human-0.md", NOTE_POSITIONS)
    _ = grayscale_png(tmp_path / "figure.png")
    result = run_cli(
        "prepare",
        str(source),
        "--output",
        str(tmp_path / "human-0.epub"),
        "--profile",
        "x4-crosspoint",
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert "Transform: note-conversion (fired)\n" in result.stdout
    assert f"Notes: {NOTES} converted into {NOTES} documents, no back-link\n" in result.stdout


def test_the_report_records_source_and_generated_note_counts_for_a_document_with_none(
    tmp_path: Path,
) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", PLAIN_BOOK)
    _ = grayscale_png(tmp_path / "figure.png")
    journey = prepare(tmp_path, prepared_source)
    _, report = journey.output, journey.report

    entry = conversion(report)
    assert entry["fired"] is False
    assert entry["notes"]["value"] == 0
    assert entry["note_documents"]["value"] == 0
    assert "nothing to convert" in entry["note"]

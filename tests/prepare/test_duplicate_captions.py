"""A figure caption Pandoc derived from an alt the document already prints is not printed twice.

An image alone in a paragraph becomes one of Pandoc's implicit figures, and the writer copies the
alt text into a `figcaption` marked `aria-hidden="true"`. That mark is for a screen reader, which
has already had the alt; a panel renders the caption anyway, and then renders the document's own
paragraph saying the same thing beneath it. A reader observed all nine figures of one document
that way on a real X4 before any measurement found it.

The rule is exact equality between caption, alt and the paragraph immediately following, with
whitespace removed. Everything here that does not fire is as much the point as everything that
does: the near misses are what keep this a duplicate-suppression rule rather than a caption
opinion.
"""

from pathlib import Path
from typing import Any

from tests.support.image_fixtures import grayscale_png
from tests.support.markdown_fixtures import write_markdown
from tests.support.prepared_epub import PreparedEpub
from tests.support.public_cli import prepare, run_cli

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
PROSE = "Ordinary prose, long enough that this reads as a document rather than as a fragment."
LESSON = "A better GPT-3 lesson."


def source(alt: str, following: str) -> str:
    """One document whose single figure is followed by the paragraph under test."""

    return (
        f'---\ntitle: "A Figured Book"\n---\n\n# A Figured Book\n\n{PROSE}\n\n'
        f"![{alt}](figure.png)\n\n{following}\n\n{PROSE} And again, past the picture.\n"
    )


def suppression(report: Any) -> Any:
    return next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "duplicate-caption-suppression"
    )


def test_a_caption_the_next_paragraph_repeats_is_printed_once(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", source(LESSON, LESSON))
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert suppression(report)["fired"] is True
    assert suppression(report)["suppressed"]["value"] == 1
    assert suppression(report)["captions"] == [LESSON]
    book = PreparedEpub(artifact)
    assert book.content_text().count(LESSON) == 1


def test_the_alt_attribute_itself_is_untouched(tmp_path: Path) -> None:
    """Only the printed copy goes. Accessibility reads the attribute and it still says the same."""

    prepared_source = write_markdown(tmp_path / "source-0.md", source(LESSON, LESSON))
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert suppression(report)["fired"] is True
    book = PreparedEpub(artifact)
    assert [alt for _, _, alt in book.image_sources()] == [LESSON]


def test_text_preservation_is_unaffected_by_the_suppression(tmp_path: Path) -> None:
    """Dropping printed text is the one thing this project refuses to assume is harmless.

    It is harmless here because neither side of the comparison ever counted the third copy. The
    baseline drops Pandoc's derived caption and keeps the alt; a built book's reader-visible text
    counts the alt attribute as the fallback the device shows in its place. Two against two before
    and two against two after. If that ever stops being true, it shows up here as words reported
    missing from a book that still says them.
    """

    prepared_source = write_markdown(tmp_path / "source-0.md", source(LESSON, LESSON))
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report
    preservation = report["artifact"]["text_preservation"]

    assert suppression(report)["fired"] is True
    assert preservation["claimed"] is True
    assert preservation["tokens"]["unexpected_missing"] == []


def test_whitespace_the_two_copies_were_spaced_by_does_not_defeat_the_match(
    tmp_path: Path,
) -> None:
    """gwern.net writes `(LeCun 2019)` in the attribute and `( LeCun 2019 )` in the prose.

    The two copies reach the AST down different paths — one straight out of an attribute, one
    through an HTML-to-Markdown conversion that spaced its inline elements — so a match that
    compared them character for character would miss every figure this exists for.
    """

    spaced = "Is GPT part of AGI? ( LeCun 2019 )"
    document = source("Is GPT part of AGI? (LeCun 2019)", spaced)

    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report
    book = PreparedEpub(artifact)
    text = book.content_text()

    assert suppression(report)["fired"] is True
    assert text.count("Is GPT part of AGI?") == 1
    assert spaced in text


def test_a_caption_the_next_paragraph_only_begins_is_still_printed(tmp_path: Path) -> None:
    """The rule is equality, not similarity. A paragraph that goes on to say more is its own text."""

    document = source(LESSON, f"{LESSON} And the reason it is better takes a while to explain.")

    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert suppression(report)["fired"] is False
    book = PreparedEpub(artifact)
    assert book.content_text().count(LESSON) == 2


def test_a_caption_differing_by_one_word_is_still_printed(tmp_path: Path) -> None:
    prepared_source = write_markdown(
        tmp_path / "source-0.md", source(LESSON, "A worse GPT-3 lesson.")
    )
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report
    book = PreparedEpub(artifact)
    text = book.content_text()

    assert suppression(report)["fired"] is False
    assert (text.count(LESSON), text.count("A worse GPT-3 lesson.")) == (1, 1)


def test_a_figure_whose_caption_came_from_its_alt_but_says_something_else_is_left_alone(
    tmp_path: Path,
) -> None:
    """`Design Graveyard` has exactly this figure, and it is why the third clause exists.

    Its caption is Pandoc's copy of the alt, like every other figure in the book, but the
    paragraph beneath it is different text. Nothing else carries the caption's words, so dropping
    it would be content loss rather than duplicate suppression.
    """

    document = source(LESSON, "The graveyard is full of designs that did not survive contact.")

    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert suppression(report)["fired"] is False
    book = PreparedEpub(artifact)
    assert book.content_text().count(LESSON) == 1


def test_a_figure_with_no_paragraph_after_it_is_left_alone(tmp_path: Path) -> None:
    """A figure is a duplicate only of the sibling that follows it, and here nothing does."""

    document = (
        f'---\ntitle: "A Figured Book"\n---\n\n# A Figured Book\n\n{PROSE}\n\n'
        f"![{LESSON}](figure.png)\n"
    )

    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert suppression(report)["fired"] is False
    book = PreparedEpub(artifact)
    assert book.content_text().count(LESSON) == 1


def test_the_terminal_says_how_many_captions_stopped_being_printed(tmp_path: Path) -> None:
    """A transform that takes text off the panel says so where a person is looking."""

    written = write_markdown(tmp_path / "human-0.md", source(LESSON, LESSON))
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)
    result = run_cli(
        "prepare",
        str(written),
        "--output",
        str(tmp_path / "human-0.epub"),
        "--profile",
        "x4-crosspoint",
    )

    assert "Transform: duplicate-caption-suppression (fired)\n" in result.stdout
    assert "Captions: 1 suppressed, each still printed by the paragraph below it\n" in result.stdout

"""The identifiers a book's own navigation points at: complete, unique, and short enough.

CrossPoint truncates an over-long href silently and lands the reader at the top of the chapter, so
`footnote-href-length` refuses at 96 bytes. The href is `text/chNNN.xhtml#<identifier>` and the
identifier used to be a slug of the document's own words, which made the length a property of the
title rather than of Galley's naming.

Two more properties turned out to hang off the same fact. The section Pandoc's EPUB3 writer
invents from the title is *sometimes not invented at all*, which leaves a book with an empty
navigation document; and when it is, its identifier took part in no de-duplication, so an article
whose first heading repeats its title ends up with two elements answering to one name. These hold
all three to Galley's naming.
"""

from pathlib import Path
from typing import Any

from galley.document.link_kinds import FOOTNOTE_HREF_LENGTH
from galley.profile.loading import enforced_limit, load_profile
from galley.transforms.identifiers import PATH_RESERVE, TITLE_PREFIX
from tests.support.markdown_fixtures import write_markdown
from tests.support.prepared_epub import PreparedEpub
from tests.support.public_cli import prepare

PROFILE = "x4-crosspoint"
ARGUMENTS = ("--profile", PROFILE, "--json")
LIMIT = enforced_limit(load_profile(PROFILE), FOOTNOTE_HREF_LENGTH) or 0
# Long enough that its slug cannot fit the budget, and made of ordinary words so the slug is the
# title rather than an artefact of punctuation.
LONG = (
    "People, ideas, machines VII: The Wizard War, lessons on technology, "
    "intelligence and organisation from the second world war"
)
PROSE = "Prose that runs long enough to read as a document rather than as a fragment of one.\n"
TITLE = "A Short Title"
# Extractors wrap what they keep in a container, and every observed extracted document
# arrives inside one. Where the document's own headings sit inside that container too, Pandoc's
# writer invents no title section, so without the heading Galley writes there is no entry for the
# work itself — the wrapped section below is listed beneath it, not in place of it.
WRAPPED = f"::: article\n\n## A section inside the wrapper\n\n{PROSE}\n:::\n"


def source(title: str, body: str) -> str:
    return f'---\ntitle: "{title}"\n---\n\n{body}'


def bounding(report: Any) -> Any:
    return next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "identifier-bounding"
    )


def longest_href(book: PreparedEpub) -> int:
    return max(len(href.encode("utf-8")) for href, _ in book.navigation_anchors())


def test_a_long_heading_no_longer_makes_a_book_refuse_its_own_navigation(tmp_path: Path) -> None:
    document = source(LONG, f"# {LONG}\n\n{PROSE}")
    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert report["artifact"]["links"]["maximum_recorded_href_bytes"]["value"] <= LIMIT
    book = PreparedEpub(artifact)
    assert longest_href(book) <= LIMIT
    assert bounding(report)["fired"] is True


def test_a_long_title_with_no_heading_of_its_own_gets_one_galley_named(tmp_path: Path) -> None:
    """Pandoc synthesises a section from the stated title and slugs that, so there is nothing in
    the document to bound. The heading it would have written is written explicitly instead."""

    prepared_source = write_markdown(tmp_path / "source-0.md", source(LONG, PROSE))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report
    prepared_source = write_markdown(tmp_path / "control.md", source("Short", PROSE))
    journey2 = prepare(tmp_path, prepared_source, expected_exit=None)
    control, _ = journey2.output, journey2.report

    assert report["outcome"] == "completed"
    assert bounding(report)["title_heading"].startswith(TITLE_PREFIX)
    book = PreparedEpub(artifact)
    assert longest_href(book) <= LIMIT
    # The reader sees the same shape of book as one whose title needed nothing done to it:
    # the heading Galley writes is the heading Pandoc was going to synthesise.
    assert [text for _, text, _ in book.headings()] == [LONG, LONG]
    control_book = PreparedEpub(control)
    assert [text for _, text, _ in control_book.headings()] == ["Short", "Short"]


def test_a_document_leading_with_its_own_heading_is_left_alone(tmp_path: Path) -> None:
    """The writer synthesises nothing for a document that already opens with a level-1 heading,
    and that heading carries an identifier of its own for the bounding pass to reach."""

    document = source("A Short Title", f"# A Short Title\n\n{PROSE}")
    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert bounding(report) == {
        **bounding(report),
        "fired": False,
        "rewritten": {},
        "title_heading": None,
    }


def test_a_wrapped_document_still_gets_a_navigation_entry(tmp_path: Path) -> None:
    """A book whose navigation document is an empty `<ol>` is invalid EPUB, and worse than that:
    this profile's `toc_depth` rests on a device test saying page breaks follow nav membership, so
    a book with no entries has no page breaks either. Galley writes the heading the writer did
    not, whatever the title's length."""

    prepared_source = write_markdown(tmp_path / "source-0.md", source("A Short Title", WRAPPED))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert bounding(report)["title_heading"].startswith(TITLE_PREFIX)
    book = PreparedEpub(artifact)
    assert book.navigation_entries() == ["A Short Title", "A section inside the wrapper"]
    assert [text for _, text, _ in book.headings()] == ["A Short Title", "A Short Title"]


def test_a_first_heading_repeating_the_title_does_not_share_its_identifier(
    tmp_path: Path,
) -> None:
    """Pandoc's HTML reader assigns and de-duplicates every identifier in the document; the one
    the *writer* invents for the title takes part in none of that. An article whose opening
    heading is its own title minus a colon is the ordinary shape that collides with it."""

    title = "Library patterns: Why frameworks are evil"
    body = f"## Library patterns Why frameworks are evil\n\n{PROSE}"
    prepared_source = write_markdown(tmp_path / "source-0.md", source(title, body))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    book = PreparedEpub(artifact)
    for identifiers in book.document_identifiers().values():
        assert sorted(set(identifiers)) == sorted(identifiers)
    # The heading's own slug is still there, and it is not the name the title answers to.
    offered = [
        identifier
        for identifiers in book.document_identifiers().values()
        for identifier in identifiers
    ]
    assert "library-patterns-why-frameworks-are-evil" in offered
    assert bounding(report)["title_heading"] in offered


def test_the_title_heading_costs_the_reader_nothing(tmp_path: Path) -> None:
    """It is now written into nearly every book Galley builds, so what it does to a reader's text
    is the load-bearing question — and the words it adds matter as much as any it could lose.

    The title is not new text: Pandoc was going to synthesise the same heading from `dc:title`,
    so the built book says it exactly as often either way. The document that already leads with a
    heading of its own is measured beside it, because "no tokens moved" has to hold where the
    transform fires and where it does not.
    """

    # The same document twice: once for Galley to write the heading, once carrying its own.
    prepared_source = write_markdown(tmp_path / "source-0.md", source(TITLE, WRAPPED))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, inserted = journey.output, journey.report
    prepared_source = write_markdown(
        tmp_path / "control.md", source(TITLE, f"# {TITLE}\n\n{WRAPPED}")
    )
    journey2 = prepare(tmp_path, prepared_source, expected_exit=None)
    _, untouched = journey2.output, journey2.report

    assert (inserted["outcome"], untouched["outcome"]) == ("completed", "completed")
    one = inserted["artifact"]["text_preservation"]["tokens"]
    two = untouched["artifact"]["text_preservation"]["tokens"]
    assert bounding(inserted)["title_heading"].startswith(TITLE_PREFIX)
    assert bounding(untouched)["title_heading"] is None
    # Neither loses a word, and both books carry exactly the same words: the heading Galley
    # writes is the heading the document would have had.
    assert one["unexpected_missing"] == two["unexpected_missing"] == []
    assert one["artifact"]["value"] == two["artifact"]["value"]
    # All the transform adds is the title, once — the difference is only whether those words
    # were already in the baseline the artifact is compared against.
    assert one["added"]["value"] - two["added"]["value"] == len(TITLE.split())


def test_a_cross_reference_still_reaches_the_heading_it_named(tmp_path: Path) -> None:
    document = source(
        "A Short Title",
        f"# {LONG}\n\n{PROSE}\nAnd [a pointer back]({{#ref}}) to it.\n".replace(
            "{#ref}", "#" + LONG.lower().replace(" ", "-").replace(",", "").replace(":", "")
        ),
    )
    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert report["artifact"]["links"]["dead"] == []
    assert report["artifact"]["references"]["broken"] == []
    book = PreparedEpub(artifact)
    targets = {
        fragment for identifiers in book.document_identifiers().values() for fragment in identifiers
    }
    for _, href, _ in book.content_anchors():
        if href.startswith("#"):
            assert href[1:] in targets


def test_two_headings_that_shorten_alike_stay_two_targets(tmp_path: Path) -> None:
    """Truncation alone would make one target of both, and a reader tapping either would reach
    whichever the writer wrote first."""

    shared = " ".join(["indistinguishable"] * 6)
    document = source("A Short Title", f"# {shared} one\n\n{PROSE}\n# {shared} two\n\n{PROSE}")
    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    rewritten = bounding(report)["rewritten"]
    assert len(set(rewritten.values())) == len(rewritten) == 2
    book = PreparedEpub(artifact)
    hrefs = [href for href, _ in book.navigation_anchors()]
    assert len(set(hrefs)) == len(hrefs)


def test_rewriting_an_identifier_moves_no_word(tmp_path: Path) -> None:
    """An identifier is not a word. Text Preservation is what proves the rewrite left the prose
    exactly where it was, on the document that needed the most rewriting."""

    document = source(LONG, f"# {LONG}\n\n{PROSE}\n## {LONG} again\n\n{PROSE}")
    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    tokens = report["artifact"]["text_preservation"]["tokens"]
    assert tokens["unexpected_missing"] == []


def test_the_same_source_still_builds_the_same_bytes(tmp_path: Path) -> None:
    document = source(LONG, f"# {LONG}\n\n{PROSE}")
    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    first, one = journey.output, journey.report
    prepared_source = write_markdown(tmp_path / "control.md", document)
    journey2 = prepare(tmp_path, prepared_source, expected_exit=None)
    second, two = journey2.output, journey2.report

    assert one["outcome"] == two["outcome"] == "completed"
    assert first.read_bytes() == second.read_bytes()


def test_the_reserved_path_length_is_measured_rather_than_assumed(tmp_path: Path) -> None:
    """The budget is the profile's limit less what the writer puts in front of an identifier.
    Galley does not choose that prefix — Pandoc names its own content documents — so it is held
    to a built book rather than trusted."""

    notes = "".join(
        f"A note[^{number}].\n\n[^{number}]: Body {number}.\n\n" for number in range(1, 12)
    )
    prepared_source = write_markdown(tmp_path / "source-0.md", source("A Short Title", notes))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    book = PreparedEpub(artifact)
    prefixes = [
        len(href.split("#")[0].encode("utf-8")) + 1 for href, _ in book.navigation_anchors()
    ]
    assert max(prefixes) <= PATH_RESERVE

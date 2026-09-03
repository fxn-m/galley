"""Prepare a live Article-Like Page through the same pipeline Markdown goes through."""

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from tests.article_fixtures import (
    APPARATUS,
    ARTICLE,
    PAIRED_LINK_HREF,
    PAIRED_LINK_TEXT,
    illustrated_article,
    paired_article,
    paired_markdown,
)
from tests.article_server import (
    served,
    write_html,
)
from tests.image_fixtures import grayscale_png
from tests.prepared_epub import (
    content_anchors,
    content_text,
    epub_version,
    media_resources,
    metadata,
    names,
    navigation_entries,
    spine_documents,
)
from tests.public_cli import run_cli, prepare

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


def test_a_live_url_is_prepared_without_any_intermediate_file(tmp_path: Path) -> None:
    """The locator is the whole input: nothing is authored on disk between page and book."""

    with served(ARTICLE) as url:
        journey = prepare(tmp_path, url)
        output, report = journey.output, journey.report

        assert output.is_file()
        assert epub_version(output) == "3.0"
        assert names(output)[0] == "mimetype"
        assert metadata(output, "title") == ["A Small Essay"]
        assert metadata(output, "creator") == ["Ada Lovelace"]
        assert report["outcome"] == "completed"
        # The isolated journey contains only the artifact and its evidence, with no authored input.
        assert set(journey.output.parent.iterdir()) == {journey.output, journey.evidence}
        assert list(tmp_path.iterdir()) == [journey.output.parent]

        assert report["source"]["kind"] == "article-url"
        assert report["source"]["url"] == url
        assert report["extraction"]["extractor"]["tool"] == "defuddle"
        assert report["extraction"]["words"]["basis"] == "measured"
        assert report["extraction"]["footnote_recovery"]["outcome"] == "not-recognised"
        assert report["canonical_document"]["source_url"] == url
        assert report["preparation"] is not None
        assert report["artifact"] is not None
        # The candidate was audited before publication, not the published bytes afterwards.
        assert report["artifact"]["conformance"]["tool"] == "epubcheck"
        assert report["artifact"]["text_preservation"]["claimed"] is True
        assert report["galley"]["dependencies"]["defuddle"] == "0.19.1"


def test_recovered_notes_become_the_same_one_file_per_note_structure(tmp_path: Path) -> None:
    """A recovered Note is canonical, so the profile's representation applies unchanged."""

    with served(APPARATUS) as url:
        journey = prepare(tmp_path, url)
        output, report = journey.output, journey.report

        assert report["extraction"]["footnote_recovery"]["recovered_notes"]["value"] == 2
        documents = spine_documents(output)
        # One spine item per note, beyond the prose documents.
        assert len(documents) >= 3
        # Exactly one listed Footnotes entry, however many notes there are.
        assert navigation_entries(output).count("Footnotes") == 1


def test_an_illustrated_article_carries_its_images_into_the_book(tmp_path: Path) -> None:
    """A page's images are part of the work, so preparation resolves them from the live page."""

    figure = grayscale_png(tmp_path / "figure.png", width=40, height=30).read_bytes()
    document = illustrated_article("figure.png")

    with served(document, resources={"/figure.png": figure}) as url:
        journey = prepare(tmp_path, url)
        output, report = journey.output, journey.report

        resources = media_resources(output)
        assert len(resources) == 2
        assert figure in resources.values()
        preservation = report["preparation"]["images"]["preservation"]
        # Image Preservation runs on the shared implementation and finds nothing unmapped.
        assert preservation["claimed"] is True
        assert preservation["references"]["value"] == 2
        assert preservation["mapped"]["value"] == 2
        assert preservation["unmapped"]["value"] == 0
        record = next(
            entry for entry in report["preparation"]["images"]["records"] if not entry["cover"]
        )
        assert record["alt"] == "a figure the essay explains"
        assert record["source"]["path"].startswith("http://127.0.0.1:")
        assert record["artifact"]["referenced"] is True


def test_a_resource_that_cannot_be_fetched_refuses_and_publishes_no_book(tmp_path: Path) -> None:
    """A missing image is a refusal, not a book with a hole where a figure was."""

    document = illustrated_article("missing.png")

    with served(document) as url:
        output = tmp_path / "broken-0.epub"
        result = run_cli("prepare", url, "--output", str(output), *ARGUMENTS)

        assert (result.returncode, result.stderr) == (3, "")
        report = json.loads(result.stdout)
        refusal = report["refusal"]
        assert refusal["boundary"] == "image-processing-failure"
        assert refusal["artifact_written"] is False
        assert [failure["reason"] for failure in refusal["fact"]["failures"]] == [
            "unfetchable-resource"
        ]
        assert not output.exists()
        # The evidence a repair needs survives the refusal.
        evidence = tmp_path / "broken-0.galley"
        assert sorted(entry.name for entry in evidence.iterdir()) == [
            "canonical-document.json",
            "extraction.html",
            "preservation-baseline.txt",
            "report.json",
        ]
        assert report["extraction"]["extractor"]["status"] == "ok"


def _treatment(report: Any, output: Path) -> dict[str, object]:
    """Describe how the pipeline treated one document, independently of what the document was."""

    transforms = {entry["name"]: entry for entry in report["preparation"]["transforms"]}
    links, notes = transforms["link-stripping"], transforms["note-conversion"]
    return {
        "notes_converted": notes["notes"],
        "note_documents": notes["note_documents"],
        "back_links": notes["backlinks"],
        "apparatus_recognised": links["interlock"]["apparatus_recognised"],
        "interlock_engaged": links["interlock"]["engaged"],
        "web_links_removed": links["kinds"]["web-link"]["removed"],
        "text_preservation_claimed": report["artifact"]["text_preservation"]["claimed"],
        "unexpected_missing": report["artifact"]["text_preservation"]["tokens"][
            "unexpected_missing"
        ],
        "footnotes_entries": navigation_entries(output).count("Footnotes"),
        "spine_documents": len(spine_documents(output)),
    }


def test_equivalent_markdown_and_article_content_get_the_same_downstream_treatment(
    tmp_path: Path,
) -> None:
    """The two routes differ in how the document arrived and in nothing after that.

    The same prose, the same web link and the same single note are written once as Markdown and
    once as the shape Defuddle produces. Once both are Canonical Documents, every transform,
    both preservation checks and the published structure must agree.
    """

    source = tmp_path / "paired.md"
    _ = source.write_text(paired_markdown(), encoding="utf-8")
    markdown_output = tmp_path / "from-markdown.epub"
    markdown_result = run_cli("prepare", str(source), "--output", str(markdown_output), *ARGUMENTS)
    assert (markdown_result.returncode, markdown_result.stderr) == (0, "")

    with served(paired_article()) as url:
        article_output = tmp_path / "from-article.epub"
        article_result = run_cli("prepare", url, "--output", str(article_output), *ARGUMENTS)
        assert (article_result.returncode, article_result.stderr) == (0, "")

    from_markdown = _treatment(json.loads(markdown_result.stdout), markdown_output)
    from_article = _treatment(json.loads(article_result.stdout), article_output)

    assert from_markdown == from_article
    assert cast(Any, from_article["notes_converted"])["value"] == 1
    assert cast(Any, from_article["web_links_removed"])["value"] == 1
    assert from_article["apparatus_recognised"] is True
    assert from_article["unexpected_missing"] == []
    # The link's visible text survives in both books while its href does not.
    for output in (markdown_output, article_output):
        assert PAIRED_LINK_TEXT in content_text(output)
        assert PAIRED_LINK_HREF not in "".join(href for href, _, _ in content_anchors(output))


def test_local_html_still_refuses_at_prepare_and_writes_nothing(tmp_path: Path) -> None:
    """The single HTML route holds on the building command too, not only on inspect."""

    source = write_html(tmp_path / "saved.html")
    original = source.read_bytes()

    output = tmp_path / "saved-0.epub"
    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS)

    assert (result.returncode, result.stderr) == (3, "")
    report = json.loads(result.stdout)
    assert report["refusal"]["boundary"] == "unsupported-source-kind"
    assert report["refusal"]["fact"]["kind"] == "local-html"
    assert "an http:// or https:// Article-Like Page" in report["refusal"]["fact"]["accepted"]
    assert not output.exists()
    # No tool ran, so the saved page was never extracted or even read.
    assert report["galley"]["dependencies"] == {}
    assert source.read_bytes() == original


def test_the_published_book_is_the_audited_one_and_no_optimize_step_exists(
    tmp_path: Path,
) -> None:
    """The artifact must be raw-upload-ready, so nothing is left for the reader to run."""

    with served(ARTICLE) as url:
        journey = prepare(tmp_path, url)
        output, report = journey.output, journey.report

        conformance = report["artifact"]["conformance"]
        assert conformance["tool"] == "epubcheck"
        # The audited subject is the published bytes, so no post-publication step is implied.
        assert report["artifact"]["sha256"] == sha256(output.read_bytes()).hexdigest()
        assert report["artifact"]["path"] == str(output)
        serialised = json.dumps(report).casefold()
        assert "optimize" not in serialised
        assert "optimise" not in serialised

    help_result = run_cli("prepare", "--help")
    assert "optimize" not in help_result.stdout.casefold()

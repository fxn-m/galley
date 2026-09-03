import json
from hashlib import sha256
from pathlib import Path

import pytest

from tests.markdown_fixtures import (
    MARKED_CONTENT,
    PLAIN_BOOK,
    UNTITLED,
    native_ast,
    write_markdown,
)
from tests.prepared_epub import PreparedEpub
from tests.public_cli import run_cli, prepare

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


@pytest.mark.real_epubcheck
def test_prepare_publishes_a_conformant_book_with_navigation_and_measured_evidence(
    tmp_path: Path,
) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)
    original = source.read_bytes()

    journey = prepare(tmp_path, str(source))
    output, report = journey.output, journey.report

    assert output.is_file()
    book = PreparedEpub(output)
    assert book.epub_version() == "3.0"
    assert book.names()[0] == "mimetype"
    assert book.metadata("title") == ["A Plain Book"]
    assert book.metadata("creator") == ["Ada Lovelace"]
    assert len(book.spine_documents()) >= 2
    evidence = journey.evidence
    assert sorted(entry.name for entry in evidence.iterdir()) == [
        "canonical-document.json",
        "preservation-baseline.txt",
        "previews",
        "report.json",
    ]
    assert json.loads((evidence / "report.json").read_text(encoding="utf-8")) == report
    document = json.loads((evidence / "canonical-document.json").read_text(encoding="utf-8"))
    assert document["pandoc"] == native_ast(source)
    assert source.read_bytes() == original

    # The nested section is listed: at the former depth of one, a book's sections were absent
    # from its navigation, and on
    # this device navigation membership is what page breaks follow.
    assert book.navigation_entries() == ["Chapter One", "A section inside it", "Chapter Two"]
    depth = next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "navigation-depth"
    )
    assert depth["fired"] is True
    assert depth["activation"] == "toc_depth"
    assert depth["device_judged"] is True
    assert depth["depth"] == {"basis": "reported", "unit": "levels", "value": 3}

    assert report["galley"]["command"] == "prepare"
    assert (report["outcome"], report["refusal"]) == ("completed", None)
    artifact = report["artifact"]
    assert artifact["path"] == str(output.resolve())
    assert artifact["sha256"] == sha256(output.read_bytes()).hexdigest()
    assert artifact["byte_size"]["value"] == output.stat().st_size
    assert artifact["package"]["version"] == "3.0"
    assert artifact["conformance"]["checked"] is True
    assert artifact["conformance"]["counts"]["error"]["value"] == 0
    packaging = report["preparation"]["packaging"]
    assert packaging["tool"] == "pandoc"
    assert (packaging["reader"], packaging["writer"]) == ("json", "epub3")
    assert packaging["matches_pinned_version"] is True
    assert packaging["exit_status"] == {"basis": "measured", "unit": "status", "value": 0}

    results = report["compatibility"]
    assert [entry["requirement_id"] for entry in results] == [
        "anchors-per-chapter",
        "footnote-href-length",
        "footnotes-per-screen",
        "image-media-type",
        "jpeg-decoding",
        "png-decoding",
        "recorded-links-per-block",
    ]
    bases = {
        entry["measurement"]["basis"] for entry in results if isinstance(entry["measurement"], dict)
    }
    assert bases <= {"measured"}

    evidence = journey.evidence
    document = json.loads((evidence / "canonical-document.json").read_text(encoding="utf-8"))
    packaged = report["preparation"]["canonical_document"]
    assert packaged["transformed"] is False
    assert packaged["retained_ast_sha256"] == packaged["packaged_ast_sha256"]
    assert packaged["sha256"] == report["canonical_document"]["sha256"]
    assert (
        packaged["sha256"]
        == sha256((evidence / "canonical-document.json").read_bytes()).hexdigest()
    )
    assert document["pandoc"]["blocks"]


def test_evidence_is_deterministic_across_runs(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)
    retained: list[tuple[bytes, bytes]] = []

    for _ in range(2):
        journey = prepare(tmp_path, str(source))
        _, report = journey.output, journey.report

        evidence = journey.evidence
        retained.append(
            (
                (evidence / "canonical-document.json").read_bytes(),
                (evidence / "preservation-baseline.txt").read_bytes(),
            )
        )
        assert report["canonical_document"]["title"] == "A Plain Book"

    assert retained[0] == retained[1]


def test_no_activated_observation_is_retired_by_preparation(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "marked.md", MARKED_CONTENT)

    journey = prepare(tmp_path, str(source))
    _, report = journey.output, journey.report

    inspected = run_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json")
    assert inspected.returncode == 0
    activated = [entry["name"] for entry in report["observations"]]
    projected = [entry["name"] for entry in json.loads(inspected.stdout)["observations"]]
    assert activated == projected
    fired = {entry["name"]: entry["fired"] for entry in report["observations"]}
    assert fired["page-break-content-destruction"] is True
    assert fired["unrenderable-glyphs"] is True


def test_a_transform_with_nothing_to_do_says_so_rather_than_going_silent(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", UNTITLED)

    journey = prepare(tmp_path, str(source))
    output, report = journey.output, journey.report

    transforms = {entry["name"]: entry for entry in report["preparation"]["transforms"]}
    assert transforms["document-author"]["fired"] is False
    assert transforms["document-author"]["author"] is None
    assert "states no author" in transforms["document-author"]["note"]
    assert transforms["document-title"]["fired"] is True
    assert transforms["document-title"]["title_source"] == "filename"
    book = PreparedEpub(output)
    assert book.metadata("title") == ["plain"]
    assert book.metadata("creator") == []


def test_the_audit_workflow_cannot_be_bypassed(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    refused = run_cli(
        "prepare",
        str(source),
        "--output",
        str(tmp_path / "skipped-0.epub"),
        *ARGUMENTS,
        "--skip-audit",
    )

    assert refused.returncode == 2
    assert not (tmp_path / "skipped-0.epub").exists()
    journey = prepare(tmp_path, str(source))
    _, report = journey.output, journey.report
    assert report["artifact"]["conformance"]["checked"] is True
    assert report["galley"]["dependencies"]["epubcheck"] == "5.3.0"


def test_human_output_names_every_transform_and_the_published_artifact(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    output = tmp_path / "human-0.epub"
    result = run_cli("prepare", str(source), "--output", str(output), "--profile", "x4-crosspoint")

    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout.startswith("prepare: completed\n")
    assert "Preparation: 12 transforms, 5 fired; Canonical Document unchanged\n" in result.stdout
    assert "Transform: document-title (fired)\n" in result.stdout
    assert "Transform: document-author (fired)\n" in result.stdout
    assert "Transform: document-language (fired)\n" in result.stdout
    assert "Transform: link-stripping (no-op)\n" in result.stdout
    assert "Transform: note-conversion (no-op)\n" in result.stdout
    assert "Transform: duplicate-caption-suppression (no-op)\n" in result.stdout
    assert "Transform: callout-title-emphasis (no-op)\n" in result.stdout
    assert "Transform: raw-html-balance (no-op)\n" in result.stdout
    assert "Transform: identifier-bounding (no-op)\n" in result.stdout
    assert "Transform: image-preparation (fired)\n" in result.stdout
    assert 'Cover: Default Cover, "A Plain Book" by Ada Lovelace\n' in result.stdout
    assert "Transform: attribute-namespacing (no-op)\n" in result.stdout
    assert "Transform: navigation-depth (fired)\n" in result.stdout
    assert "Packaging: pandoc 3.10 to epub3 (exit 0)\n" in result.stdout
    assert f"Artifact: {output.resolve()}\n" in result.stdout


def test_the_evidence_directory_can_be_placed_anywhere(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    chosen = tmp_path / "chosen-0"
    journey = prepare(tmp_path, str(source), "--evidence-dir", str(chosen))
    output, _ = journey.output, journey.report

    assert output.is_file()
    assert (chosen / "report.json").is_file()
    assert not journey.output.with_suffix(".galley").exists()

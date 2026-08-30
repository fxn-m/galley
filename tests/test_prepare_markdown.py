import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from tests.markdown_fixtures import (
    MARKED_CONTENT,
    PLAIN_BOOK,
    UNTITLED,
    native_ast,
    write_markdown,
)
from tests.prepared_epub import (
    epub_version,
    metadata,
    names,
    navigation_entries,
    spine_documents,
)
from tests.public_cli import public_cli_commands, run_command

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


def prepared(tmp_path: Path, index: int, command: list[str], *extra: str) -> tuple[Path, Any]:
    """Run one entry point into its own output path and return the artifact and its Report."""

    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, "--output", str(output), *ARGUMENTS, *extra)
    assert (result.returncode, result.stderr) == (0, "")
    return output, json.loads(result.stdout)


def test_prepare_publishes_an_epub3_and_its_evidence_bundle(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)
    original = source.read_bytes()

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output, report = prepared(tmp_path, index, command)

        assert output.is_file()
        assert epub_version(output) == "3.0"
        assert names(output)[0] == "mimetype"
        assert metadata(output, "title") == ["A Plain Book"]
        assert metadata(output, "creator") == ["Ada Lovelace"]
        assert len(spine_documents(output)) >= 2
        evidence = tmp_path / f"book-{index}.galley"
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


def test_the_profiles_navigation_depth_governs_generated_navigation(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output, report = prepared(tmp_path, index, command)

        # The nested section is listed: at the former depth of one, a book's sections were absent
        # from its navigation, and on
        # this device navigation membership is what page breaks follow.
        assert navigation_entries(output) == ["Chapter One", "A section inside it", "Chapter Two"]
        depth = next(
            entry
            for entry in report["preparation"]["transforms"]
            if entry["name"] == "navigation-depth"
        )
        assert depth["fired"] is True
        assert depth["activation"] == "toc_depth"
        assert depth["device_judged"] is True
        assert depth["depth"] == {"basis": "reported", "unit": "levels", "value": 3}


# The one prepare test that proves a prepared artifact truly conforms, so it pays for
# the real checker while the rest of the suite uses the instant stand-in.
@pytest.mark.real_epubcheck
def test_the_report_carries_the_measured_artifact_and_its_packaging(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output, report = prepared(tmp_path, index, command)

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


def test_compatibility_is_measured_on_the_artifact_not_projected(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

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
            entry["measurement"]["basis"]
            for entry in results
            if isinstance(entry["measurement"], dict)
        }
        assert bases <= {"measured"}


def test_the_packaged_ast_is_the_retained_canonical_document(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

        evidence = tmp_path / f"book-{index}.galley"
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

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

        evidence = tmp_path / f"book-{index}.galley"
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

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

        inspected = run_command(
            public_cli_commands("inspect", str(source))[index],
            "--profile",
            "x4-crosspoint",
            "--json",
        )
        assert inspected.returncode == 0
        activated = [entry["name"] for entry in report["observations"]]
        projected = [entry["name"] for entry in json.loads(inspected.stdout)["observations"]]
        assert activated == projected
        fired = {entry["name"]: entry["fired"] for entry in report["observations"]}
        assert fired["page-break-content-destruction"] is True
        assert fired["unrenderable-glyphs"] is True


def test_a_transform_with_nothing_to_do_says_so_rather_than_going_silent(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", UNTITLED)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output, report = prepared(tmp_path, index, command)

        transforms = {entry["name"]: entry for entry in report["preparation"]["transforms"]}
        assert transforms["document-author"]["fired"] is False
        assert transforms["document-author"]["author"] is None
        assert "states no author" in transforms["document-author"]["note"]
        assert transforms["document-title"]["fired"] is True
        assert transforms["document-title"]["title_source"] == "filename"
        assert metadata(output, "title") == ["plain"]
        assert metadata(output, "creator") == []


def test_the_audit_workflow_cannot_be_bypassed(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        refused = run_command(
            command,
            "--output",
            str(tmp_path / f"skipped-{index}.epub"),
            *ARGUMENTS,
            "--skip-audit",
        )

        assert refused.returncode == 2
        assert not (tmp_path / f"skipped-{index}.epub").exists()
        _, report = prepared(tmp_path, index, command)
        assert report["artifact"]["conformance"]["checked"] is True
        assert report["galley"]["dependencies"]["epubcheck"] == "5.3.0"


def test_human_output_names_every_transform_and_the_published_artifact(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output = tmp_path / f"human-{index}.epub"
        result = run_command(
            command,
            "--output",
            str(output),
            "--profile",
            "x4-crosspoint",
        )

        assert (result.returncode, result.stderr) == (0, "")
        assert result.stdout.startswith("prepare: completed\n")
        assert (
            "Preparation: 12 transforms, 5 fired; Canonical Document unchanged\n" in result.stdout
        )
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

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        chosen = tmp_path / f"chosen-{index}"
        output, _ = prepared(tmp_path, index, command, "--evidence-dir", str(chosen))

        assert output.is_file()
        assert (chosen / "report.json").is_file()
        assert not (tmp_path / f"book-{index}.galley").exists()

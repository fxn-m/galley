"""Recover Defuddle's normalised Footnote Apparatus into canonical Notes, or leave it alone."""

import json
from pathlib import Path
from typing import Any

from tests.support.article_fixtures import (
    APPARATUS,
    APPARATUS_MISMATCHED,
    APPARATUS_MULTI_PARAGRAPH,
    APPARATUS_WITH_EMPTY_NOTE,
    APPARATUS_WITH_STRAY_ITEM,
    APPARATUS_WITHOUT_TARGETS,
    LOOKALIKE_LINKS,
    filler,
)
from tests.support.article_server import (
    defuddle_returning,
    extracted_content,
    native_html_ast,
    served,
)
from tests.support.markdown_fixtures import write_markdown
from tests.support.public_cli import run_cli

CONVENTION = "doc-noteref-endnotes"


def inspect_json(source: str, *extra: str) -> Any:
    result = run_cli("inspect", source, "--profile", "x4-crosspoint", "--json", *extra)
    assert (result.returncode, result.stderr) == (0, "")
    return json.loads(result.stdout)


def test_the_recognised_shape_becomes_canonical_notes() -> None:
    """Both halves of the relabel run, so every recovered Note carries its text."""

    with served(APPARATUS) as url:
        report = inspect_json(url)
        recovery = report["extraction"]["footnote_recovery"]
        assert recovery["outcome"] == "recovered"
        assert recovery["convention"] == CONVENTION
        assert recovery["basis"] == "measured"
        assert recovery["references"]["value"] == 2
        assert recovery["definitions"]["value"] == 2
        assert recovery["recovered_notes"]["value"] == 2
        assert recovery["empty_notes"]["value"] == 0
        assert recovery["mismatch"]["value"] == 0
        assert recovery["reason"] is None
        # The Canonical Document holds the notes, which is what the interlock counts.
        assert report["canonical_document"]["reading"]["notes"]["value"] == 2


def test_a_recovered_note_reaches_the_baseline_and_carries_its_paragraphs(tmp_path: Path) -> None:
    """Recovery runs before the Canonical Document, so note text is in the fixed point too."""

    with served(APPARATUS_MULTI_PARAGRAPH) as url:
        evidence = tmp_path / "evidence-0"
        result = run_cli(
            "inspect", url, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        baseline = (evidence / "preservation-baseline.txt").read_text(encoding="utf-8")
        assert "Firstpara body here." in baseline
        assert "Secondpara body here." in baseline
        report = json.loads(result.stdout)
        assert report["extraction"]["footnote_recovery"]["outcome"] == "recovered"
        assert report["canonical_document"]["reading"]["notes"]["value"] == 1


def test_references_without_targets_leave_the_content_unchanged() -> None:
    """Extraction dropped the targets, so there is nothing to pair and nothing is invented."""

    with served(APPARATUS_WITHOUT_TARGETS) as url:
        report = inspect_json(url)
        recovery = report["extraction"]["footnote_recovery"]
        assert recovery["outcome"] == "skipped"
        assert recovery["reason"] == "no-definitions"
        assert recovery["references"]["value"] == 2
        assert recovery["definitions"]["value"] == 0
        assert recovery["recovered_notes"]["value"] == 0
        assert report["canonical_document"]["reading"]["notes"]["value"] == 0


def test_mismatched_counts_refuse_recovery_for_the_whole_document() -> None:
    """Recovering only the paired half would leave the other reference pointing at nothing."""

    with served(APPARATUS_MISMATCHED) as url:
        report = inspect_json(url)
        recovery = report["extraction"]["footnote_recovery"]
        assert recovery["outcome"] == "skipped"
        assert recovery["reason"] == "reference-definition-mismatch"
        assert (recovery["references"]["value"], recovery["definitions"]["value"]) == (2, 1)
        assert recovery["mismatch"]["value"] == 1
        assert recovery["recovered_notes"]["value"] == 0
        # The note that would have paired stays readable in place instead.
        assert report["canonical_document"]["reading"]["notes"]["value"] == 0
        assert report["extraction"]["words"]["value"] > 0


def test_one_empty_note_refuses_recovery_of_every_note(tmp_path: Path) -> None:
    """A blank note is worse than no note, so the good recovery is refused with the bad one."""

    with served(APPARATUS_WITH_EMPTY_NOTE) as url:
        evidence = tmp_path / "evidence-0"
        result = run_cli(
            "inspect", url, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        recovery = json.loads(result.stdout)["extraction"]["footnote_recovery"]
        assert recovery["outcome"] == "skipped"
        assert recovery["reason"] == "empty-note"
        assert recovery["empty_notes"]["value"] == 1
        assert recovery["recovered_notes"]["value"] == 0
        # No text was lost by refusing; the surviving note is still readable in place.
        baseline = (evidence / "preservation-baseline.txt").read_text(encoding="utf-8")
        assert "Firstnote body here." in baseline


def test_a_note_that_parses_to_nothing_refuses_recovery_of_every_note(tmp_path: Path) -> None:
    """The markup says every definition carries text and the parse says none of them do.

    One observed article shipped seventeen blank footnote pages this way: one stray `<li>` inside
    a note's `<p>` makes Pandoc's HTML5 parser restructure the list, and every note comes
    out empty — including the one that was well-formed. Emptiness is a property of the notes the
    pipeline produced, so that is where the rule is applied.
    """

    with served(APPARATUS_WITH_STRAY_ITEM) as url:
        evidence = tmp_path / "stray-0"
        result = run_cli(
            "inspect", url, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        report = json.loads(result.stdout)
        recovery = report["extraction"]["footnote_recovery"]
        assert (recovery["outcome"], recovery["reason"]) == ("skipped", "empty-note")
        assert recovery["recovered_notes"]["value"] == 0
        assert recovery["empty_notes"]["value"] == 2
        assert report["canonical_document"]["reading"]["notes"]["value"] == 0
        # Nothing was lost by refusing: both notes are still readable in place.
        baseline = (evidence / "preservation-baseline.txt").read_text(encoding="utf-8")
        assert "Firstnote body here." in baseline
        assert "Secondnote body here." in baseline


def test_a_duplicate_target_refuses_recovery(tmp_path: Path) -> None:
    """An identifier defined twice makes the pairing ambiguous, so nothing is relabelled."""

    duplicated = (
        '<article><p>Alpha bravo charlie.<sup id="fnref:1"><a href="#fn:1">1</a></sup></p>'
        f"{filler()}"
        '<div id="footnotes"><ol>'
        '<li id="fn:1"><p>Firstnote body here.</p></li>'
        '<li id="fn:1"><p>Duplicate body here.</p></li>'
        "</ol></div></article>"
    )
    command_path = defuddle_returning(tmp_path / "defuddle", duplicated)

    with served() as url:
        result = run_cli(
            "inspect",
            url,
            "--profile",
            "x4-crosspoint",
            "--json",
            environment={"GALLEY_DEFUDDLE": str(command_path)},
        )

    assert (result.returncode, result.stderr) == (0, "")
    recovery = json.loads(result.stdout)["extraction"]["footnote_recovery"]
    assert recovery["outcome"] == "skipped"
    assert recovery["reason"] == "duplicate-target"
    assert recovery["recovered_notes"]["value"] == 0


def test_lookalike_links_are_not_an_apparatus_and_are_left_alone() -> None:
    """A link whose href resembles a reference is not a Footnote Apparatus and is not treated as one."""

    with served(LOOKALIKE_LINKS) as url:
        report = inspect_json(url)
        recovery = report["extraction"]["footnote_recovery"]
        assert recovery["outcome"] == "not-recognised"
        assert recovery["reason"] == "no-apparatus"
        assert recovery["convention"] is None
        assert recovery["references"]["value"] == 0
        assert recovery["recovered_notes"]["value"] == 0
        assert report["canonical_document"]["reading"]["notes"]["value"] == 0
        # The link itself survives untouched, for the link transforms to decide about.
        assert report["canonical_document"]["reading"]["links"]["value"] == 1


def test_content_outside_the_convention_is_carried_through_untouched(tmp_path: Path) -> None:
    """Recognition rewrites two places or none; it is never a cleanup pass over the document.

    The proof is independent: the Canonical Document must equal Defuddle's own output parsed
    directly, so any styling this pass had quietly removed would show up as a difference.
    """

    with served(LOOKALIKE_LINKS) as url:
        content = extracted_content(url)
        evidence = tmp_path / "evidence-0"
        result = run_cli(
            "inspect", url, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        document = json.loads((evidence / "canonical-document.json").read_text("utf-8"))
        assert document["pandoc"] == native_html_ast(content, tmp_path)


def test_a_markdown_source_never_reports_extraction_facts(tmp_path: Path) -> None:
    """Recovery is an extraction-stage pass; a Markdown source has no extraction stage at all."""

    source = write_markdown(tmp_path / "notes.md")

    result = run_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json")

    assert (result.returncode, result.stderr) == (0, "")
    assert json.loads(result.stdout)["extraction"] is None

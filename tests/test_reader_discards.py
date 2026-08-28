"""What a Report says when the source reader dropped content before Galley could see it.

The Preservation Baseline is rendered from the Pandoc AST, so it is taken after the reader
has run. Everything Galley is handed does survive, and a claim scoped to that is true and
misleading: an observed dense-note document defined 42 footnotes, referenced 40, and built a book
missing a paragraph while the Report claimed Text Preservation.
"""

import json
from pathlib import Path
from typing import Any

from tests.article_fixtures import filler
from tests.article_server import served
from tests.markdown_fixtures import native_ast, write_markdown
from tests.repair_fixtures import RepairInputs, inspected, repaired_document
from tests.prepared_epub import content_text
from tests.public_cli import public_cli_commands, run_command

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
ORPHAN_TEXT = "Nobody points at this note and its words go nowhere."
# A note definition nothing references. Pandoc's Markdown reader drops it, warns on stderr, and
# the AST that follows carries no trace of the words — so no measurement taken from that AST can
# tell that they are gone.
ORPHANED = f"""---
title: An Orphaned Note
---

# An Orphaned Note

Prose that runs long enough to read as a document, carrying one real note.[^2]

[^1]: {ORPHAN_TEXT}

[^2]: A note something does point at.
"""
WHOLE = """---
title: A Whole Document
---

# A Whole Document

Prose that runs long enough to read as a document, carrying one real note.[^1]

[^1]: A note something does point at.
"""


def prepared(tmp_path: Path, index: int, command: list[str]) -> tuple[Path, Any]:
    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, "--output", str(output), *ARGUMENTS)
    assert (result.returncode, result.stderr) == (0, "")
    return output, json.loads(result.stdout)


def discarded(report: Any) -> Any:
    return report["artifact"]["text_preservation"]["discarded"]


def test_the_reader_dropping_a_note_is_recorded_as_a_fact(tmp_path: Path) -> None:
    """A warning string joined to nothing cannot qualify a claim, so the shapes Galley recognises
    as discards become facts something can read."""

    source = write_markdown(tmp_path / "orphaned.md", ORPHANED)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

        assert report["outcome"] == "completed"
        assert discarded(report)["count"]["value"] == 1
        assert [entry["kind"] for entry in discarded(report)["items"]] == ["unreferenced-note"]
        assert discarded(report)["items"][0]["identifier"] == "1"


def test_a_run_whose_reader_discarded_content_claims_no_text_preservation(
    tmp_path: Path,
) -> None:
    """The words are really gone from the book, and the measurement really does show nothing
    missing. Both are true, and only one of them is what "claimed" means."""

    source = write_markdown(tmp_path / "orphaned.md", ORPHANED)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        artifact, report = prepared(tmp_path, index, command)

        preservation = report["artifact"]["text_preservation"]
        assert ORPHAN_TEXT not in content_text(artifact)
        assert preservation["tokens"]["unexpected_missing"] == []
        assert preservation["claimed"] is False
        assert preservation["reason"] == "source-reader-discarded-content"
        # The measurement is kept, because it is still true of what Galley was handed.
        assert preservation["tokens"]["baseline"]["value"] > 0


def test_the_document_still_completes_and_publishes_its_book(tmp_path: Path) -> None:
    """The document still completes because refusing all unreferenced notes would also discard
    valid dense-note documents."""

    source = write_markdown(tmp_path / "orphaned.md", ORPHANED)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        artifact, report = prepared(tmp_path, index, command)

        assert (report["outcome"], report["refusal"]) == ("completed", None)
        assert artifact.is_file()


def test_the_human_output_carries_the_same_qualification(tmp_path: Path) -> None:
    """A concise renderer dropping it while the JSON keeps it is the same defect one surface
    over: the reader of the terminal takes the measurement for the claim."""

    source = write_markdown(tmp_path / "orphaned.md", ORPHANED)

    for command in public_cli_commands("prepare", str(source)):
        result = run_command(
            command,
            "--output",
            str(tmp_path / "rendered.epub"),
            "--profile",
            "x4-crosspoint",
            "--overwrite",
        )

        assert result.returncode == 0
        assert "Text Preservation: not claimed (the source reader discarded content" in (
            result.stdout
        )


def test_a_document_whose_reader_discarded_nothing_says_so(tmp_path: Path) -> None:
    """Silence and "nothing was dropped" are the same absence to a reader of the Report, and this
    is now the field a Text Preservation claim rests on."""

    source = write_markdown(tmp_path / "whole.md", WHOLE)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

        assert discarded(report) == {**discarded(report), "items": []}
        assert discarded(report)["count"]["value"] == 0
        preservation = report["artifact"]["text_preservation"]
        assert (preservation["claimed"], preservation["reason"]) == (True, None)


def test_a_warning_that_is_not_a_discard_qualifies_nothing(tmp_path: Path) -> None:
    """Under-claiming is the safe direction, but a message that is not a discard must not suppress
    a true claim. An unclosed div is a real Pandoc warning and drops no word."""

    source = write_markdown(
        tmp_path / "unclosed.md",
        "---\ntitle: An Unclosed Div\n---\n\n# An Unclosed Div\n\n"
        "::: aside\n\nProse that runs long enough to read as a document of its own.\n",
    )

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

        assert [entry["event"] for entry in report["warnings"]] == ["pandoc-message"]
        assert discarded(report)["count"]["value"] == 0
        assert report["artifact"]["text_preservation"]["claimed"] is True


def test_an_extracted_page_carries_its_readers_discards_too(tmp_path: Path) -> None:
    """The article route once rebuilt its Inspection by naming four fields and silently dropped
    every one it did not name. The rebuild now replaces rather than reconstructs.
    """

    page = f"""<!doctype html>
<html lang="en"><head><title>An Orphaned Note</title></head><body>
<article><h1>An Orphaned Note</h1>
<p>Text with a real note.<sup id="fnref:2"><a href="#fn:2">2</a></sup></p>
{filler()}
<div id="footnotes"><ol>
<li id="fn:1"><p>{ORPHAN_TEXT}</p></li>
<li id="fn:2"><p>A note something does point at.</p></li>
</ol></div>
</article></body></html>
"""
    with served(page) as url:
        for index, command in enumerate(public_cli_commands("prepare", url)):
            output = tmp_path / f"article-{index}.epub"
            result = run_command(command, "--output", str(output), *ARGUMENTS)
            report = json.loads(result.stdout)

            assert (result.returncode, report["outcome"]) == (0, "completed")
            # Zero, and stated: no shape Galley recognises as a discard comes out of Pandoc's HTML
            # reader today, so what this holds is that the field survives the route rather than
            # what it contains. `test_prepare_language.py` holds the same rebuild on a field this
            # route does fill, which is where the defect was actually caught.
            assert discarded(report) == {
                **discarded(report),
                "count": {"basis": "measured", "unit": "items", "value": 0},
                "items": [],
            }


def test_a_repaired_document_carries_the_discards_of_the_reader_that_read_its_source(
    tmp_path: Path,
) -> None:
    """`prepare` runs no reader at all on this route — the Canonical Document is handed to it —
    so the discards have to travel on the document. A localised document prepares from what
    `localise`'s parse left, and `localise` is where the reader ran."""

    source = write_markdown(tmp_path / "orphaned.md", ORPHANED)
    evidence = inspected(tmp_path / "orphaned.galley", str(source))
    canonical = repaired_document(
        evidence,
        tmp_path / "repaired.json",
        native_ast(write_markdown(tmp_path / "repaired.md", ORPHANED)),
    )
    repair = RepairInputs(
        evidence / "report.json", canonical, evidence / "preservation-baseline.txt"
    )

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        result = run_command(
            command,
            "--output",
            str(tmp_path / f"repaired-{index}.epub"),
            *ARGUMENTS,
            *repair.options,
        )
        report = json.loads(result.stdout)

        assert (result.returncode, report["outcome"]) == (0, "completed")
        assert discarded(report)["count"]["value"] == 1
        assert report["artifact"]["text_preservation"]["claimed"] is False

"""Raw HTML reaches the book verbatim, so a tag with no partner destroys it. These hold the line.

The failure this exists for is not hypothetical: one `</div>` from a code sample inside a list
item made a real document's chapter unparseable, EPUBCheck report a fatal `RSC-016`, and
the text measurement read 2,299 of 27,298 tokens — a book reported as losing four thousand words
that had lost none.
"""

import json
from pathlib import Path
from typing import Any

from tests.support.markdown_fixtures import write_markdown
from tests.support.prepared_epub import PreparedEpub
from tests.support.public_cli import prepare, run_cli

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
PROSE = "Prose that runs long enough to read as a document rather than as a fragment of one."


def source(*, body: str = "", raw: str = "") -> str:
    """One document with a stated title, prose on both sides, and the raw markup under test."""

    block = f"```{{=html}}\n{raw}\n```\n\n" if raw else ""
    return (
        f'---\ntitle: "A Raw Book"\n---\n\n# A Raw Book\n\n{PROSE}\n\n'
        f"{block}{body}\n\n{PROSE} And again, on the other side.\n"
    )


def balance(report: Any) -> Any:
    return next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "raw-html-balance"
    )


def test_a_closing_tag_with_no_partner_is_dropped_and_the_book_builds(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", source(raw="</div>"))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert balance(report)["payloads"] == ["</div>"]
    assert balance(report)["dropped"]["value"] == 1
    assert report["artifact"]["problems"] == []
    book = PreparedEpub(artifact)
    assert PROSE in book.content_text()


def test_an_opening_tag_with_no_partner_goes_the_same_way(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", source(raw='<div class="orphan">'))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert balance(report)["payloads"] == ['<div class="orphan">']


def test_a_pair_split_across_two_raw_nodes_survives_untouched(tmp_path: Path) -> None:
    """The shape that actually occurs: Pandoc reads `H<sub>2</sub>O` as an opening raw inline, a
    string, and a closing raw inline. Judging balance inside one node would drop both halves of a
    perfectly good element."""

    prepared_source = write_markdown(
        tmp_path / "source-0.md", source(body="Water is H<sub>2</sub>O.")
    )
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    artifact, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert balance(report) == {**balance(report), "fired": False, "payloads": []}
    assert "<sub>2</sub>" in _chapter(artifact)


def test_a_self_closing_element_is_not_waiting_for_a_partner(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", source(raw="<div>one<hr/>two</div>"))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert balance(report)["fired"] is False


def test_a_document_with_no_raw_markup_still_says_the_step_ran(tmp_path: Path) -> None:
    """ "Nothing was dropped" and "the step is broken" have to stay distinguishable."""

    prepared_source = write_markdown(tmp_path / "source-0.md", source(body="Ordinary prose only."))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert balance(report) == {
        **balance(report),
        "fired": False,
        "payloads": [],
        "dropped": {"basis": "measured", "unit": "nodes", "value": 0},
    }


def test_dropping_a_tag_moves_no_word(tmp_path: Path) -> None:
    """A structural tag carries no reader-visible text, which is what makes this safe at all."""

    prepared_source = write_markdown(tmp_path / "source-0.md", source(raw="</div>"))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    tokens = report["artifact"]["text_preservation"]["tokens"]
    assert tokens["unexpected_missing"] == []


def test_the_retained_canonical_document_is_not_edited(tmp_path: Path) -> None:
    """The drop happens on the private working copy. The persisted Canonical Document remains as
    parsed, so the evidence still shows the document that arrived."""

    prepared_source = write_markdown(tmp_path / "source-0.md", source(raw="</div>"))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    evidence = journey.evidence / "canonical-document.json"
    assert "</div>" in evidence.read_text(encoding="utf-8")
    assert report["preparation"]["canonical_document"]["transformed"] is True


def test_the_same_source_still_builds_the_same_bytes(tmp_path: Path) -> None:
    document = source(raw="</div>")
    prepared_source = write_markdown(tmp_path / "source-0.md", document)
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    first, one = journey.output, journey.report
    prepared_source = write_markdown(tmp_path / "control.md", document)
    journey2 = prepare(tmp_path, prepared_source, expected_exit=None)
    second, two = journey2.output, journey2.report

    assert one["outcome"] == two["outcome"] == "completed"
    assert first.read_bytes() == second.read_bytes()


def test_a_chapter_that_is_still_not_well_formed_is_named_rather_than_blamed_on_lost_words(
    tmp_path: Path,
) -> None:
    """Balance is not the only way raw markup breaks XML, and this is deliberately not repaired:
    `<br>` is legal HTML that the writer emits verbatim and XML will not accept, and closing it
    would be Galley inferring what an author meant, which stays the agent's job. So the balancer
    leaves it — a void element is not waiting for a partner — and the run refuses naming the
    chapter. What must not happen is thousands of missing tokens being reported for a chapter no
    parser read.

    The same holds for an HTML comment carrying a double hyphen, which is the other shape.
    """

    written = write_markdown(tmp_path / "malformed-0.md", source(raw="<div>one<br>two</div>"))
    original = written.read_bytes()
    output = tmp_path / "malformed-0.epub"
    result = run_cli("prepare", str(written), "--output", str(output), *ARGUMENTS)

    assert result.returncode == 3
    report = json.loads(result.stdout)
    refusal = report["refusal"]
    assert refusal["boundary"] == "malformed-content-document"
    assert refusal["stage"] == "artifact-well-formedness"
    assert refusal["artifact_written"] is False
    assert refusal["fact"]["malformed_documents"] == ["EPUB/text/ch001.xhtml"]
    assert "EPUB/text/ch001.xhtml" in refusal["summary"]
    assert balance(report)["payloads"] == []
    assert not output.exists()
    assert written.read_bytes() == original

    comment = write_markdown(tmp_path / "comment-0.md", source(raw="<!-- a -- b -->"))
    again = run_cli(
        "prepare", str(comment), "--output", str(tmp_path / "comment-0.epub"), *ARGUMENTS
    )
    assert json.loads(again.stdout)["refusal"]["boundary"] == "malformed-content-document"


def _chapter(artifact: Path) -> str:
    import zipfile

    with zipfile.ZipFile(artifact) as archive:
        return archive.read("EPUB/text/ch001.xhtml").decode("utf-8")

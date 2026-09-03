"""A callout's title arrives as bare nested divs, and this is what gives its standing back.

A reader opened `Advice-to-Young-People` on a real X4 and reported the callouts as the book's only
problem. Twelve titles were bordered, tinted and bold on the page but appeared as
ordinary body text on the panel: every bit of the prominence was CSS, and the book does not carry
the stylesheet.

The markup Galley sees is not the page's own. jxnl.co is MkDocs Material and writes
`<p class="admonition-title">`, which Pandoc would have carried through as a paragraph. The pinned
extractor rewrites it into bare `<div>`s -- twelve callouts out, zero admonitions -- and a bare
`Div` is rendered by an EPUB writer as nothing at all. So `callout` is the extractor's own
normalised vocabulary rather than any publishing tool's, and matching it reads the same pinned
contract Galley already reads `content` and `title` from.

These build the AST the way the real route does: the pinned Pandoc's HTML reader over the exact
markup the extractor emits, submitted through the public repaired-document interface.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

from tests.markdown_fixtures import write_markdown
from tests.prepared_epub import content_text, element_texts, navigation_entries
from tests.public_cli import prepare
from tests.repair_fixtures import RepairInputs, inspected, repaired_document

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
PROSE = "Ordinary prose, long enough that this reads as a document rather than as a fragment."
REACH = "How to Reach Out"
SURVIVAL = "Survival"
BODY = "Do not send me anything longer than you would send to a crush."


def callout(title_markup: str, body: str = BODY) -> str:
    """One callout exactly as the pinned extractor writes it, around the title markup given."""

    return f'<div class="callout" data-callout="note">{title_markup}<p>{body}</p></div>'


def recognised(title: str) -> str:
    """The nesting this transform recognises: a title div wrapping an inner div wrapping a line."""

    return f'<div class="callout-title"><div class="callout-title-inner">{title}</div></div>'


def html_ast(path: Path, markup: str) -> Any:
    """Parse the extractor's markup with the same pinned Pandoc, independently of Galley."""

    _ = path.write_text(f"<h1>A Callout Book</h1><p>{PROSE}</p>{markup}\n", encoding="utf-8")
    completed = subprocess.run(
        ["pandoc", "--from", "html", "--to", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def callout_inputs(tmp_path: Path, markup: str, lines: list[str]) -> tuple[Path, RepairInputs]:
    """Inspect a source carrying the same words, then prepare the callout AST as a repair.

    The Markdown source exists to produce a real inspection and a real Preservation Baseline; the
    words in it are the words the callout markup carries, so the baseline holds this book to
    exactly what the divs say.
    """

    words = "\n\n".join(lines)
    source = write_markdown(
        tmp_path / "callout-0.md",
        f"---\ntitle: A Callout Book\n---\n\n# A Callout Book\n\n{PROSE}\n\n{words}\n",
    )
    evidence = inspected(tmp_path / "callout-0.galley", str(source))
    canonical = repaired_document(
        evidence,
        tmp_path / "callout-0.json",
        html_ast(tmp_path / "callout-0.html", markup),
    )
    repair = RepairInputs(
        evidence / "report.json", canonical, evidence / "preservation-baseline.txt"
    )
    return source, repair


def emphasis(report: Any) -> Any:
    return next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "callout-title-emphasis"
    )


def test_a_recognised_callout_title_becomes_one_emphasised_paragraph(tmp_path: Path) -> None:
    markup = callout(recognised(REACH)) + callout(recognised(SURVIVAL), "Keep going anyway.")
    lines = [REACH, BODY, SURVIVAL, "Keep going anyway."]

    source, repair = callout_inputs(tmp_path, markup, lines)
    journey = prepare(tmp_path, source, *repair.options, expected_exit=None)
    (artifact, report) = journey.output, journey.report

    assert report["outcome"] == "completed"
    assert emphasis(report)["fired"] is True
    assert emphasis(report)["emphasised"]["value"] == 2
    assert emphasis(report)["titles"] == [REACH, SURVIVAL]
    assert element_texts(artifact, "strong") == [REACH, SURVIVAL]


def test_no_title_becomes_a_heading_because_headings_drive_pagination(tmp_path: Path) -> None:
    """`nav-membership-drives-pagination` is a device-test claim at firmware 1.4.1: page breaks
    follow navigation membership rather than heading level. Twelve callout titles promoted to
    headings would put twelve page breaks into one book and change its pagination. Emphasis
    restores the title's standing without touching navigation at all, and this test is what stops
    a later change quietly promoting them.
    """

    markup = callout(recognised(REACH))

    source, repair = callout_inputs(tmp_path, markup, [REACH, BODY])
    journey = prepare(tmp_path, source, *repair.options, expected_exit=None)
    (artifact, report) = journey.output, journey.report

    assert emphasis(report)["fired"] is True
    for tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        assert REACH not in element_texts(artifact, tag)
    assert navigation_entries(artifact) == ["A Callout Book"]


def test_no_title_becomes_a_blockquote_because_real_quotations_already_are(tmp_path: Path) -> None:
    """The indented-block idea was rejected because actual quotations in the document are already
    blockquotes and render correctly. Giving callouts the same
    treatment would make two different things look identical.
    """

    markup = callout(recognised(REACH))

    source, repair = callout_inputs(tmp_path, markup, [REACH, BODY])
    journey = prepare(tmp_path, source, *repair.options, expected_exit=None)
    (artifact, report) = journey.output, journey.report

    assert emphasis(report)["fired"] is True
    assert element_texts(artifact, "blockquote") == []


def test_the_words_survive_the_reblocking_untouched(tmp_path: Path) -> None:
    """Nothing is added and nothing removed, only re-blocked. Confirmed rather than assumed."""

    markup = callout(recognised(REACH))

    source, repair = callout_inputs(tmp_path, markup, [REACH, BODY])
    journey = prepare(tmp_path, source, *repair.options, expected_exit=None)
    (artifact, report) = journey.output, journey.report
    preservation = report["artifact"]["text_preservation"]

    assert preservation["claimed"] is True
    assert preservation["tokens"]["unexpected_missing"] == []
    assert content_text(artifact).count(REACH) == 1


def test_a_title_holding_more_than_one_block_is_left_alone(tmp_path: Path) -> None:
    inner = f'<div class="callout-title-inner">{REACH}</div><p>{SURVIVAL}</p>'
    markup = callout(f'<div class="callout-title">{inner}</div>')

    source, repair = callout_inputs(tmp_path, markup, [REACH, SURVIVAL, BODY])
    journey = prepare(tmp_path, source, *repair.options, expected_exit=None)
    (artifact, report) = journey.output, journey.report

    assert emphasis(report)["fired"] is False
    assert element_texts(artifact, "strong") == []


def test_an_inner_title_with_no_wrapper_is_left_alone(tmp_path: Path) -> None:
    """`callout-title-inner` standing on its own is not the shape this transform has seen."""

    markup = callout(f'<div class="callout-title-inner">{REACH}</div>')

    source, repair = callout_inputs(tmp_path, markup, [REACH, BODY])
    journey = prepare(tmp_path, source, *repair.options, expected_exit=None)
    (artifact, report) = journey.output, journey.report

    assert emphasis(report)["fired"] is False
    assert element_texts(artifact, "strong") == []


def test_an_empty_title_is_left_alone(tmp_path: Path) -> None:
    markup = callout('<div class="callout-title"><div class="callout-title-inner"></div></div>')

    source, repair = callout_inputs(tmp_path, markup, [BODY])
    journey = prepare(tmp_path, source, *repair.options, expected_exit=None)
    (artifact, report) = journey.output, journey.report

    assert emphasis(report)["fired"] is False
    assert element_texts(artifact, "strong") == []

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from tests.epub_fixtures import CHAPTER_PATH, chapter, default_entries, replace, write_epub
from tests.public_cli import NO_EPUBCHECK, run_public_cli

# The fixture's navigation document contributes one recorded cross-reference of its own,
# so chapter expectations below carry it explicitly rather than hiding it.
NAVIGATION_RECORDED = 1
NAVIGATION_HREF_BYTES = len(b"chapter-1.xhtml")


def audited_links(tmp_path: Path, body: str, name: str = "links.epub") -> dict[str, Any]:
    """Audit a fixture whose chapter carries the supplied body and return its link facts."""

    entries = replace(default_entries(), CHAPTER_PATH, chapter(body))
    book = write_epub(tmp_path / name, entries)
    before = sha256(book.read_bytes()).hexdigest()
    results = run_public_cli(
        "audit", str(book), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    assert sha256(book.read_bytes()).hexdigest() == before
    reports: list[dict[str, Any]] = [json.loads(result.stdout) for result in results]
    assert reports[0]["artifact"] == reports[1]["artifact"]
    return reports[0]["artifact"]["links"]


def test_a_link_is_recorded_only_with_an_in_book_href_and_visible_text(tmp_path: Path) -> None:
    body = (
        '<p id="start">'
        '<a href="#start">visible</a>'
        '<a href="#start"></a>'
        '<a href="https://example.com/">external</a>'
        '<a href="mailto:reader@example.com">mail</a>'
        "</p>"
    )

    links = audited_links(tmp_path, body)

    assert links["total"]["value"] == 4 + NAVIGATION_RECORDED
    assert links["recorded"]["value"] == 1 + NAVIGATION_RECORDED
    assert links["maximum_recorded_per_block"]["value"] == 1


def test_every_link_kind_is_counted(tmp_path: Path) -> None:
    body = (
        '<p id="start">'
        '<a href="https://example.com/">web</a>'
        '<a href="#start">cross</a>'
        '<a href="#absent">dead file fragment</a>'
        '<a href="images/absent.xhtml">dead file</a>'
        '<a epub:type="noteref" href="#start">note</a>'
        '<a epub:type="backlink" href="#start">back</a>'
        "</p>"
    )

    links = audited_links(tmp_path, body)

    assert {kind: value["value"] for kind, value in links["kinds"].items()} == {
        "cross-reference": 2,
        "dead-link": 2,
        "footnote-back-link": 1,
        "footnote-reference": 1,
        "web-link": 1,
    }
    assert [entry["text"] for entry in links["dead"]] == ["dead file fragment", "dead file"]


def test_an_unresolved_footnote_reference_is_reported_as_a_target_fact(tmp_path: Path) -> None:
    body = (
        '<p id="start">'
        '<a epub:type="noteref" href="#start">resolves</a>'
        '<a epub:type="noteref" href="#gone">misdirects</a>'
        "</p>"
    )

    links = audited_links(tmp_path, body)

    assert links["footnote_references"]["total"]["value"] == 2
    assert links["footnote_references"]["unresolved"]["value"] == 1
    assert links["kinds"]["dead-link"]["value"] == 1


def test_recorded_links_are_counted_per_innermost_reading_block(tmp_path: Path) -> None:
    anchors = "".join(f'<a href="#start">{index}</a>' for index in range(5))
    body = f'<p id="start">{anchors}</p><p>{anchors}{anchors}</p>'

    links = audited_links(tmp_path, body)

    assert links["recorded"]["value"] == 15 + NAVIGATION_RECORDED
    assert links["maximum_recorded_per_block"]["value"] == 10


def test_a_nested_block_is_measured_separately_from_its_parent(tmp_path: Path) -> None:
    outer = "".join(f'<a href="#start">{index}</a>' for index in range(3))
    inner = "".join(f'<a href="#start">{index}</a>' for index in range(9))
    body = f'<ul id="start"><li>{outer}<blockquote><p>{inner}</p></blockquote></li></ul>'

    links = audited_links(tmp_path, body)

    assert links["recorded"]["value"] == 12 + NAVIGATION_RECORDED
    assert links["maximum_recorded_per_block"]["value"] == 9


def test_inline_children_of_a_division_form_one_implicit_block(tmp_path: Path) -> None:
    anchors = "".join(f'<a href="#start">{index}</a>' for index in range(4))
    body = f'<div id="start"><span>{anchors}</span><p>{anchors}</p><span>{anchors}</span></div>'

    links = audited_links(tmp_path, body)

    assert links["recorded"]["value"] == 12 + NAVIGATION_RECORDED
    assert links["maximum_recorded_per_block"]["value"] == 4


def test_href_length_is_measured_in_decoded_utf8_bytes(tmp_path: Path) -> None:
    target = "caf&#233;-section-with-a-deliberately-long-identifier"
    decoded = "#café-section-with-a-deliberately-long-identifier"
    body = f'<p id="start"><a href="#{target}">accented</a><a href="#start">short</a></p>'

    links = audited_links(tmp_path, body)

    assert len(decoded.encode()) > NAVIGATION_HREF_BYTES
    assert links["maximum_recorded_href_bytes"]["value"] == len(decoded.encode())


def test_anchors_are_counted_for_each_content_document(tmp_path: Path) -> None:
    body = (
        '<p id="one">a</p><p id="two">b</p><section id="three"><span id="four">c</span></section>'
    )

    links = audited_links(tmp_path, body)

    counts = {entry["path"]: entry["count"]["value"] for entry in links["anchors"]["documents"]}
    assert counts["EPUB/chapter-1.xhtml"] == 4
    assert links["anchors"]["maximum_per_document"]["value"] == 4


def test_only_the_profile_s_excluded_schemes_escape_the_recorded_count(tmp_path: Path) -> None:
    body = (
        '<p id="start">'
        '<a href="https://example.com/">https</a>'
        '<a href="tel:+15550100">tel</a>'
        '<a href="javascript:void(0)">script</a>'
        '<a href="data:text/plain,hello">data</a>'
        '<a href="//example.com/protocol-relative">protocol relative</a>'
        "</p>"
    )

    links = audited_links(tmp_path, body)

    assert links["kinds"]["web-link"]["value"] == 3
    assert links["recorded"]["value"] == 2 + NAVIGATION_RECORDED
    assert links["maximum_recorded_per_block"]["value"] == 2


def test_anchors_are_counted_for_spine_chapters_only(tmp_path: Path) -> None:
    body = '<p id="one">a</p><p id="two">b</p><p id="three">c</p>'

    links = audited_links(tmp_path, body)

    paths = [entry["path"] for entry in links["anchors"]["documents"]]
    assert paths == ["EPUB/chapter-1.xhtml"]
    assert links["anchors"]["maximum_per_document"]["value"] == 3

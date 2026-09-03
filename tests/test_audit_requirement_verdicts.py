import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from tests.epub_fixtures import (
    CHAPTER_PATH,
    NAVIGATION_PATH,
    chapter,
    default_entries,
    replace,
    without,
    write_epub,
)
from tests.public_cli import NO_EPUBCHECK, run_cli

MALFORMED_XML = b'<?xml version="1.0" encoding="UTF-8"?>\n<html><body><p>unclosed\n'
LINKLESS_NAVIGATION = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Audit Fixture</title></head>
  <body><nav epub:type="toc" id="toc"><ol><li><span>Chapter One</span></li></ol></nav></body>
</html>
"""


def audited(book: Path) -> dict[str, Any]:
    before = sha256(book.read_bytes()).hexdigest()
    result = run_cli(
        "audit", str(book), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert sha256(book.read_bytes()).hexdigest() == before
    reports: dict[str, Any] = json.loads(result.stdout)
    return reports


def verdicts(report: dict[str, Any]) -> dict[str, str]:
    return {
        str(entry["requirement_id"]): str(entry["verdict"]) for entry in report["compatibility"]
    }


def requirement(report: dict[str, Any], identifier: str) -> dict[str, Any]:
    return next(entry for entry in report["compatibility"] if entry["requirement_id"] == identifier)


def linked(tmp_path: Path, body: str, name: str) -> dict[str, Any]:
    entries = replace(default_entries(), CHAPTER_PATH, chapter(body))
    return audited(write_epub(tmp_path / name, entries))


def test_a_conforming_artifact_receives_true_navigation_verdicts(tmp_path: Path) -> None:
    report = audited(write_epub(tmp_path / "true.epub"))

    assert verdicts(report)["recorded-links-per-block"] == "true"
    assert verdicts(report)["footnote-href-length"] == "true"
    assert verdicts(report)["anchors-per-chapter"] == "true"


def test_the_recorded_link_ceiling_is_evaluated_at_its_exact_boundary(tmp_path: Path) -> None:
    def block(count: int) -> str:
        anchors = "".join(f'<a href="#start">{index}</a>' for index in range(count))
        return f'<p id="start">{anchors}</p>'

    at_limit = linked(tmp_path, block(128), "at-limit.epub")
    over_limit = linked(tmp_path, block(129), "over-limit.epub")

    assert verdicts(at_limit)["recorded-links-per-block"] == "true"
    assert verdicts(over_limit)["recorded-links-per-block"] == "false"
    assert requirement(over_limit, "recorded-links-per-block")["measurement"]["value"] == 129


def test_the_footnote_href_ceiling_is_evaluated_at_its_exact_boundary(tmp_path: Path) -> None:
    def link(length: int) -> str:
        return f'<p id="start"><a href="#{"a" * (length - 1)}">note</a></p>'

    at_limit = linked(tmp_path, link(96), "href-96.epub")
    over_limit = linked(tmp_path, link(97), "href-97.epub")

    assert verdicts(at_limit)["footnote-href-length"] == "true"
    assert verdicts(over_limit)["footnote-href-length"] == "false"
    assert requirement(over_limit, "footnote-href-length")["measurement"]["value"] == 97


def test_an_artifact_without_recorded_links_is_not_applicable(tmp_path: Path) -> None:
    entries = replace(default_entries(), CHAPTER_PATH, chapter("<p>No links at all.</p>"))
    entries = replace(entries, NAVIGATION_PATH, LINKLESS_NAVIGATION)
    report = audited(write_epub(tmp_path / "linkless.epub", entries))

    for identifier in ("recorded-links-per-block", "footnote-href-length"):
        entry = requirement(report, identifier)
        assert entry["verdict"] == "not_applicable"
        assert entry["applicability"] is False
        assert entry["measurement"] is None


def test_an_unreadable_content_document_leaves_navigation_verdicts_unknown(
    tmp_path: Path,
) -> None:
    entries = replace(default_entries(), CHAPTER_PATH, MALFORMED_XML)
    report = audited(write_epub(tmp_path / "unknown.epub", entries))

    entry = requirement(report, "recorded-links-per-block")
    assert entry["verdict"] == "unknown"
    assert entry["applicability"] is True
    assert report["artifact"]["links"]["complete"] is False


def test_a_permanently_unevaluable_requirement_says_so(tmp_path: Path) -> None:
    report = audited(write_epub(tmp_path / "unevaluable.epub"))

    entry = requirement(report, "footnotes-per-screen")
    assert entry["verdict"] == "unevaluable"
    assert entry["measurement"] is None
    assert entry["observed_limit"] == {
        "basis": "reported",
        "unit": "recorded links per rendered screen",
        "value": 16,
    }


def test_a_false_crash_class_requirement_still_completes_the_audit(tmp_path: Path) -> None:
    anchors = "".join(f'<a href="#start">{index}</a>' for index in range(129))
    entries = replace(default_entries(), CHAPTER_PATH, chapter(f'<p id="start">{anchors}</p>'))
    book = write_epub(tmp_path / "crash-class.epub", entries)
    before = sha256(book.read_bytes()).hexdigest()

    result = run_cli(
        "audit", str(book), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert sha256(book.read_bytes()).hexdigest() == before
    report = json.loads(result.stdout)
    entry = requirement(report, "recorded-links-per-block")
    assert report["outcome"] == "completed"
    assert report["refusal"] is None
    assert (entry["verdict"], entry["failure_mode"], entry["authority"]) == (
        "false",
        "crash",
        "refuse",
    )


def test_failure_mode_authority_and_limits_travel_with_every_result(tmp_path: Path) -> None:
    report = audited(write_epub(tmp_path / "profile-fields.epub"))

    assert verdicts(report) == {
        "anchors-per-chapter": "true",
        "footnote-href-length": "true",
        "footnotes-per-screen": "unevaluable",
        "image-media-type": "true",
        "jpeg-decoding": "not_applicable",
        "png-decoding": "true",
        "recorded-links-per-block": "true",
    }
    entry = requirement(report, "recorded-links-per-block")
    assert entry["failure_mode"] == "crash"
    assert entry["authority"] == "refuse"
    assert entry["profile_version"] == "0.4.0"
    assert entry["enforced_limit"] == {
        "basis": "reported",
        "unit": "recorded links",
        "value": 128,
    }
    assert entry["observed_limit"] == {
        "basis": "reported",
        "unit": "recorded links",
        "value": 256,
    }


def test_the_navigation_observation_reports_its_primitive_without_judging(tmp_path: Path) -> None:
    body = '<p id="start"><a href="#start">one</a><a epub:type="noteref" href="#start">2</a></p>'
    report = linked(tmp_path, body, "dilution.epub")

    entry = next(
        observation
        for observation in report["observations"]
        if observation["name"] == "link-footnote-dilution"
    )
    assert entry["evidence"] == "flaggable"
    assert entry["consequence"] == "navigation"
    assert entry["fired"] is None
    assert entry["applicability"] is True
    assert entry["measurement"]["value"] == 1


def test_a_navigation_only_artifact_keeps_the_subject_unchanged(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "unchanged.epub", without(default_entries(), CHAPTER_PATH))
    original = book.read_bytes()

    report = audited(book)

    assert book.read_bytes() == original
    assert report["outcome"] == "completed"


def test_an_unresolved_footnote_target_fires_the_computable_observation(tmp_path: Path) -> None:
    body = (
        '<p id="start">'
        '<a epub:type="noteref" href="#start">resolves</a>'
        '<a epub:type="noteref" href="#gone">misdirects</a>'
        "</p>"
    )
    report = linked(tmp_path, body, "targets.epub")

    entry = next(
        candidate
        for candidate in report["observations"]
        if candidate["name"] == "footnote-target-reliability"
    )
    assert entry["evidence"] == "computable"
    assert entry["consequence"] == "navigation"
    assert entry["applicability"] is True
    assert entry["fired"] is True
    assert entry["measurement"]["value"] == 1
    assert entry["locations"] == [CHAPTER_PATH]


def test_resolved_footnote_targets_leave_the_observation_unfired(tmp_path: Path) -> None:
    body = '<p id="start"><a epub:type="noteref" href="#start">resolves</a></p>'
    report = linked(tmp_path, body, "resolved.epub")

    entry = next(
        candidate
        for candidate in report["observations"]
        if candidate["name"] == "footnote-target-reliability"
    )
    assert entry["applicability"] is True
    assert entry["fired"] is False

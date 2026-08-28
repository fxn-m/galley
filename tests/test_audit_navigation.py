from pathlib import Path

from tests.epub_fixtures import (
    NAVIGATION_PATH,
    PACKAGE_PATH,
    default_entries,
    plus,
    replace,
    without,
    write_epub,
)
from tests.test_audit_package_facts import (
    CHAPTER_ITEM,
    FIGURE_ITEM,
    MALFORMED_XML,
    NCX_XML,
    audit_artifact,
    package,
    problem_kinds,
)


def test_a_package_without_navigation_is_an_artifact_fact(tmp_path: Path) -> None:
    entries = replace(default_entries(), PACKAGE_PATH, package(f"{CHAPTER_ITEM}{FIGURE_ITEM}"))
    entries = without(entries, NAVIGATION_PATH)
    book = write_epub(tmp_path / "no-navigation.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["navigation"] == {
        "entry_count": {"basis": "measured", "unit": "entries", "value": 0},
        "kind": None,
        "malformed_xml": False,
        "path": None,
        "present": False,
    }
    assert problem_kinds(artifact) == ["missing-navigation"]


def test_an_ncx_navigation_document_is_recognised(tmp_path: Path) -> None:
    ncx_item = '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    entries = replace(
        default_entries(),
        PACKAGE_PATH,
        package(
            f"{CHAPTER_ITEM}{FIGURE_ITEM}{ncx_item}",
            spine_attributes=' toc="ncx"',
        ),
    )
    entries = without(entries, NAVIGATION_PATH)
    entries = plus(entries, ("EPUB/toc.ncx", NCX_XML.encode("utf-8")))
    book = write_epub(tmp_path / "ncx.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["navigation"] == {
        "entry_count": {"basis": "measured", "unit": "entries", "value": 1},
        "kind": "ncx",
        "malformed_xml": False,
        "path": "EPUB/toc.ncx",
        "present": True,
    }
    assert artifact["spine"]["toc"] == "ncx"
    assert problem_kinds(artifact) == []


def test_malformed_navigation_xml_is_reported_as_malformed_not_missing(tmp_path: Path) -> None:
    entries = replace(default_entries(), NAVIGATION_PATH, MALFORMED_XML)
    book = write_epub(tmp_path / "bad-navigation.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["navigation"] == {
        "entry_count": {"basis": "measured", "unit": "entries", "value": 0},
        "kind": "epub3-nav",
        "malformed_xml": True,
        "path": NAVIGATION_PATH,
        "present": True,
    }
    assert problem_kinds(artifact) == ["malformed-xml"]
    assert artifact["problems"][0]["location"] == NAVIGATION_PATH

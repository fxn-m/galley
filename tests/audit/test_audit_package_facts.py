import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from tests.support.epub_fixtures import (
    CHAPTER_PATH,
    CONTAINER_PATH,
    FIGURE_PATH,
    PACKAGE_PATH,
    default_entries,
    plus,
    replace,
    without,
    write_epub,
)
from tests.support.public_cli import NO_EPUBCHECK, run_cli

MALFORMED_XML = b'<?xml version="1.0" encoding="UTF-8"?>\n<html><body><p>unclosed\n'

PACKAGE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:uuid:galley-audit-fixture</dc:identifier>
    <dc:title>Audit Fixture</dc:title>
  </metadata>
  <manifest>{manifest}</manifest>
  <spine{spine_attributes}>{spine}</spine>
</package>
"""
NAV_ITEM = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
CHAPTER_ITEM = '<item id="chapter-1" href="chapter-1.xhtml" media-type="application/xhtml+xml"/>'
FIGURE_ITEM = '<item id="figure" href="images/figure.png" media-type="image/png"/>'
CHAPTER_ITEMREF = '<itemref idref="chapter-1"/>'

NCX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="chapter-1"><navLabel><text>One</text></navLabel>
      <content src="chapter-1.xhtml"/></navPoint>
  </navMap>
</ncx>
"""


def package(manifest: str, spine: str = CHAPTER_ITEMREF, spine_attributes: str = "") -> bytes:
    return PACKAGE_TEMPLATE.format(
        manifest=manifest, spine=spine, spine_attributes=spine_attributes
    ).encode("utf-8")


def audit_artifact(book: Path) -> dict[str, Any]:
    """Audit one EPUB through the installed command and return its artifact facts."""

    before = sha256(book.read_bytes()).hexdigest()
    result = run_cli(
        "audit", str(book), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert sha256(book.read_bytes()).hexdigest() == before
    artifacts: dict[str, Any] = json.loads(result.stdout)["artifact"]

    return artifacts


def problem_kinds(artifact: dict[str, Any]) -> list[str]:
    return [str(problem["kind"]) for problem in artifact["problems"]]


def test_a_missing_container_is_an_artifact_fact(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "no-container.epub", without(default_entries(), CONTAINER_PATH))

    artifact = audit_artifact(book)

    assert artifact["container"] == {
        "malformed_xml": False,
        "package_path": None,
        "present": False,
        "rootfiles": [],
    }
    assert artifact["package"]["present"] is False
    assert problem_kinds(artifact) == ["missing-container"]


def test_malformed_container_xml_is_an_artifact_fact(tmp_path: Path) -> None:
    entries = replace(default_entries(), CONTAINER_PATH, MALFORMED_XML)
    book = write_epub(tmp_path / "bad-container.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["container"]["present"] is True
    assert artifact["container"]["malformed_xml"] is True
    assert artifact["container"]["package_path"] is None
    assert problem_kinds(artifact) == ["malformed-xml"]


def test_a_missing_package_document_is_an_artifact_fact(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "no-package.epub", without(default_entries(), PACKAGE_PATH))

    artifact = audit_artifact(book)

    assert artifact["container"]["package_path"] == PACKAGE_PATH
    assert artifact["package"] == {
        "cover_id": None,
        "malformed_xml": False,
        "path": PACKAGE_PATH,
        "present": False,
        "title": None,
        "unique_identifier": None,
        "version": None,
    }
    assert artifact["manifest"]["item_count"]["value"] == 0
    assert problem_kinds(artifact) == ["missing-package-document"]


def test_malformed_package_xml_is_an_artifact_fact(tmp_path: Path) -> None:
    entries = replace(default_entries(), PACKAGE_PATH, MALFORMED_XML)
    book = write_epub(tmp_path / "bad-package.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["package"]["present"] is True
    assert artifact["package"]["malformed_xml"] is True
    assert artifact["manifest"]["items"] == []
    assert problem_kinds(artifact) == ["malformed-xml"]


def test_malformed_content_document_xml_is_an_artifact_fact(tmp_path: Path) -> None:
    entries = replace(default_entries(), CHAPTER_PATH, MALFORMED_XML)
    book = write_epub(tmp_path / "bad-chapter.epub", entries)

    artifact = audit_artifact(book)

    documents = artifact["content_documents"]
    assert [document["malformed_xml"] for document in documents] == [True, False]
    assert problem_kinds(artifact) == ["malformed-xml"]
    assert artifact["problems"][0]["location"] == CHAPTER_PATH


def test_duplicate_archive_members_are_an_artifact_fact(tmp_path: Path) -> None:
    entries = plus(default_entries(), (CHAPTER_PATH, b"<html/>"))
    with pytest.warns(UserWarning, match="Duplicate name"):
        book = write_epub(tmp_path / "duplicated.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["archive"]["duplicate_members"] == [CHAPTER_PATH]
    assert artifact["archive"]["member_count"]["value"] == 8
    assert "duplicate-archive-member" in problem_kinds(artifact)


def test_unsafe_archive_paths_are_an_artifact_fact(tmp_path: Path) -> None:
    entries = plus(default_entries(), ("../escape.xhtml", b"<html/>"), ("/absolute.xhtml", b"<i/>"))
    book = write_epub(tmp_path / "unsafe.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["archive"]["unsafe_members"] == ["../escape.xhtml", "/absolute.xhtml"]
    assert problem_kinds(artifact) == ["unsafe-archive-path", "unsafe-archive-path"]


def test_a_manifest_item_missing_from_the_archive_is_a_broken_reference(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "missing-resource.epub", without(default_entries(), FIGURE_PATH))

    artifact = audit_artifact(book)

    items = {item["id"]: item for item in artifact["manifest"]["items"]}
    assert items["figure"]["present"] is False
    assert artifact["references"]["broken"] == [
        {"from": PACKAGE_PATH, "kind": "manifest", "target": FIGURE_PATH},
        {"from": CHAPTER_PATH, "kind": "content-document", "target": FIGURE_PATH},
    ]
    assert artifact["references"]["broken_count"]["value"] == 2
    assert problem_kinds(artifact) == ["broken-reference", "broken-reference"]


def test_an_unresolved_spine_idref_is_a_broken_reference(tmp_path: Path) -> None:
    entries = replace(
        default_entries(),
        PACKAGE_PATH,
        package(f"{NAV_ITEM}{CHAPTER_ITEM}{FIGURE_ITEM}", '<itemref idref="absent"/>'),
    )
    book = write_epub(tmp_path / "unresolved-spine.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["spine"]["items"] == [
        {"idref": "absent", "linear": True, "path": None, "resolved": False}
    ]
    assert artifact["references"]["broken"] == [
        {"from": PACKAGE_PATH, "kind": "spine", "target": "absent"}
    ]


def test_a_broken_content_document_reference_is_reported(tmp_path: Path) -> None:
    chapter = b'<?xml version="1.0" encoding="UTF-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">\n<body><p><img src="images/absent.png" alt="Gone"/></p></body></html>\n'
    entries = replace(default_entries(), CHAPTER_PATH, chapter)
    book = write_epub(tmp_path / "broken-reference.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["references"]["broken"] == [
        {"from": CHAPTER_PATH, "kind": "content-document", "target": "EPUB/images/absent.png"}
    ]
    assert artifact["references"]["document_count"]["value"] == 2
    assert problem_kinds(artifact) == ["broken-reference"]


def test_duplicate_manifest_ids_are_an_artifact_fact(tmp_path: Path) -> None:
    entries = replace(
        default_entries(),
        PACKAGE_PATH,
        package(f"{NAV_ITEM}{CHAPTER_ITEM}{CHAPTER_ITEM}{FIGURE_ITEM}"),
    )
    book = write_epub(tmp_path / "duplicate-ids.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["manifest"]["duplicate_ids"] == ["chapter-1"]
    assert "duplicate-manifest-id" in problem_kinds(artifact)


def test_a_declared_cover_image_is_an_artifact_fact(tmp_path: Path) -> None:
    cover_item = '<item id="figure" href="images/figure.png" media-type="image/png" properties="cover-image"/>'
    nav_item = (
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    )
    entries = replace(
        default_entries(), PACKAGE_PATH, package(f"{nav_item}{CHAPTER_ITEM}{cover_item}")
    )
    book = write_epub(tmp_path / "cover.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["package"]["cover_id"] == "figure"
    assert problem_kinds(artifact) == []


def test_a_legacy_cover_metadata_reference_is_an_artifact_fact(tmp_path: Path) -> None:
    legacy = PACKAGE_TEMPLATE.replace(
        "</metadata>", '<meta name="cover" content="figure"/></metadata>'
    )
    nav_item = (
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    )
    opf = legacy.format(
        manifest=f"{nav_item}{CHAPTER_ITEM}{FIGURE_ITEM}",
        spine=CHAPTER_ITEMREF,
        spine_attributes="",
    ).encode("utf-8")
    book = write_epub(tmp_path / "legacy-cover.epub", replace(default_entries(), PACKAGE_PATH, opf))

    artifact = audit_artifact(book)

    assert artifact["package"]["cover_id"] == "figure"


def test_a_duplicate_manifest_id_never_repoints_a_spine_item(tmp_path: Path) -> None:
    shadow = '<item id="chapter-1" href="images/figure.png" media-type="image/png"/>'
    entries = replace(
        default_entries(), PACKAGE_PATH, package(f"{CHAPTER_ITEM}{shadow}{FIGURE_ITEM}")
    )
    book = write_epub(tmp_path / "shadowed-id.epub", entries)

    artifact = audit_artifact(book)

    assert artifact["manifest"]["duplicate_ids"] == ["chapter-1"]
    assert artifact["spine"]["items"][0]["path"] == "EPUB/chapter-1.xhtml"

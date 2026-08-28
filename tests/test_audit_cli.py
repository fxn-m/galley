import json
from hashlib import sha256
from pathlib import Path

from tests.epub_fixtures import PACKAGE_PATH, default_entries, without, write_epub
from tests.public_cli import NO_EPUBCHECK, run_public_cli
from tests.report_fixtures import X4_PROFILE_FACTS


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_audit_reports_package_structure_without_touching_the_subject(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    before = digest(book)

    results = run_public_cli(
        "audit", str(book), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    assert digest(book) == before
    for result in results:
        report = json.loads(result.stdout)
        assert report["galley"]["command"] == "audit"
        assert report["galley"]["report_schema"] == "galley/report/1"
        assert (report["outcome"], report["refusal"]) == ("completed", None)
        assert report["profile"] == X4_PROFILE_FACTS
        artifact = report["artifact"]
        assert artifact["path"] == str(book.resolve())
        assert artifact["sha256"] == before
        assert artifact["byte_size"] == {
            "basis": "measured",
            "unit": "bytes",
            "value": book.stat().st_size,
        }
        assert artifact["container"] == {
            "malformed_xml": False,
            "package_path": PACKAGE_PATH,
            "present": True,
            "rootfiles": [PACKAGE_PATH],
        }
        assert artifact["package"] == {
            "cover_id": None,
            "malformed_xml": False,
            "path": PACKAGE_PATH,
            "present": True,
            "title": "Audit Fixture",
            "unique_identifier": "urn:uuid:8f1d6b0e-6d2a-4d51-9a7e-2c4b8d3f5a61",
            "version": "3.0",
        }
        assert artifact["navigation"] == {
            "entry_count": {"basis": "measured", "unit": "entries", "value": 1},
            "kind": "epub3-nav",
            "malformed_xml": False,
            "path": "EPUB/nav.xhtml",
            "present": True,
        }
        assert artifact["problems"] == []


def test_audit_resolves_manifest_spine_resources_and_the_reference_graph(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")

    results = run_public_cli(
        "audit", str(book), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    for result in results:
        artifact = json.loads(result.stdout)["artifact"]
        manifest = artifact["manifest"]
        assert manifest["item_count"] == {"basis": "measured", "unit": "items", "value": 4}
        assert manifest["duplicate_ids"] == []
        assert manifest["items"][0] == {
            "declared_media_type": "application/xhtml+xml",
            "href": "chapter-1.xhtml",
            "id": "chapter-1",
            "path": "EPUB/chapter-1.xhtml",
            "present": True,
            "properties": [],
        }
        assert [item["id"] for item in manifest["items"]] == ["chapter-1", "figure", "nav", "style"]
        assert artifact["spine"] == {
            "item_count": {"basis": "measured", "unit": "items", "value": 1},
            "items": [
                {
                    "idref": "chapter-1",
                    "linear": True,
                    "path": "EPUB/chapter-1.xhtml",
                    "resolved": True,
                }
            ],
            "toc": None,
        }
        assert [document["path"] for document in artifact["content_documents"]] == [
            "EPUB/chapter-1.xhtml",
            "EPUB/nav.xhtml",
        ]
        assert [resource["path"] for resource in artifact["resources"]] == [
            "EPUB/images/figure.png",
            "EPUB/styles/main.css",
        ]
        assert artifact["resources"][0]["declared_media_type"] == "image/png"
        assert artifact["references"] == {
            "broken": [],
            "broken_count": {"basis": "measured", "unit": "references", "value": 0},
            "document_count": {"basis": "measured", "unit": "references", "value": 3},
            "external_count": {"basis": "measured", "unit": "references", "value": 1},
            "same_document_count": {"basis": "measured", "unit": "references", "value": 1},
        }
        assert artifact["archive"] == {
            "duplicate_members": [],
            "member_count": {"basis": "measured", "unit": "members", "value": 7},
            "mimetype": {
                "declared": "application/epub+zip",
                "matches_epub": True,
                "present": True,
            },
            "unreadable_members": [],
            "unsafe_members": [],
        }


def test_audit_leaves_source_and_preparation_stages_honestly_unavailable(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")

    results = run_public_cli(
        "audit", str(book), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    for result in results:
        report = json.loads(result.stdout)
        assert report["source"] is None
        assert report["extraction"] is None
        assert report["canonical_document"] is None
        assert report["preparation"] is None
        assert report["warnings"] == []
        assert report["reading_verdict"] == {"predicted": None, "value": "not_tested"}


def test_human_audit_output_describes_the_same_result(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    before = digest(book)

    results = run_public_cli(
        "audit", str(book), "--profile", "x4-crosspoint", environment=NO_EPUBCHECK
    )

    expected = (
        "audit: completed\n"
        "Profile: x4-crosspoint 0.4.0 (firmware 1.4.1)\n"
        f"Artifact: {book.resolve()}\n"
        f"Bytes: {book.stat().st_size}; sha256 {before}\n"
        f"Package: {PACKAGE_PATH} (EPUB 3.0)\n"
        "Manifest items: 4; spine items: 1; navigation: EPUB/nav.xhtml (epub3-nav)\n"
        "Content documents: 2; resources: 2\n"
        "References: 3; broken: 0\n"
        "Problems: 0\n"
        "Links: 3 total; 2 recorded; max 1 per block; longest href 15 bytes (complete)\n"
        "Images: 1 measured; 0 not device-verified; 0 unresolved references\n"
        "Text Preservation: not claimed (Preservation Baseline unavailable)\n"
        "Conformance: unavailable (epubcheck not-found)\n"
        "Non-requirement: EPUB validity is not a requirement. (package-validity)\n"
        "Compatibility: true 5, false 0, unknown 0, unevaluable 1, not_applicable 1\n"
        "Observations: 6 recorded; 5 applicable; 0 fired; 3 awaiting agent or human judgement\n"
    )
    assert [(result.returncode, result.stdout, result.stderr) for result in results] == [
        (0, expected, ""),
        (0, expected, ""),
    ]
    assert digest(book) == before


def test_human_audit_output_names_every_problem_kind(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "broken.epub", without(default_entries(), PACKAGE_PATH))

    results = run_public_cli(
        "audit", str(book), "--profile", "x4-crosspoint", environment=NO_EPUBCHECK
    )

    for result in results:
        assert result.returncode == 0
        assert "Problems: 1 (missing-package-document)\n" in result.stdout


def test_audit_with_an_unknown_profile_refuses_without_reading_the_subject(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    before = digest(book)

    results = run_public_cli(
        "audit", str(book), "--profile", "missing", "--json", environment=NO_EPUBCHECK
    )

    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    assert digest(book) == before
    for result in results:
        report = json.loads(result.stdout)
        assert report["galley"]["command"] == "audit"
        assert report["refusal"]["boundary"] == "unknown-profile"
        assert report["refusal"]["authority"] == "audit"
        assert report["artifact"] is None


def test_audit_refuses_an_unreadable_subject_and_keeps_the_facts_it_measured(
    tmp_path: Path,
) -> None:
    not_an_archive = tmp_path / "not-an-archive.epub"
    original = b"This file is not a ZIP archive.\n"
    _ = not_an_archive.write_bytes(original)

    results = run_public_cli(
        "audit",
        str(not_an_archive),
        "--profile",
        "x4-crosspoint",
        "--json",
        environment=NO_EPUBCHECK,
    )

    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    assert not_an_archive.read_bytes() == original
    for result in results:
        report = json.loads(result.stdout)
        assert report["outcome"] == "refused"
        assert report["refusal"]["boundary"] == "unreadable-artifact"
        assert report["refusal"]["stage"] == "artifact-acquisition"
        assert report["refusal"]["artifact_written"] is False
        assert report["refusal"]["fact"]["reason"] == "not-a-zip-archive"
        assert report["profile"]["resolved"] is True
        artifact = report["artifact"]
        assert artifact["path"] == str(not_an_archive.resolve())
        assert artifact["sha256"] == sha256(original).hexdigest()
        assert artifact["byte_size"]["value"] == len(original)


def test_audit_refuses_a_missing_subject(tmp_path: Path) -> None:
    missing = tmp_path / "absent.epub"

    results = run_public_cli(
        "audit", str(missing), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    assert not missing.exists()
    for result in results:
        report = json.loads(result.stdout)
        assert report["refusal"]["boundary"] == "unreadable-artifact"
        assert report["refusal"]["fact"]["reason"] == "missing"
        assert report["artifact"] == {"path": str(missing.resolve())}


def test_human_refusal_output_shows_the_facts_measured_before_stopping(tmp_path: Path) -> None:
    not_an_archive = tmp_path / "not-an-archive.epub"
    original = b"This file is not a ZIP archive.\n"
    _ = not_an_archive.write_bytes(original)

    results = run_public_cli(
        "audit", str(not_an_archive), "--profile", "x4-crosspoint", environment=NO_EPUBCHECK
    )

    expected = (
        "audit: refused\n"
        "Profile: x4-crosspoint 0.4.0 (firmware 1.4.1)\n"
        "Boundary: unreadable-artifact\n"
        "Artifact written: no\n"
        f"Bytes: {len(original)}; sha256 {sha256(original).hexdigest()}\n"
        f"cannot read EPUB: {not_an_archive.resolve()}\n"
    )
    assert [(result.returncode, result.stdout, result.stderr) for result in results] == [
        (3, expected, ""),
        (3, expected, ""),
    ]
    assert not_an_archive.read_bytes() == original

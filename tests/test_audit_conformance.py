import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from tests.epub_fixtures import PACKAGE_PATH, default_entries, replace, write_epub
from tests.public_cli import run_public_cli

# Conformance retention is about what the real checker reports, so the whole module
# opts out of the suite's instant EPUBCheck stand-in.
pytestmark = pytest.mark.real_epubcheck

INVALID_PACKAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:uuid:8f1d6b0e-6d2a-4d51-9a7e-2c4b8d3f5a61</dc:identifier>
    <dc:title>Audit Fixture</dc:title>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter-1" href="chapter-1.xhtml" media-type="application/xhtml+xml"/>
    <item id="figure" href="images/figure.png" media-type="image/png"/>
    <item id="style" href="styles/main.css" media-type="text/css"/>
  </manifest>
  <spine>
    <itemref idref="chapter-1"/>
  </spine>
</package>
"""


def audited(book: Path) -> dict[str, Any]:
    """Audit one EPUB through both entry points with the real pinned EPUBCheck."""

    before = sha256(book.read_bytes()).hexdigest()
    results = run_public_cli("audit", str(book), "--profile", "x4-crosspoint", "--json")

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    assert sha256(book.read_bytes()).hexdigest() == before
    reports: list[dict[str, Any]] = [json.loads(result.stdout) for result in results]
    assert reports[0]["artifact"] == reports[1]["artifact"]
    return reports[0]


@pytest.fixture(scope="module")
def valid_report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    book = write_epub(tmp_path_factory.mktemp("valid") / "valid.epub")
    return audited(book)


@pytest.fixture(scope="module")
def invalid_report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    entries = replace(default_entries(), PACKAGE_PATH, INVALID_PACKAGE)
    book = write_epub(tmp_path_factory.mktemp("invalid") / "invalid.epub", entries)
    return audited(book)


def test_audit_records_the_exact_epubcheck_version(valid_report: dict[str, Any]) -> None:
    conformance = valid_report["artifact"]["conformance"]

    assert conformance["checked"] is True
    assert conformance["tool"] == "epubcheck"
    assert conformance["version"] == "5.3.0"
    assert conformance["pinned_version"] == "5.3.0"
    assert conformance["matches_pinned_version"] is True
    assert valid_report["galley"]["dependencies"]["epubcheck"] == "5.3.0"


def test_a_conformant_artifact_reports_no_messages(valid_report: dict[str, Any]) -> None:
    conformance = valid_report["artifact"]["conformance"]

    assert conformance["valid"] is True
    assert conformance["messages"] == []
    assert conformance["counts"] == {
        "error": {"basis": "reported", "value": 0},
        "fatal": {"basis": "reported", "value": 0},
        "usage": {"basis": "reported", "value": 0},
        "warning": {"basis": "reported", "value": 0},
    }
    assert conformance["exit_code"] == {"basis": "measured", "unit": "exit code", "value": 0}
    assert conformance["publication"]["epub_version"] == "3.3"


def test_the_report_retains_the_epubcheck_package_inventory(valid_report: dict[str, Any]) -> None:
    inventory = valid_report["artifact"]["conformance"]["inventory"]

    names = {str(item["file_name"]) for item in inventory}
    assert {"EPUB/package.opf", "EPUB/chapter-1.xhtml", "EPUB/images/figure.png"} <= names
    chapter = next(item for item in inventory if item["file_name"] == "EPUB/chapter-1.xhtml")
    assert chapter["declared_media_type"] == "application/xhtml+xml"
    assert chapter["is_spine_item"] is True
    assert chapter["uncompressed_size"]["basis"] == "reported"
    assert chapter["checksum"]


def test_an_invalid_artifact_completes_audit_and_retains_every_message(
    invalid_report: dict[str, Any],
) -> None:
    conformance = invalid_report["artifact"]["conformance"]

    assert invalid_report["outcome"] == "completed"
    assert invalid_report["refusal"] is None
    assert conformance["valid"] is False
    assert conformance["counts"]["error"]["value"] >= 1
    assert {str(message["id"]) for message in conformance["messages"]} == {"RSC-005"}
    texts = [str(message["message"]) for message in conformance["messages"]]
    assert any("dc:language" in text for text in texts)
    assert any("dcterms:modified" in text for text in texts)
    failure = conformance["messages"][0]
    assert failure["severity"] == "ERROR"
    assert failure["locations"][0]["path"] == PACKAGE_PATH
    assert failure["locations"][0]["line"]["basis"] == "reported"


def test_messages_and_inventory_use_a_stable_order(invalid_report: dict[str, Any]) -> None:
    conformance = invalid_report["artifact"]["conformance"]

    def position(message: dict[str, Any]) -> tuple[str, int, int, str]:
        location = message["locations"][0]
        return (
            str(location["path"]),
            int(location["line"]["value"]),
            int(location["column"]["value"]),
            str(message["id"]),
        )

    positions = [position(message) for message in conformance["messages"]]
    assert positions == sorted(positions)
    names = [str(item["file_name"]) for item in conformance["inventory"]]
    assert names == sorted(names)


def test_conformance_never_becomes_a_compatibility_requirement(
    invalid_report: dict[str, Any],
) -> None:
    requirements = {str(entry["requirement_id"]) for entry in invalid_report["compatibility"]}

    assert invalid_report["artifact"]["conformance"]["valid"] is False
    assert "package-validity" not in requirements
    assert not any("valid" in requirement for requirement in requirements)
    assert invalid_report["artifact"]["problems"] == []


def test_the_package_validity_non_requirement_sits_beside_the_result(
    invalid_report: dict[str, Any],
) -> None:
    conformance = invalid_report["artifact"]["conformance"]

    assert conformance["non_requirements"] == [
        {
            "id": "package-validity",
            "profile_version": "0.4.0",
            "rationale": (
                "The device imposes no validity gate, so an EPUBCheck failure must never be "
                'read as "this book will not open". Galley still runs EPUBCheck and reports its '
                "result as a fact."
            ),
            "statement": "EPUB validity is not a requirement.",
        }
    ]


def test_human_output_shows_conformance_beside_the_non_requirement(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "valid.epub")

    results = run_public_cli("audit", str(book), "--profile", "x4-crosspoint")

    for result in results:
        assert result.returncode == 0
        assert (
            "Conformance: EPUBCheck 5.3.0; 0 fatal, 0 error, 0 warning, 0 usage\n" in result.stdout
        )
        assert (
            "Non-requirement: EPUB validity is not a requirement. (package-validity)\n"
            in result.stdout
        )

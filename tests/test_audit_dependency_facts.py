import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from tests.epub_fixtures import write_epub
from tests.public_cli import run_public_cli

# The Homebrew launcher is a shell script that execs a Java runtime, so an absent runtime
# surfaces exactly this way: a non-zero exit, a Java diagnostic on stderr, and no JSON.
MISSING_JAVA = """#!/bin/sh
echo 'The operation could not be completed. Unable to locate a Java Runtime.' >&2
exit 1
"""
NO_JSON_WRITTEN = """#!/bin/sh
echo 'EPUBCheck completed'
exit 0
"""
UNREADABLE_JSON = """#!/bin/sh
printf 'not json at all' > "$3"
exit 0
"""
# A JSON object naming no checker version cannot be read as a conformance result.
CHECKERLESS_JSON = """#!/bin/sh
printf '{}' > "$3"
exit 0
"""
OTHER_VERSION = """#!/bin/sh
printf '{"checker":{"checkerVersion":"5.2.0","nFatal":0,"nError":0,"nWarning":0,"nUsage":0},\
"messages":[],"items":[],"publication":{}}' > "$3"
exit 0
"""
UNRUNNABLE = "#!/nonexistent/interpreter\n"


def stub(directory: Path, script: str) -> Path:
    command = directory / "epubcheck"
    _ = command.write_text(script, encoding="utf-8")
    command.chmod(0o755)
    return command


def audit_with(book: Path, command: str) -> dict[str, Any]:
    """Audit one EPUB with an explicitly selected EPUBCheck command."""

    before = sha256(book.read_bytes()).hexdigest()
    results = run_public_cli(
        "audit",
        str(book),
        "--profile",
        "x4-crosspoint",
        "--json",
        environment={"GALLEY_EPUBCHECK": command},
    )

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    assert sha256(book.read_bytes()).hexdigest() == before
    reports: list[dict[str, Any]] = [json.loads(result.stdout) for result in results]
    return reports[0]


def test_a_missing_epubcheck_completes_audit_as_an_execution_fact(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")

    report = audit_with(book, "galley-epubcheck-not-installed")

    conformance = report["artifact"]["conformance"]
    assert report["outcome"] == "completed"
    assert conformance["checked"] is False
    assert conformance["reason"] == "not-found"
    assert conformance["command"] == "galley-epubcheck-not-installed"
    assert conformance["tool"] == "epubcheck"
    assert "epubcheck" not in report["galley"]["dependencies"]
    assert [entry["id"] for entry in conformance["non_requirements"]] == ["package-validity"]


def test_a_missing_java_runtime_is_an_execution_fact_with_its_diagnostic(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    command = stub(tmp_path, MISSING_JAVA)

    report = audit_with(book, str(command))

    conformance = report["artifact"]["conformance"]
    assert report["outcome"] == "completed"
    assert conformance["checked"] is False
    assert conformance["reason"] == "no-output"
    assert conformance["exit_code"] == {"basis": "measured", "unit": "exit code", "value": 1}
    assert "Unable to locate a Java Runtime" in str(conformance["stderr"])
    assert "epubcheck" not in report["galley"]["dependencies"]


@pytest.mark.parametrize(
    ("script", "reason"),
    (
        (NO_JSON_WRITTEN, "no-output"),
        (UNREADABLE_JSON, "malformed-output"),
        (CHECKERLESS_JSON, "malformed-output"),
    ),
)
def test_unusable_dependency_output_is_an_execution_fact(
    tmp_path: Path, script: str, reason: str
) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    command = stub(tmp_path, script)

    report = audit_with(book, str(command))

    conformance = report["artifact"]["conformance"]
    assert report["outcome"] == "completed"
    assert conformance["checked"] is False
    assert conformance["reason"] == reason
    assert conformance["exit_code"]["value"] == 0


def test_a_failed_conformance_run_never_modifies_the_epub(tmp_path: Path) -> None:
    enclosure = tmp_path / "enclosure"
    enclosure.mkdir()
    book = write_epub(enclosure / "fixture.epub")
    original = book.read_bytes()
    command = stub(tmp_path, MISSING_JAVA)
    os.chmod(book, 0o444)
    os.chmod(enclosure, 0o555)
    try:
        report = audit_with(book, str(command))
    finally:
        os.chmod(enclosure, 0o755)

    assert report["artifact"]["conformance"]["checked"] is False
    assert book.read_bytes() == original
    assert [entry.name for entry in enclosure.iterdir()] == ["fixture.epub"]


def test_a_checkerless_document_is_never_reported_as_a_completed_check(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    command = stub(tmp_path, CHECKERLESS_JSON)

    conformance = audit_with(book, str(command))["artifact"]["conformance"]

    assert conformance["checked"] is False
    assert "version" not in conformance
    assert "valid" not in conformance
    assert "counts" not in conformance


def test_an_unpinned_epubcheck_version_is_recorded_rather_than_assumed(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    command = stub(tmp_path, OTHER_VERSION)

    report = audit_with(book, str(command))

    conformance = report["artifact"]["conformance"]
    assert conformance["checked"] is True
    assert conformance["version"] == "5.2.0"
    assert conformance["pinned_version"] == "5.3.0"
    assert conformance["matches_pinned_version"] is False
    assert report["galley"]["dependencies"]["epubcheck"] == "5.2.0"


def test_an_unrunnable_epubcheck_is_an_execution_fact(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    command = stub(tmp_path, UNRUNNABLE)

    conformance = audit_with(book, str(command))["artifact"]["conformance"]

    assert conformance["checked"] is False
    assert conformance["reason"] == "not-executable"
    assert conformance["detail"]


def test_dependency_stdout_is_captured_as_a_fact(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    command = stub(tmp_path, NO_JSON_WRITTEN)

    conformance = audit_with(book, str(command))["artifact"]["conformance"]

    assert conformance["stdout"] == "EPUBCheck completed"
    assert conformance["stderr"] == ""

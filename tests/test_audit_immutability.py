import json
import os
from hashlib import sha256
from pathlib import Path

import pytest

from tests.epub_fixtures import CHAPTER_PATH, default_entries, replace, write_epub
from tests.public_cli import run_cli

MALFORMED_XML = b'<?xml version="1.0" encoding="UTF-8"?>\n<html><body><p>unclosed\n'

# Immutability holds only if the real checker leaves the subject alone too, so this
# module opts out of the suite's instant EPUBCheck stand-in.
pytestmark = pytest.mark.real_epubcheck


def test_audit_never_writes_beside_a_read_only_subject(tmp_path: Path) -> None:
    enclosure = tmp_path / "enclosure"
    enclosure.mkdir()
    book = write_epub(enclosure / "read-only.epub")
    before = book.stat()
    digest = sha256(book.read_bytes()).hexdigest()
    os.chmod(book, 0o444)
    os.chmod(enclosure, 0o555)
    try:
        results = run_cli("audit", str(book), "--profile", "x4-crosspoint", "--json")
    finally:
        os.chmod(enclosure, 0o755)

    assert (results.returncode, results.stderr) == (0, "")
    after = book.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    assert sha256(book.read_bytes()).hexdigest() == digest
    assert [entry.name for entry in enclosure.iterdir()] == ["read-only.epub"]


def test_a_malformed_package_never_changes_the_audited_bytes(tmp_path: Path) -> None:
    entries = replace(default_entries(), CHAPTER_PATH, MALFORMED_XML)
    book = write_epub(tmp_path / "malformed.epub", entries)
    original = book.read_bytes()

    result = run_cli("audit", str(book), "--profile", "x4-crosspoint", "--json")

    assert (result.returncode, result.stderr) == (0, "")
    assert book.read_bytes() == original
    report = json.loads(result.stdout)
    assert report["outcome"] == "completed"
    assert report["artifact"]["sha256"] == sha256(original).hexdigest()

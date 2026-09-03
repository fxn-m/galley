import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path

from tests.support.epub_fixtures import write_epub
from tests.support.public_cli import NO_EPUBCHECK, cli_command, run_cli

EPUBCHECK_ENV = {**os.environ, **NO_EPUBCHECK}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_audit_writes_the_same_report_to_a_file(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")
    before = digest(book)

    command = cli_command("audit", str(book))
    report_path = tmp_path / "report-0.json"
    result = subprocess.run(
        [*command, "--profile", "x4-crosspoint", "--json", "--report-out", str(report_path)],
        check=False,
        capture_output=True,
        text=True,
        env=EPUBCHECK_ENV,
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert json.loads(result.stdout) == json.loads(report_path.read_text(encoding="utf-8"))
    assert digest(book) == before


def test_audit_report_output_never_replaces_the_audited_epub(tmp_path: Path) -> None:
    command = cli_command("audit")
    book = write_epub(tmp_path / "fixture-0.epub")
    before = digest(book)
    result = subprocess.run(
        [
            *command,
            str(book),
            "--profile",
            "x4-crosspoint",
            "--json",
            "--report-out",
            str(book),
            "--overwrite",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=EPUBCHECK_ENV,
    )

    assert (result.returncode, result.stderr) == (3, "")
    report = json.loads(result.stdout)
    assert report["refusal"]["boundary"] == "output-is-input"
    assert digest(book) == before


def test_audit_overwrite_without_a_report_output_is_an_invocation_error(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "fixture.epub")

    result = run_cli(
        "audit",
        str(book),
        "--profile",
        "x4-crosspoint",
        "--overwrite",
        "--json",
        environment=NO_EPUBCHECK,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "requires --report-out" in result.stderr

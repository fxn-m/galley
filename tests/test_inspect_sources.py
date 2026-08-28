import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from galley.sources import accepted_routes, classify
from tests.markdown_fixtures import write_markdown
from tests.public_cli import public_cli_commands, run_command, run_public_cli

HTML_VARIANTS = ("saved.html", "saved.htm", "saved.HTML", "saved.Htm", "saved.xhtml")
REFUSED_KINDS = {
    "saved.html": "local-html",
    "report.pdf": "pdf",
    "book.epub": "epub",
    "notes": "unknown-local-kind",
    "archive.tar.gz": "unknown-local-kind",
}
NON_HTTP_URLS = ("file:///tmp/page.html", "ftp://example.com/a.md", "data:text/plain,hello")


def refuse(source: Path | str) -> list[Any]:
    results = run_public_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json")
    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    return [json.loads(result.stdout) for result in results]


def test_markdown_and_live_urls_are_the_supported_routes() -> None:
    assert classify("notes.md").supported is True
    assert classify("notes.MARKDOWN").supported is True
    assert classify("https://example.com/essay").supported is True
    assert classify("http://example.com/essay").supported is True
    assert [kind.id for kind in (classify("a.md"), classify("http://e.com"))] == [
        "markdown",
        "article-url",
    ]
    assert accepted_routes() == [
        "a local Markdown file (.md or .markdown)",
        "an http:// or https:// Article-Like Page",
    ]


def test_every_refused_local_kind_names_its_kind_and_the_accepted_routes(tmp_path: Path) -> None:
    for name, kind in REFUSED_KINDS.items():
        source = tmp_path / name
        original = f"Galley must not read {name}.\n".encode()
        _ = source.write_bytes(original)

        for report in refuse(source):
            refusal = report["refusal"]
            assert refusal["boundary"] == "unsupported-source-kind"
            assert refusal["stage"] == "source-classification"
            assert refusal["authority"] == "inspect"
            assert refusal["artifact_written"] is False
            assert refusal["fact"]["kind"] == kind
            assert refusal["fact"]["accepted"] == accepted_routes()
            assert refusal["fact"]["reason"]
            # The profile resolved; only the source did not.
            assert report["profile"]["resolved"] is True
            assert report["source"] is None
        assert source.read_bytes() == original


def test_common_local_html_filename_variants_are_all_refused(tmp_path: Path) -> None:
    for name in HTML_VARIANTS:
        source = tmp_path / name
        _ = source.write_text("<html><body><p>saved</p></body></html>\n", encoding="utf-8")

        for report in refuse(source):
            assert report["refusal"]["fact"]["kind"] == "local-html"


def test_non_http_url_schemes_are_refused() -> None:
    for locator in NON_HTTP_URLS:
        for report in refuse(locator):
            assert report["refusal"]["fact"]["kind"] == "unsupported-url-scheme"
            assert report["refusal"]["fact"]["source"] == locator


def test_a_refused_source_is_never_read_or_changed(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    original = b"PK\x03\x04 not a Galley source\n"
    _ = source.write_bytes(original)

    _ = refuse(source)

    assert source.read_bytes() == original
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["book.epub"]


def test_an_inspected_source_is_unchanged_after_success(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("inspect")):
        source = write_markdown(tmp_path / f"kept-{index}.md")
        original = source.read_bytes()
        evidence = tmp_path / f"evidence-{index}"
        result = run_command(
            command,
            str(source),
            "--profile",
            "x4-crosspoint",
            "--json",
            "--evidence-dir",
            str(evidence),
            "--report-out",
            str(tmp_path / f"report-{index}.json"),
        )

        assert (result.returncode, result.stderr) == (0, "")
        assert source.read_bytes() == original
        assert (
            sha256(source.read_bytes()).hexdigest() == json.loads(result.stdout)["source"]["sha256"]
        )


def test_a_refused_source_kind_writes_no_evidence(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    _ = source.write_bytes(b"%PDF-1.4\n")

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        evidence = tmp_path / f"refused-{index}"
        result = run_command(
            command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (3, "")
        assert json.loads(result.stdout)["refusal"]["boundary"] == "unsupported-source-kind"
        # A refusal still publishes its Report; there is no Canonical Document to publish.
        assert sorted(entry.name for entry in evidence.iterdir()) == ["report.json"]


def test_no_output_can_replace_the_named_source(tmp_path: Path) -> None:
    """Naming a file Galley refuses is not permission to overwrite it."""

    for index, command in enumerate(public_cli_commands("inspect")):
        evidence = tmp_path / f"collision-{index}"
        evidence.mkdir()
        source = evidence / "report.json"
        original = b"MY IMPORTANT SOURCE\n"
        _ = source.write_bytes(original)
        result = run_command(
            command,
            str(source),
            "--profile",
            "x4-crosspoint",
            "--json",
            "--evidence-dir",
            str(evidence),
            "--overwrite",
        )

        assert (result.returncode, result.stderr) == (3, "")
        refusal = json.loads(result.stdout)["refusal"]
        assert refusal["boundary"] == "output-is-input"
        assert refusal["stage"] == "evidence-output"
        assert source.read_bytes() == original


def test_a_second_pathname_cannot_defeat_source_identity(tmp_path: Path) -> None:
    """The evidence directory is guarded by identity, not by name."""

    for index, command in enumerate(public_cli_commands("inspect")):
        evidence = tmp_path / f"linked-{index}"
        evidence.mkdir()
        source = write_markdown(tmp_path / f"linked-{index}.md")
        original = source.read_bytes()
        os.link(source, evidence / "preservation-baseline.txt")
        result = run_command(
            command,
            str(source),
            "--profile",
            "x4-crosspoint",
            "--json",
            "--evidence-dir",
            str(evidence),
            "--overwrite",
        )

        assert (result.returncode, result.stderr) == (3, "")
        assert json.loads(result.stdout)["refusal"]["boundary"] == "output-is-input"
        assert source.read_bytes() == original

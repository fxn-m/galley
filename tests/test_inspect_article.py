"""Inspect a live Article-Like Page through pinned Defuddle and pinned Pandoc."""

import json
from pathlib import Path
from typing import Any

from tests.article_fixtures import (
    ARTICLE_WORDS,
)
from tests.article_server import (
    MALFORMED_DEFUDDLE,
    extracted_content,
    native_html_ast,
    served,
    write_command,
    write_html,
)
from tests.markdown_fixtures import write_markdown
from tests.public_cli import (
    NO_DEFUDDLE,
    public_cli_commands,
    run_command,
    run_public_cli,
)


def inspect_json(source: str, *extra: str) -> list[Any]:
    results = run_public_cli("inspect", source, "--profile", "x4-crosspoint", "--json", *extra)
    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    return [json.loads(result.stdout) for result in results]


def test_an_http_article_is_inspected_into_a_canonical_document() -> None:
    """The locator is the source; retrieval and primary extraction belong to Defuddle."""

    with served() as url:
        for report in inspect_json(url):
            assert (report["outcome"], report["refusal"]) == ("completed", None)
            assert report["source"]["kind"] == "article-url"
            assert report["source"]["url"] == url
            canonical = report["canonical_document"]
            assert canonical["schema"] == "galley/canonical-document/1"
            assert canonical["title"] == "A Small Essay"
            assert canonical["source_url"] == url


def test_the_preservation_baseline_holds_the_extracted_prose(tmp_path: Path) -> None:
    """A baseline exists before any preparation transform, exactly as it does for Markdown."""

    with served() as url:
        for index, command in enumerate(public_cli_commands("inspect", url)):
            evidence = tmp_path / f"evidence-{index}"
            result = run_command(
                command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
            )

            assert (result.returncode, result.stderr) == (0, "")
            assert sorted(entry.name for entry in evidence.iterdir()) == [
                "canonical-document.json",
                "extraction.html",
                "preservation-baseline.txt",
                "report.json",
            ]
            baseline = (evidence / "preservation-baseline.txt").read_text(encoding="utf-8")
            for word in ARTICLE_WORDS:
                assert word in baseline
            # Defuddle removed the site chrome, so it never reaches the fixed point every
            # Text Preservation comparison is measured against.
            assert "Copyright chrome nobody reads." not in baseline


def test_the_report_records_both_tool_versions_and_what_defuddle_returned() -> None:
    """Extraction facts are what the dependency said, and say so; Galley remeasures separately."""

    with served() as url:
        for report in inspect_json(url):
            assert report["galley"]["dependencies"] == {"defuddle": "0.19.1", "pandoc": "3.10"}
            extraction = report["extraction"]
            assert extraction["title"] == "A Small Essay"
            assert extraction["author"] == "Ada Lovelace"
            assert extraction["source_url"] == url
            assert extraction["extractor"] == {
                "matches_pinned_version": True,
                "pinned_version": "0.19.1",
                "status": "ok",
                "tool": "defuddle",
                "version": "0.19.1",
            }
            # Defuddle counted these words; Galley did not, and the basis says which.
            assert extraction["word_count"]["basis"] == "reported"
            assert extraction["word_count"]["value"] > 0
            assert extraction["parse_time"]["basis"] == "reported"
            assert extraction["content_bytes"]["basis"] == "reported"
            # Galley's own count of the parsed document is measured, and is a separate fact.
            assert extraction["words"]["basis"] == "measured"
            assert extraction["words"]["value"] > 0


def test_the_canonical_document_carries_the_extracted_ast_verbatim(tmp_path: Path) -> None:
    """The envelope holds Pandoc's own JSON, not a Galley reconstruction of it."""

    with served() as url:
        content = extracted_content(url)
        for index, command in enumerate(public_cli_commands("inspect", url)):
            evidence = tmp_path / f"evidence-{index}"
            result = run_command(
                command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
            )

            assert (result.returncode, result.stderr) == (0, "")
            document = json.loads((evidence / "canonical-document.json").read_text("utf-8"))
            assert document["pandoc"] == native_html_ast(content, tmp_path)
            assert document["source_url"] == url


def test_a_retrieval_failure_is_a_tool_failure_and_not_an_extraction_failure() -> None:
    """Nothing about an unreachable server is evidence that the page holds no readable work."""

    with served() as url:
        pass  # The server is shut down on exit, so the locator now refuses connection.

    results = run_public_cli("inspect", url, "--profile", "x4-crosspoint", "--json")

    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    for result in results:
        refusal = json.loads(result.stdout)["refusal"]
        # Defuddle ran and could not retrieve the page: the tool failed, nothing is missing.
        assert refusal["boundary"] == "extraction-tool-failure"
        assert refusal["stage"] == "article-extraction"
        assert refusal["fact"]["reason"] == "failed"
        assert refusal["fact"]["url"] == url


def test_a_missing_defuddle_is_a_tool_failure_naming_the_pinned_version() -> None:
    """A dependency that is not installed produces a structured fact, never a shell traceback."""

    with served() as url:
        results = run_public_cli(
            "inspect", url, "--profile", "x4-crosspoint", "--json", environment=NO_DEFUDDLE
        )

    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    for result in results:
        refusal = json.loads(result.stdout)["refusal"]
        # The dependency is genuinely absent, which is the machine's problem and not this page's.
        assert refusal["boundary"] == "dependency-unavailable"
        assert refusal["stage"] == "article-extraction"
        assert refusal["fact"]["reason"] == "not-found"
        assert refusal["fact"]["pinned_version"] == "0.19.1"


def test_a_local_html_file_never_reaches_defuddle(tmp_path: Path) -> None:
    """HTML has one route; a saved page is refused before any tool runs."""

    source = write_html(tmp_path / "saved.html")

    results = run_public_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json")

    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    for result in results:
        report = json.loads(result.stdout)
        assert report["refusal"]["boundary"] == "unsupported-source-kind"
        assert report["refusal"]["fact"]["kind"] == "local-html"
        # No tool ran, so no version was recorded and no extraction fact exists.
        assert report["galley"]["dependencies"] == {}
        assert report["extraction"] is None


def test_human_output_names_the_page_the_extractor_and_the_measured_words() -> None:
    """The concise rendering consumes the same Report, and an article's source is its locator."""

    with served() as url:
        results = run_public_cli("inspect", url, "--profile", "x4-crosspoint")

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    for result in results:
        assert f"Source: {url} (article-url)" in result.stdout
        assert "Extraction: defuddle 0.19.1 (ok)" in result.stdout
        # Both counts are shown, and which one Galley took itself is stated rather than implied.
        measured = next(line for line in result.stdout.splitlines() if line.startswith("Words: "))
        assert measured.endswith(" reported")
        assert "measured;" in measured
        assert 'Canonical Document: "A Small Essay" by Ada Lovelace' in result.stdout


def test_malformed_extractor_output_is_a_tool_failure_naming_what_was_unusable(
    tmp_path: Path,
) -> None:
    """A document Galley cannot read is the extractor failing, not a page without a work."""

    command = write_command(tmp_path / "defuddle", MALFORMED_DEFUDDLE)

    with served() as url:
        results = run_public_cli(
            "inspect",
            url,
            "--profile",
            "x4-crosspoint",
            "--json",
            environment={"GALLEY_DEFUDDLE": str(command)},
        )

    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    for result in results:
        report = json.loads(result.stdout)
        refusal = report["refusal"]
        assert refusal["boundary"] == "extraction-tool-failure"
        assert refusal["stage"] == "article-extraction"
        assert refusal["fact"]["reason"] == "malformed-output"
        # The version still answered, so it is recorded; only the extraction was unusable.
        assert report["galley"]["dependencies"] == {"defuddle": "0.19.1"}
        assert report["extraction"] is None


def test_the_extractor_output_is_retained_so_extraction_can_be_checked(tmp_path: Path) -> None:
    """Extraction is inspectable rather than trusted: its own cleaned HTML is kept beside the rest."""

    with served() as url:
        content = extracted_content(url)
        for index, command in enumerate(public_cli_commands("inspect", url)):
            evidence = tmp_path / f"evidence-{index}"
            result = run_command(
                command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
            )

            assert (result.returncode, result.stderr) == (0, "")
            retained = (evidence / "extraction.html").read_text(encoding="utf-8")
            # Exactly what the extractor produced, so a reader can judge the extractor itself.
            assert retained == content
            assert "Copyright chrome nobody reads." not in retained


def test_a_markdown_source_retains_no_extraction_output(tmp_path: Path) -> None:
    """Only a source with an extraction stage has extractor output to keep."""

    source = write_markdown(tmp_path / "notes.md")
    evidence = tmp_path / "evidence"
    result = run_command(
        public_cli_commands("inspect", str(source))[0],
        "--profile",
        "x4-crosspoint",
        "--json",
        "--evidence-dir",
        str(evidence),
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert not (evidence / "extraction.html").exists()

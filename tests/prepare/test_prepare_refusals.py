import json
from pathlib import Path

from tests.support.epub_fixtures import write_epub
from tests.support.markdown_fixtures import PLAIN_BOOK, write_markdown
from tests.support.public_cli import NO_PANDOC, run_cli

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


def test_prepare_without_an_output_destination_is_an_invocation_error(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    result = run_cli("prepare", str(source), *ARGUMENTS)

    assert result.returncode == 2
    assert "--output" in result.stderr
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["plain.md"]


def test_an_existing_artifact_refuses_and_is_left_untouched(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    output = tmp_path / "kept-0.epub"
    existing = b"A previously published artifact is not replaced in silence.\n"
    _ = output.write_bytes(existing)

    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS)

    assert (result.returncode, result.stderr) == (3, "")
    report = json.loads(result.stdout)
    refusal = report["refusal"]
    assert refusal["boundary"] == "output-exists"
    assert refusal["stage"] == "artifact-output"
    assert refusal["authority"] == "prepare"
    assert refusal["artifact_written"] is False
    assert refusal["fact"]["path"] == str(output.resolve())
    assert output.read_bytes() == existing
    assert not (tmp_path / "kept-0.galley").exists()


def test_stale_evidence_refuses_before_the_source_is_parsed(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    output = tmp_path / "stale-0.epub"
    evidence = tmp_path / "stale-0.galley"
    evidence.mkdir()
    stale = evidence / "canonical-document.json"
    _ = stale.write_bytes(b"A previous run left this behind.\n")

    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS)

    assert (result.returncode, result.stderr) == (3, "")
    report = json.loads(result.stdout)
    assert report["refusal"]["boundary"] == "output-exists"
    assert report["refusal"]["fact"]["path"] == str(stale.resolve())
    assert report["source"] is None
    assert report["canonical_document"] is None
    assert stale.read_bytes() == b"A previous run left this behind.\n"
    assert sorted(entry.name for entry in evidence.iterdir()) == ["canonical-document.json"]
    assert not output.exists()


def test_overwrite_replaces_the_artifact_and_its_evidence(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    output = tmp_path / "replaced-0.epub"
    _ = output.write_bytes(b"stale artifact bytes\n")
    evidence = tmp_path / "replaced-0.galley"
    evidence.mkdir()
    _ = (evidence / "preservation-baseline.txt").write_bytes(b"stale baseline\n")

    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS, "--overwrite")

    assert (result.returncode, result.stderr) == (0, "")
    report = json.loads(result.stdout)
    assert report["outcome"] == "completed"
    assert output.read_bytes()[:2] == b"PK"
    assert (evidence / "preservation-baseline.txt").read_bytes() != b"stale baseline\n"


def test_an_unsupported_source_kind_refuses_before_writing_anything(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "existing.epub")

    output = tmp_path / "from-epub-0.epub"

    result = run_cli("prepare", str(book), "--output", str(output), *ARGUMENTS)

    assert (result.returncode, result.stderr) == (3, "")
    refusal = json.loads(result.stdout)["refusal"]
    assert refusal["boundary"] == "unsupported-source-kind"
    assert refusal["authority"] == "prepare"
    assert not output.exists()
    assert not (tmp_path / "from-epub-0.galley").exists()


def test_a_missing_parser_refuses_and_publishes_no_artifact(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    output = tmp_path / "unparsed-0.epub"

    result = run_cli(
        "prepare", str(source), "--output", str(output), *ARGUMENTS, environment=NO_PANDOC
    )

    assert (result.returncode, result.stderr) == (3, "")
    report = json.loads(result.stdout)
    assert report["refusal"]["boundary"] == "dependency-unavailable"
    assert report["refusal"]["artifact_written"] is False
    assert report["source"]["sha256"] is not None
    assert not output.exists()
    evidence = tmp_path / "unparsed-0.galley"
    assert sorted(entry.name for entry in evidence.iterdir()) == ["report.json"]


def test_an_output_that_is_the_source_refuses_before_reading_it(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "self-0.md", PLAIN_BOOK)
    original = source.read_bytes()

    result = run_cli("prepare", str(source), "--output", str(source), *ARGUMENTS)

    assert (result.returncode, result.stderr) == (3, "")
    refusal = json.loads(result.stdout)["refusal"]
    assert refusal["boundary"] == "output-is-input"
    assert source.read_bytes() == original


def test_a_refused_run_leaves_no_staged_candidate_behind(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    output = tmp_path / "absent-0.epub"
    report_out = tmp_path / "taken-0.json"
    _ = report_out.write_text("{}\n", encoding="utf-8")

    result = run_cli(
        "prepare", str(source), "--output", str(output), *ARGUMENTS, "--report-out", str(report_out)
    )

    assert (result.returncode, result.stderr) == (3, "")
    assert json.loads(result.stdout)["refusal"]["boundary"] == "output-exists"
    assert not output.exists()
    assert [entry.name for entry in tmp_path.iterdir() if "candidate" in entry.name] == []
    assert report_out.read_text(encoding="utf-8") == "{}\n"

import json
from pathlib import Path

from tests.epub_fixtures import write_epub
from tests.markdown_fixtures import PLAIN_BOOK, write_markdown
from tests.public_cli import NO_PANDOC, public_cli_commands, run_command, run_public_cli

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


def test_prepare_without_an_output_destination_is_an_invocation_error(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    results = run_public_cli("prepare", str(source), *ARGUMENTS)

    assert [result.returncode for result in results] == [2, 2]
    for result in results:
        assert "--output" in result.stderr
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["plain.md"]


def test_an_existing_artifact_refuses_and_is_left_untouched(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output = tmp_path / f"kept-{index}.epub"
        existing = b"A previously published artifact is not replaced in silence.\n"
        _ = output.write_bytes(existing)

        result = run_command(command, "--output", str(output), *ARGUMENTS)

        assert (result.returncode, result.stderr) == (3, "")
        report = json.loads(result.stdout)
        refusal = report["refusal"]
        assert refusal["boundary"] == "output-exists"
        assert refusal["stage"] == "artifact-output"
        assert refusal["authority"] == "prepare"
        assert refusal["artifact_written"] is False
        assert refusal["fact"]["path"] == str(output.resolve())
        assert output.read_bytes() == existing
        assert not (tmp_path / f"kept-{index}.galley").exists()


def test_stale_evidence_refuses_before_the_source_is_parsed(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output = tmp_path / f"stale-{index}.epub"
        evidence = tmp_path / f"stale-{index}.galley"
        evidence.mkdir()
        stale = evidence / "canonical-document.json"
        _ = stale.write_bytes(b"A previous run left this behind.\n")

        result = run_command(command, "--output", str(output), *ARGUMENTS)

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

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output = tmp_path / f"replaced-{index}.epub"
        _ = output.write_bytes(b"stale artifact bytes\n")
        evidence = tmp_path / f"replaced-{index}.galley"
        evidence.mkdir()
        _ = (evidence / "preservation-baseline.txt").write_bytes(b"stale baseline\n")

        result = run_command(command, "--output", str(output), *ARGUMENTS, "--overwrite")

        assert (result.returncode, result.stderr) == (0, "")
        report = json.loads(result.stdout)
        assert report["outcome"] == "completed"
        assert output.read_bytes()[:2] == b"PK"
        assert (evidence / "preservation-baseline.txt").read_bytes() != b"stale baseline\n"


def test_an_unsupported_source_kind_refuses_before_writing_anything(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "existing.epub")

    for index, command in enumerate(public_cli_commands("prepare", str(book))):
        output = tmp_path / f"from-epub-{index}.epub"

        result = run_command(command, "--output", str(output), *ARGUMENTS)

        assert (result.returncode, result.stderr) == (3, "")
        refusal = json.loads(result.stdout)["refusal"]
        assert refusal["boundary"] == "unsupported-source-kind"
        assert refusal["authority"] == "prepare"
        assert not output.exists()
        assert not (tmp_path / f"from-epub-{index}.galley").exists()


def test_a_missing_parser_refuses_and_publishes_no_artifact(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output = tmp_path / f"unparsed-{index}.epub"

        result = run_command(command, "--output", str(output), *ARGUMENTS, environment=NO_PANDOC)

        assert (result.returncode, result.stderr) == (3, "")
        report = json.loads(result.stdout)
        assert report["refusal"]["boundary"] == "dependency-unavailable"
        assert report["refusal"]["artifact_written"] is False
        assert report["source"]["sha256"] is not None
        assert not output.exists()
        evidence = tmp_path / f"unparsed-{index}.galley"
        assert sorted(entry.name for entry in evidence.iterdir()) == ["report.json"]


def test_an_output_that_is_the_source_refuses_before_reading_it(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        source = write_markdown(tmp_path / f"self-{index}.md", PLAIN_BOOK)
        original = source.read_bytes()

        result = run_command(command, str(source), "--output", str(source), *ARGUMENTS)

        assert (result.returncode, result.stderr) == (3, "")
        refusal = json.loads(result.stdout)["refusal"]
        assert refusal["boundary"] == "output-is-input"
        assert source.read_bytes() == original


def test_a_refused_run_leaves_no_staged_candidate_behind(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "plain.md", PLAIN_BOOK)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output = tmp_path / f"absent-{index}.epub"
        report_out = tmp_path / f"taken-{index}.json"
        _ = report_out.write_text("{}\n", encoding="utf-8")

        result = run_command(
            command, "--output", str(output), *ARGUMENTS, "--report-out", str(report_out)
        )

        assert (result.returncode, result.stderr) == (3, "")
        assert json.loads(result.stdout)["refusal"]["boundary"] == "output-exists"
        assert not output.exists()
        assert [entry.name for entry in tmp_path.iterdir() if "candidate" in entry.name] == []
        assert report_out.read_text(encoding="utf-8") == "{}\n"

import json
from hashlib import sha256
from pathlib import Path

from tests.markdown_fixtures import (
    RETAINED_EVIDENCE_BASELINE,
    UNCLOSED_DIVISION,
    native_ast,
    write_markdown,
)
from tests.public_cli import public_cli_commands, run_command, run_public_cli


def test_inspect_without_an_evidence_directory_writes_nothing(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")

    results = run_public_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json")

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["retained.md"]


def test_evidence_directory_holds_the_report_document_and_baseline(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        evidence = tmp_path / f"evidence-{index}"
        result = run_command(
            command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        assert sorted(entry.name for entry in evidence.iterdir()) == [
            "canonical-document.json",
            "preservation-baseline.txt",
            "report.json",
        ]
        written = json.loads((evidence / "report.json").read_text(encoding="utf-8"))
        assert written == json.loads(result.stdout)
        document = json.loads((evidence / "canonical-document.json").read_text(encoding="utf-8"))
        assert document["pandoc"] == native_ast(source)
        assert set(document) == {"author", "pandoc", "schema", "source_url", "title", "warnings"}
        baseline = (evidence / "preservation-baseline.txt").read_bytes()
        assert baseline.decode("utf-8") == RETAINED_EVIDENCE_BASELINE
        assert written["canonical_document"]["preservation_baseline"]["sha256"] == (
            sha256(baseline).hexdigest()
        )


def test_canonical_document_hash_names_the_persisted_bytes(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        evidence = tmp_path / f"hashed-{index}"
        result = run_command(
            command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        written = (evidence / "canonical-document.json").read_bytes()
        report = json.loads(result.stdout)
        assert report["canonical_document"]["sha256"] == sha256(written).hexdigest()


def test_construction_events_become_warnings_on_both_surfaces(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "unclosed.md", UNCLOSED_DIVISION)

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        evidence = tmp_path / f"warned-{index}"
        result = run_command(
            command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        warnings = json.loads(result.stdout)["warnings"]
        assert len(warnings) == 1
        assert warnings[0]["stage"] == "source-parse"
        assert warnings[0]["event"] == "pandoc-message"
        assert warnings[0]["recomputable"] is False
        assert "unclosed" in warnings[0]["detail"]
        document = json.loads((evidence / "canonical-document.json").read_text(encoding="utf-8"))
        assert document["warnings"] == warnings
        assert "warnings" not in document["pandoc"]["meta"]


def test_existing_evidence_refuses_without_explicit_overwrite(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")
    original = source.read_bytes()

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        evidence = tmp_path / f"kept-{index}"
        evidence.mkdir()
        existing = evidence / "canonical-document.json"
        existing_bytes = b"Retained inspection evidence is immutable.\n"
        _ = existing.write_bytes(existing_bytes)
        result = run_command(
            command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (3, "")
        refusal = json.loads(result.stdout)["refusal"]
        assert refusal["boundary"] == "output-exists"
        assert refusal["stage"] == "evidence-output"
        assert refusal["fact"]["path"] == str(existing.resolve())
        assert existing.read_bytes() == existing_bytes
        assert sorted(entry.name for entry in evidence.iterdir()) == ["canonical-document.json"]
        assert source.read_bytes() == original


def test_overwrite_replaces_evidence_but_never_the_source(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")
    original = source.read_bytes()

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        evidence = tmp_path / f"replaced-{index}"
        evidence.mkdir()
        stale = evidence / "canonical-document.json"
        _ = stale.write_bytes(b"A previous run left this behind.\n")
        result = run_command(
            command,
            "--profile",
            "x4-crosspoint",
            "--json",
            "--evidence-dir",
            str(evidence),
            "--overwrite",
        )

        assert (result.returncode, result.stderr) == (0, "")
        report = json.loads(result.stdout)
        assert report["outcome"] == "completed"
        assert json.loads(stale.read_text(encoding="utf-8"))["pandoc"] == native_ast(source)
        assert json.loads((evidence / "report.json").read_text(encoding="utf-8")) == report
        assert source.read_bytes() == original


def test_overwrite_alone_is_an_invocation_error(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")

    results = run_public_cli(
        "inspect", str(source), "--profile", "x4-crosspoint", "--json", "--overwrite"
    )

    assert [result.returncode for result in results] == [2, 2]
    for result in results:
        assert "requires --report-out or --evidence-dir" in result.stderr
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["retained.md"]

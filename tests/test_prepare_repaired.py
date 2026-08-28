"""Prepare an agent-repaired Canonical Document through the shared pipeline, with its lineage."""

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from tests.prepared_epub import document_texts, navigation_entries
from tests.test_prepare_notes import note_documents
from tests.public_cli import public_cli_commands, run_command
from tests.repair_fixtures import CONSUMED_TOKENS, declarations, hand_rolled_repair

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


def digest(path: Path) -> str:
    """Hash one file independently of Galley, so a lineage claim is checked, not restated."""

    return sha256(path.read_bytes()).hexdigest()


def prepared(tmp_path: Path, index: int, command: list[str], *extra: str) -> tuple[Path, Any, int]:
    """Run one entry point into its own output path and return artifact, Report and exit code."""

    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, "--output", str(output), *ARGUMENTS, *extra)
    assert result.stderr == ""
    return output, json.loads(result.stdout), result.returncode


def test_the_three_repair_options_are_an_all_or_nothing_set(tmp_path: Path) -> None:
    source, repair = hand_rolled_repair(tmp_path)
    partial = [
        ("--canonical-document", str(repair.canonical)),
        ("--inspection-report", str(repair.report)),
        ("--preservation-baseline", str(repair.baseline)),
        (
            "--inspection-report",
            str(repair.report),
            "--canonical-document",
            str(repair.canonical),
        ),
    ]

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        for subset in partial:
            result = run_command(
                command,
                "--output",
                str(tmp_path / f"partial-{index}.epub"),
                *ARGUMENTS,
                *subset,
                environment={"TERM": "dumb", "COLUMNS": "200"},
            )

            assert result.returncode == 2
            assert result.stdout == ""
            assert "--inspection-report" in result.stderr
            assert not (tmp_path / f"partial-{index}.epub").exists()


def test_a_repaired_document_reaches_the_same_pipeline_a_parsed_one_does(tmp_path: Path) -> None:
    source, repair = hand_rolled_repair(tmp_path)
    declared = declarations(tmp_path / "expected.json", CONSUMED_TOKENS)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output, report, code = prepared(
            tmp_path,
            index,
            command,
            "--expected-missing-tokens",
            str(declared),
            *repair.options,
        )

        assert (code, report["outcome"]) == (0, "completed")
        assert output.is_file()
        assert navigation_entries(output) == ["Great Work", "Footnotes"]
        texts = document_texts(output)
        bodies = [texts[document] for document in note_documents(output)]
        assert bodies[0].removeprefix("Footnotes ").startswith("Footnote 1.")
        assert "Curiosity is the engine." in bodies[0]
        assert "Persistence keeps it running." in bodies[1]
        notes = next(
            entry
            for entry in report["preparation"]["transforms"]
            if entry["name"] == "note-conversion"
        )
        assert notes["fired"] is True
        assert notes["notes"]["value"] == 2


def test_the_report_records_the_chain_from_inspected_source_to_built_artifact(
    tmp_path: Path,
) -> None:
    source, repair = hand_rolled_repair(tmp_path)
    declared = declarations(tmp_path / "expected.json", CONSUMED_TOKENS)
    inspection = json.loads(repair.report.read_text(encoding="utf-8"))

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output, report, code = prepared(
            tmp_path, index, command, "--expected-missing-tokens", str(declared), *repair.options
        )

        assert code == 0
        lineage = report["source"]["repair"]
        assert lineage["changed"] is True
        assert lineage["source"] == {
            "kind": "markdown",
            "path": str(source.resolve()),
            "sha256": digest(source),
            "url": None,
        }
        assert lineage["inspection_report"] == {
            "command": "inspect",
            "path": str(repair.report.resolve()),
            "run_id": inspection["galley"]["run_id"],
            "sha256": digest(repair.report),
        }
        assert lineage["original_canonical_document"] == {
            "sha256": inspection["canonical_document"]["sha256"]
        }
        assert lineage["repaired_canonical_document"]["path"] == str(repair.canonical.resolve())
        assert lineage["preservation_baseline"] == {
            "path": str(repair.baseline.resolve()),
            "sha256": digest(repair.baseline),
        }
        # The retained baseline travels across the repair unchanged, so the Canonical Document
        # facts describe the pre-repair text the artifact is measured against.
        assert (
            report["canonical_document"]["preservation_baseline"]
            == inspection["canonical_document"]["preservation_baseline"]
        )
        # The fifth link, kept where audit reads it rather than copied into the chain.
        assert report["artifact"]["sha256"] == digest(output)


def test_text_the_repair_did_not_declare_still_refuses_the_book(tmp_path: Path) -> None:
    source, repair = hand_rolled_repair(tmp_path)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output, report, code = prepared(tmp_path, index, command, *repair.options)

        assert (code, report["outcome"]) == (3, "refused")
        assert not output.exists()
        assert report["refusal"]["boundary"] == "text-preservation"
        assert [entry["token"] for entry in report["refusal"]["fact"]["unexpected_missing"]] == [
            "Notes"
        ]
        assert report["refusal"]["artifact_written"] is False
        # The chain is recorded before any transform runs, so a refusal carries it too.
        assert report["source"]["repair"]["changed"] is True


def test_the_tokens_a_repair_consumes_are_declared_evidence_in_the_report(
    tmp_path: Path,
) -> None:
    source, repair = hand_rolled_repair(tmp_path)
    declared = declarations(tmp_path / "expected.json", {**CONSUMED_TOKENS, "Unlost": 2})

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report, code = prepared(
            tmp_path, index, command, "--expected-missing-tokens", str(declared), *repair.options
        )

        assert code == 0
        tokens = report["artifact"]["text_preservation"]["tokens"]
        # Every declaration is visible, including one that turned out not to be needed, so an
        # allowed loss is stated evidence rather than an exception that only shows when it fires.
        assert [entry["token"] for entry in tokens["declared"]] == ["Notes", "Unlost"]
        assert tokens["declared"][1]["count"]["value"] == 2
        assert [entry["token"] for entry in tokens["expected_missing"]] == ["Notes"]
        assert tokens["unexpected_missing"] == []


def test_the_repair_inputs_are_never_mutated_and_never_become_outputs(tmp_path: Path) -> None:
    source, repair = hand_rolled_repair(tmp_path)
    declared = declarations(tmp_path / "expected.json", CONSUMED_TOKENS)
    before = {path: path.read_bytes() for path in repair.paths}

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, _, completed = prepared(
            tmp_path, index, command, "--expected-missing-tokens", str(declared), *repair.options
        )
        _, _, refused = prepared(tmp_path, index + 10, command, *repair.options)

        assert (completed, refused) == (0, 3)
        assert {path: path.read_bytes() for path in repair.paths} == before

        for claimed in repair.paths:
            result = run_command(
                command,
                "--output",
                str(claimed),
                *ARGUMENTS,
                *repair.options,
            )
            written = run_command(
                command,
                "--output",
                str(tmp_path / f"clash-{index}.epub"),
                "--report-out",
                str(claimed),
                *ARGUMENTS,
                *repair.options,
            )

            for attempt in (result, written):
                report = json.loads(attempt.stdout)
                assert (attempt.returncode, report["outcome"]) == (3, "refused")
                assert report["refusal"]["boundary"] == "output-is-input"
            assert {path: path.read_bytes() for path in repair.paths} == before


def test_the_concise_output_names_the_repair_it_prepared(tmp_path: Path) -> None:
    source, repair = hand_rolled_repair(tmp_path)
    declared = declarations(tmp_path / "expected.json", CONSUMED_TOKENS)
    inspection = json.loads(repair.report.read_text(encoding="utf-8"))
    original = inspection["canonical_document"]["sha256"]

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        result = run_command(
            command,
            "--output",
            str(tmp_path / f"human-{index}.epub"),
            "--profile",
            "x4-crosspoint",
            "--expected-missing-tokens",
            str(declared),
            *repair.options,
        )

        assert result.returncode == 0
        assert f"Repaired Canonical Document: changed; original sha256 {original}" in result.stdout
        assert f"Inherited from: {repair.report.resolve()}" in result.stdout

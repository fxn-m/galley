import json
import os
import subprocess
from pathlib import Path

from tests.public_cli import public_cli_commands, run_public_cli


def test_unknown_profile_workflow_emits_a_refused_report(tmp_path: Path) -> None:
    source = tmp_path / "unread.md"
    original = b"This input must not be read or changed.\n"
    _ = source.write_bytes(original)

    results = run_public_cli("inspect", str(source), "--profile", "missing", "--json")

    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    assert source.read_bytes() == original
    reports = [json.loads(result.stdout) for result in results]
    for report in reports:
        assert set(report) == {
            "artifact",
            "canonical_document",
            "compatibility",
            "extraction",
            "galley",
            "observations",
            "outcome",
            "preparation",
            "profile",
            "reading_verdict",
            "refusal",
            "source",
            "warnings",
        }
        assert report["galley"]["report_schema"] == "galley/report/1"
        assert report["galley"]["command"] == "inspect"
        assert report["outcome"] == "refused"
        assert report["refusal"] == {
            "artifact_written": False,
            "authority": "inspect",
            "basis_for_inference": None,
            "boundary": "unknown-profile",
            "fact": {
                "known_profiles": ["kindle-ios-personal-documents", "x4-crosspoint"],
                "requested": "missing",
            },
            "stage": "profile-resolution",
            "summary": "unknown Device Profile: missing",
        }
        assert report["profile"] == {
            "id": None,
            "observed_software": None,
            "profile_version": None,
            "requested": "missing",
            "resolved": False,
        }
        assert report["source"] is None
        assert report["extraction"] is None
        assert report["canonical_document"] is None
        assert report["preparation"] is None
        assert report["artifact"] is None
        assert report["compatibility"] == []
        assert report["observations"] == []
        assert report["warnings"] == []
        assert report["reading_verdict"] == {"predicted": None, "value": "not_tested"}


def test_human_workflow_output_renders_the_same_refused_report(tmp_path: Path) -> None:
    source = tmp_path / "unread.md"
    _ = source.write_text("This workflow stops at profile resolution.\n", encoding="utf-8")

    results = run_public_cli("inspect", str(source), "--profile", "missing")

    expected = (
        "inspect: refused\n"
        "Profile: missing (unresolved)\n"
        "Boundary: unknown-profile\n"
        "Artifact written: no\n"
        "unknown Device Profile: missing\n"
    )
    assert [(result.returncode, result.stdout, result.stderr) for result in results] == [
        (3, expected, ""),
        (3, expected, ""),
    ]


def test_unknown_profile_workflow_writes_the_same_report_to_a_file(tmp_path: Path) -> None:
    source = tmp_path / "unread.md"
    original = b"Report output must not mutate this input.\n"
    _ = source.write_bytes(original)

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        report_path = tmp_path / f"report-{index}.json"
        result = subprocess.run(
            [
                *command,
                "--profile",
                "missing",
                "--json",
                "--report-out",
                str(report_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert (result.returncode, result.stderr) == (3, "")
        assert json.loads(result.stdout) == json.loads(report_path.read_text(encoding="utf-8"))
        assert source.read_bytes() == original


def test_existing_report_file_refuses_without_mutating_files(tmp_path: Path) -> None:
    source = tmp_path / "unread.md"
    source_bytes = b"The input is immutable.\n"
    report_bytes = b"Existing report evidence stays byte-for-byte unchanged.\n"
    _ = source.write_bytes(source_bytes)

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        report_path = tmp_path / f"existing-{index}.json"
        _ = report_path.write_bytes(report_bytes)
        result = subprocess.run(
            [
                *command,
                "--profile",
                "missing",
                "--json",
                "--report-out",
                str(report_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert (result.returncode, result.stderr) == (3, "")
        report = json.loads(result.stdout)
        assert report["refusal"] == {
            "artifact_written": False,
            "authority": "inspect",
            "basis_for_inference": None,
            "boundary": "output-exists",
            "fact": {"path": str(report_path.resolve())},
            "stage": "report-output",
            "summary": f"report output already exists: {report_path.resolve()}",
        }
        assert source.read_bytes() == source_bytes
        assert report_path.read_bytes() == report_bytes


def test_report_overwrite_never_replaces_the_workflow_input(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("inspect")):
        source = tmp_path / f"input-{index}.md"
        source_bytes = b"Even explicit overwrite cannot replace an input.\n"
        _ = source.write_bytes(source_bytes)
        result = subprocess.run(
            [
                *command,
                str(source),
                "--profile",
                "missing",
                "--json",
                "--report-out",
                str(source),
                "--overwrite",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert (result.returncode, result.stderr) == (3, "")
        report = json.loads(result.stdout)
        assert report["refusal"] == {
            "artifact_written": False,
            "authority": "inspect",
            "basis_for_inference": None,
            "boundary": "output-is-input",
            "fact": {"path": str(source.resolve())},
            "stage": "report-output",
            "summary": f"report output is the workflow input: {source.resolve()}",
        }
        assert source.read_bytes() == source_bytes


def test_report_overwrite_replaces_only_the_command_owned_output(tmp_path: Path) -> None:
    source = tmp_path / "unread.md"
    source_bytes = b"Overwrite applies to the report, never this input.\n"
    _ = source.write_bytes(source_bytes)

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        report_path = tmp_path / f"replaceable-{index}.json"
        _ = report_path.write_text("old report\n", encoding="utf-8")
        result = subprocess.run(
            [
                *command,
                "--profile",
                "missing",
                "--json",
                "--report-out",
                str(report_path),
                "--overwrite",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert (result.returncode, result.stderr) == (3, "")
        assert json.loads(result.stdout) == json.loads(report_path.read_text(encoding="utf-8"))
        assert source.read_bytes() == source_bytes


def test_overwrite_without_a_report_output_is_an_invocation_error(tmp_path: Path) -> None:
    source = tmp_path / "unread.md"
    _ = source.write_text("This workflow must not begin.\n", encoding="utf-8")

    results = run_public_cli(
        "inspect", str(source), "--profile", "missing", "--overwrite", "--json"
    )

    assert [result.returncode for result in results] == [2, 2]
    assert [result.stdout for result in results] == ["", ""]
    for result in results:
        assert "--overwrite" in result.stderr
        assert "requires --report-out or --evidence-dir" in result.stderr


def test_report_overwrite_never_replaces_a_hard_link_to_the_input(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("inspect")):
        source = tmp_path / f"hard-linked-input-{index}.md"
        report_path = tmp_path / f"hard-linked-report-{index}.json"
        source_bytes = b"A second pathname must not defeat input identity.\n"
        _ = source.write_bytes(source_bytes)
        os.link(source, report_path)

        result = subprocess.run(
            [
                *command,
                str(source),
                "--profile",
                "missing",
                "--json",
                "--report-out",
                str(report_path),
                "--overwrite",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert (result.returncode, result.stderr) == (3, "")
        report = json.loads(result.stdout)
        assert report["refusal"]["boundary"] == "output-is-input"
        assert source.read_bytes() == source_bytes
        assert report_path.read_bytes() == source_bytes


def test_report_write_failure_emits_a_structured_internal_error(tmp_path: Path) -> None:
    source = tmp_path / "unread.md"
    source_bytes = b"A report write failure must not affect this input.\n"
    report_path = tmp_path / "missing" / "report.json"
    _ = source.write_bytes(source_bytes)

    results = run_public_cli(
        "inspect",
        str(source),
        "--profile",
        "missing",
        "--json",
        "--report-out",
        str(report_path),
    )

    assert [(result.returncode, result.stderr) for result in results] == [(4, ""), (4, "")]
    for result in results:
        report = json.loads(result.stdout)
        assert report["outcome"] == "refused"
        assert report["refusal"] == {
            "artifact_written": False,
            "authority": "inspect",
            "basis_for_inference": None,
            "boundary": "internal-error",
            "fact": {
                "error_type": "FileNotFoundError",
                "operation": "write-report",
                "path": str(report_path.resolve()),
            },
            "stage": "report-output",
            "summary": "internal error while writing Report: FileNotFoundError",
        }
    assert not report_path.exists()
    assert source.read_bytes() == source_bytes

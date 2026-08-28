"""Refuse a repair that cannot be read, cannot be validated, or is not this preparation's.

Every case here is checked before the repaired document contributes one fact, so each refusal
publishes no book and retains no evidence: a run that declined its inputs produced nothing.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.markdown_fixtures import PLAIN_BOOK, write_markdown
from tests.public_cli import public_cli_commands, run_command
from tests.repair_fixtures import RepairInputs, edited, hand_rolled_repair, inspected

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


def refused(tmp_path: Path, source: Path, repair: RepairInputs, name: str) -> list[Any]:
    """Run both entry points with these Repair Inputs and require a refusal from each."""

    reports: list[Any] = []
    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        output = tmp_path / f"{name}-{index}.epub"
        result = run_command(command, "--output", str(output), *ARGUMENTS, *repair.options)
        report = json.loads(result.stdout)

        assert (result.returncode, report["outcome"]) == (3, "refused")
        assert report["refusal"]["artifact_written"] is False
        assert not output.exists()
        assert not (tmp_path / f"{name}-{index}.galley").exists()
        reports.append(report)
    return reports


@pytest.mark.parametrize(
    ("case", "boundary", "reason"),
    [
        ("missing", "unreadable-repair-input", "missing"),
        ("malformed", "invalid-repair-input", "malformed-json"),
        ("schema-invalid", "invalid-repair-input", "schema-invalid"),
        ("audit-report", "repair-lineage-mismatch", "not-an-inspection"),
        ("other-profile", "repair-lineage-mismatch", "profile-mismatch"),
        ("other-source", "repair-lineage-mismatch", "source-mismatch"),
        ("changed-source", "repair-lineage-mismatch", "source-changed"),
        ("other-baseline", "repair-lineage-mismatch", "baseline-mismatch"),
        ("other-api-version", "repair-lineage-mismatch", "pandoc-api-version-mismatch"),
    ],
)
def test_a_repair_that_is_not_this_preparation_refuses(
    tmp_path: Path, case: str, boundary: str, reason: str
) -> None:
    source, repair = hand_rolled_repair(tmp_path)
    broken = _broken(tmp_path, source, repair, case)

    for report in refused(tmp_path, source, broken, case):
        assert report["refusal"]["boundary"] == boundary
        assert report["refusal"]["fact"]["reason"] == reason
        assert report["refusal"]["stage"] == "repair-input"
        assert report["canonical_document"] is None


def _broken(tmp_path: Path, source: Path, repair: RepairInputs, case: str) -> RepairInputs:
    """Damage exactly one thing about an otherwise-good repair."""

    if case == "missing":
        return replace(repair, baseline=tmp_path / "absent.txt")
    if case == "malformed":
        broken = tmp_path / "malformed.json"
        _ = broken.write_text("{ not json", encoding="utf-8")
        return replace(repair, canonical=broken)
    if case == "schema-invalid":
        return replace(
            repair,
            canonical=edited(
                repair.canonical, tmp_path / "no-pandoc.json", lambda d: d.pop("pandoc")
            ),
        )
    if case == "audit-report":
        return replace(
            repair,
            report=edited(
                repair.report,
                tmp_path / "audit-report.json",
                lambda d: d["galley"].update(command="audit"),
            ),
        )
    if case == "other-profile":
        return replace(
            repair,
            report=edited(
                repair.report,
                tmp_path / "other-profile.json",
                lambda d: d["profile"].update(id="some-other-device"),
            ),
        )
    if case == "other-source":
        other = write_markdown(tmp_path / "other.md", PLAIN_BOOK)
        elsewhere = inspected(tmp_path / "other.galley", str(other))
        return replace(repair, report=elsewhere / "report.json")
    if case == "changed-source":
        _ = source.write_text(f"{source.read_text(encoding='utf-8')}\nA later edit.\n", "utf-8")
        return repair
    if case == "other-baseline":
        rewritten = tmp_path / "other-baseline.txt"
        _ = rewritten.write_text("Not the retained text.\n", encoding="utf-8")
        return replace(repair, baseline=rewritten)
    return replace(
        repair,
        canonical=edited(
            repair.canonical,
            tmp_path / "other-api.json",
            lambda d: d["pandoc"].update({"pandoc-api-version": [1, 23, 1]}),
        ),
    )

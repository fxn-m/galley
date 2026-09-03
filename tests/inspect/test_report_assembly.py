"""Run-scoped Report assembly and validation at every public Report seam."""

from pathlib import Path
from typing import cast

import pytest
from jsonschema import ValidationError

from galley.output.policy import apply_report_output_policy
from galley.profile.loading import load_profile
from galley.report.envelope import (
    ReportAssembly,
    ReportRun,
    report_json,
    unknown_profile_report,
)


def test_report_assembly_hides_intermediate_invalidity_until_completion() -> None:
    assembly = ReportAssembly.completed("inspect", load_profile("x4-crosspoint"))
    assembly.add_facts("source", {"word_count": 12})
    source: dict[str, object] = {"word_count": {"value": 12, "basis": "measured"}}

    assembly.add_facts("source", source)
    report = assembly.complete()
    source["word_count"] = {"value": 13, "basis": "measured"}

    assert report["source"] == {"word_count": {"value": 12, "basis": "measured"}}


def test_report_assembly_returns_an_independent_validated_refusal() -> None:
    assembly = ReportAssembly.completed("inspect", load_profile("x4-crosspoint"))
    assembly.add_facts("source", {"word_count": {"value": 12, "basis": "measured"}})

    refused = assembly.refuse(
        boundary="example-refusal",
        stage="example-stage",
        summary="the example stopped",
        fact={"reason": "example"},
    )

    assert refused["outcome"] == "refused"
    assert refused["source"] == {"word_count": {"value": 12, "basis": "measured"}}
    assert assembly.complete()["outcome"] == "completed"


def test_report_assembly_owns_dependency_evaluation_and_warning_order() -> None:
    assembly = ReportAssembly.completed("inspect", load_profile("x4-crosspoint"))
    warnings: list[dict[str, object]] = [
        {
            "stage": "source-parse",
            "event": "first",
            "detail": "First warning.",
            "recomputable": False,
        },
        {
            "stage": "source-parse",
            "event": "second",
            "detail": "Second warning.",
            "recomputable": False,
        },
    ]

    assembly.add_dependency("pandoc", "3.10")
    assembly.add_evaluation(compatibility=[], observations=[])
    assembly.add_warnings(warnings)
    report = assembly.complete()
    warnings.reverse()

    assert cast(dict[str, object], report["galley"])["dependencies"] == {"pandoc": "3.10"}
    assert [entry["event"] for entry in cast(list[dict[str, object]], report["warnings"])] == [
        "first",
        "second",
    ]


def test_workflow_completion_rejects_an_invalid_completed_report() -> None:
    assembly = ReportAssembly.completed("inspect", load_profile("x4-crosspoint"))
    assembly.add_facts("source", {"word_count": 12})

    with pytest.raises(ValidationError):
        assembly.complete()


def test_refusal_return_rejects_invalid_accumulated_facts() -> None:
    assembly = ReportAssembly.completed("inspect", load_profile("x4-crosspoint"))
    assembly.add_facts("source", {"word_count": 12})

    with pytest.raises(ValidationError):
        assembly.refuse(
            boundary="example-refusal",
            stage="example-stage",
            summary="the example stopped",
            fact={"reason": "example"},
        )


def test_serialization_revalidates_a_completed_report_after_nested_mutation() -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    profile = cast(dict[str, object], report["profile"])
    profile["resolved"] = True

    with pytest.raises(ValidationError):
        report_json(report)


def test_output_policy_rejects_an_invalid_completed_report(tmp_path: Path) -> None:
    run = ReportRun.start()
    report = ReportAssembly.completed("inspect", load_profile("x4-crosspoint"), run=run)
    report.complete()
    report["outcome"] = "unknown"

    with pytest.raises(ValidationError):
        apply_report_output_policy(
            report,
            source=None,
            output=tmp_path / "report.json",
            overwrite=False,
            run=run,
        )

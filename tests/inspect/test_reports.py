from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator, ValidationError

from galley.outcomes import ExitCode
from galley.output.policy import apply_report_output_policy
from galley.report.envelope import (
    REPORT_SCHEMA,
    ReportRun,
    unknown_profile_report,
    validate_report,
)
from galley.report.render import render_report

REQUIRED_REPORT_KEYS = (
    "galley",
    "outcome",
    "refusal",
    "profile",
    "source",
    "extraction",
    "canonical_document",
    "preparation",
    "artifact",
    "compatibility",
    "observations",
    "warnings",
    "reading_verdict",
)


def test_packaged_report_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(REPORT_SCHEMA)


@pytest.mark.parametrize("missing_key", REQUIRED_REPORT_KEYS)
def test_report_schema_requires_every_canonical_top_level_key(missing_key: str) -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    _ = report.pop(missing_key)

    with pytest.raises(ValidationError):
        validate_report(report)


def test_human_renderer_rejects_an_unvalidated_report() -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    invalid_report = deepcopy(report)
    invalid_report["outcome"] = "unknown"

    with pytest.raises(ValidationError):
        render_report(invalid_report)


@pytest.mark.parametrize(
    ("outcome", "refusal"),
    (("completed", "present"), ("refused", None)),
)
def test_report_schema_binds_refusal_presence_to_outcome(outcome: str, refusal: str | None) -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    report["outcome"] = outcome
    if refusal is None:
        report["refusal"] = None

    with pytest.raises(ValidationError):
        validate_report(report)


def test_report_schema_requires_quantity_basis_and_projected_relation() -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    measurement: dict[str, object] = {"value": 1}
    report["compatibility"] = [
        {
            "requirement_id": "example",
            "verdict": "unknown",
            "failure_mode": "unknown",
            "authority": "report",
            "applicability": True,
            "measurement": measurement,
            "enforced_limit": None,
            "observed_limit": None,
            "profile_version": "0.4.0",
        }
    ]

    with pytest.raises(ValidationError):
        validate_report(report)

    measurement["basis"] = "projected"
    with pytest.raises(ValidationError):
        validate_report(report)

    measurement["relation"] = "lower-bound"
    validate_report(report)


def test_report_schema_requires_basis_for_nested_fact_quantities() -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    report["source"] = {"word_count": {"value": 12}}

    with pytest.raises(ValidationError):
        validate_report(report)

    report["source"] = {"word_count": {"value": 12, "basis": "measured"}}
    validate_report(report)


@pytest.mark.parametrize(
    "source_facts",
    (
        {"word_count": 12},
        {"nested": {"page_count": 3}},
        {"samples": [1, 2]},
    ),
)
def test_report_schema_rejects_unwrapped_numeric_facts(
    source_facts: dict[str, object],
) -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    report["source"] = source_facts

    with pytest.raises(ValidationError):
        validate_report(report)


def test_report_schema_requires_relation_on_nested_projected_quantities() -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    report["source"] = {
        "outer": {
            "value": {"inner": {"value": 12, "basis": "projected"}},
            "basis": "measured",
        }
    }

    with pytest.raises(ValidationError):
        validate_report(report)


@pytest.mark.parametrize("field", ("fact", "basis_for_inference"))
def test_refusal_schema_rejects_unwrapped_numeric_facts(field: str) -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    refusal = cast(dict[str, object], report["refusal"])
    refusal[field] = {"threshold": 300}

    with pytest.raises(ValidationError):
        validate_report(report)


@pytest.mark.parametrize(
    "profile",
    (
        {
            "requested": "x4-crosspoint",
            "resolved": True,
            "id": None,
            "profile_version": None,
            "observed_software": None,
        },
        {
            "requested": "missing",
            "resolved": False,
            "id": "x4-crosspoint",
            "profile_version": "0.4.0",
            "observed_software": {
                "kind": "firmware",
                "observed_at": "2026-08-17",
                "operating_system": None,
                "version": "1.4.1",
            },
        },
    ),
)
def test_report_schema_rejects_contradictory_profile_resolution(
    profile: dict[str, object],
) -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    report["profile"] = profile

    with pytest.raises(ValidationError):
        validate_report(report)


def test_completed_report_requires_a_resolved_profile() -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    report["outcome"] = "completed"
    report["refusal"] = None

    with pytest.raises(ValidationError):
        validate_report(report)


def test_unknown_profile_refusal_requires_an_unresolved_profile() -> None:
    report = unknown_profile_report("inspect", "x4-crosspoint", ["x4-crosspoint"])
    report["profile"] = {
        "requested": "x4-crosspoint",
        "resolved": True,
        "id": "x4-crosspoint",
        "profile_version": "0.4.0",
        "observed_software": {
            "kind": "firmware",
            "observed_at": "2026-08-17",
            "operating_system": None,
            "version": "1.4.1",
        },
    }

    with pytest.raises(ValidationError):
        validate_report(report)


def test_output_refusal_preserves_accumulated_report_facts(tmp_path: Path) -> None:
    run = ReportRun.start()
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"], run=run)
    categories = ("source", "extraction", "canonical_document", "preparation", "artifact")
    for value, category in enumerate(categories, start=1):
        report[category] = {"count": {"value": value, "basis": "measured"}}
    report["warnings"] = [
        {
            "stage": "extraction",
            "event": "retained-warning",
            "detail": "This accumulated fact must survive a later refusal.",
            "recomputable": False,
        }
    ]
    validate_report(report)
    output = tmp_path / "existing-report.json"
    _ = output.write_text("existing\n", encoding="utf-8")

    emission = apply_report_output_policy(
        report,
        source=tmp_path / "source.md",
        output=output,
        overwrite=False,
        run=run,
    )

    assert emission.exit_code == ExitCode.REFUSED
    assert emission.report["refusal"] != report["refusal"]
    for category in categories:
        assert emission.report[category] == report[category]
    assert emission.report["warnings"] == report["warnings"]


def test_output_identity_failure_is_an_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = ReportRun.start()
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"], run=run)
    source = tmp_path / "source.md"
    output = tmp_path / "report.json"
    original_resolve = Path.resolve

    def fail_output_resolution(path: Path, strict: bool = False) -> Path:
        if path == output:
            raise PermissionError("identity unavailable")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_output_resolution)
    emission = apply_report_output_policy(
        report,
        source=source,
        output=output,
        overwrite=False,
        run=run,
    )

    assert emission.exit_code == ExitCode.INTERNAL_ERROR
    refusal = cast(dict[str, object], emission.report["refusal"])
    assert refusal["boundary"] == "internal-error"
    assert cast(dict[str, object], refusal["fact"])["operation"] == "identify-report-output"


@pytest.mark.parametrize("locations", ([12], [{"line": 7}]))
def test_observation_locations_reject_unwrapped_quantities(locations: list[object]) -> None:
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"])
    report["observations"] = [
        {
            "name": "example",
            "evidence": "computable",
            "consequence": "legibility",
            "applicability": True,
            "fired": False,
            "measurement": None,
            "locations": locations,
            "note": "A factual observation.",
        }
    ]

    with pytest.raises(ValidationError):
        validate_report(report)


def test_cli_exit_code_allocation_is_stable() -> None:
    assert ExitCode.COMPLETED == 0
    assert ExitCode.INVOCATION_ERROR == 2
    assert ExitCode.REFUSED == 3
    assert ExitCode.INTERNAL_ERROR == 4
    assert ExitCode.DELIVERY_UNCONFIRMED == 5

"""Create and validate canonical Reports."""

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Self, cast
from uuid import uuid4

from galley import __version__
from galley.reader_software import observed_software
from galley.report.clock import Clock, timestamp
from galley.validation import load_schema

Report = dict[str, object]
ReportCommand = Literal["inspect", "prepare", "audit", "localise"]
FactCategory = Literal["source", "extraction", "canonical_document", "preparation", "artifact"]


@dataclass(frozen=True)
class ReportRun:
    """One monotonic and UTC clock shared across a workflow."""

    started_at: datetime
    started_clock: int
    clock: Clock = field(default_factory=Clock)

    @classmethod
    def start(cls, clock: Clock | None = None) -> Self:
        ticking = clock if clock is not None else Clock()
        return cls(
            started_at=ticking.utc_now(), started_clock=ticking.monotonic_ns(), clock=ticking
        )


REPORT_SCHEMA, REPORT_VALIDATOR = load_schema("report.json")


def with_dependency(report: Report, name: str, version: str) -> Report:
    """Return the Report with one dependency version recorded in its envelope."""

    validate_report(report)
    updated = deepcopy(report)
    galley = cast(dict[str, object], updated["galley"])
    dependencies = cast(dict[str, str], galley["dependencies"])
    dependencies[name] = version
    validate_report(updated)
    return updated


def resolved_profile_facts(profile: dict[str, object]) -> dict[str, object]:
    """Describe a Device Profile that resolved by exact identifier."""

    return {
        "requested": profile["id"],
        "resolved": True,
        "id": profile["id"],
        "profile_version": profile["profile_version"],
        "observed_software": observed_software(profile),
    }


def unresolved_profile_facts(requested: str) -> dict[str, object]:
    """Describe a Device Profile request that never resolved."""

    return {
        "requested": requested,
        "resolved": False,
        "id": None,
        "profile_version": None,
        "observed_software": None,
    }


def completed_report(
    command: ReportCommand,
    profile: dict[str, object],
    *,
    run: ReportRun | None = None,
) -> Report:
    """Create the canonical envelope for a workflow that reached its end."""

    report = _envelope(command, resolved_profile_facts(profile), run or ReportRun.start())
    validate_report(report)
    return report


def unknown_profile_report(
    command: ReportCommand,
    requested: str,
    known_profiles: list[str],
    *,
    run: ReportRun | None = None,
) -> Report:
    """Create a refused Report without reading the workflow subject."""

    return refused_report(
        command,
        requested,
        boundary="unknown-profile",
        stage="profile-resolution",
        summary=f"unknown Device Profile: {requested}",
        fact={"requested": requested, "known_profiles": known_profiles},
        run=run,
    )


def refused_report(
    command: ReportCommand,
    requested: str,
    *,
    boundary: str,
    stage: str,
    summary: str,
    fact: dict[str, object],
    run: ReportRun | None = None,
) -> Report:
    """Create the complete canonical envelope for an early refusal."""

    report = _envelope(command, unresolved_profile_facts(requested), run or ReportRun.start())
    report["outcome"] = "refused"
    report["refusal"] = _refusal(command, boundary, stage, summary, fact)
    validate_report(report)
    return report


def with_evaluation(
    report: Report,
    *,
    compatibility: list[dict[str, object]],
    observations: list[dict[str, object]],
) -> Report:
    """Return the Report with profile Requirement Verdicts and observations joined in."""

    validate_report(report)
    updated = deepcopy(report)
    updated["compatibility"] = compatibility
    updated["observations"] = observations
    validate_report(updated)
    return updated


def with_warnings(report: Report, warnings: list[dict[str, object]]) -> Report:
    """Return the Report carrying only construction events that left no recomputable trace."""

    validate_report(report)
    updated = deepcopy(report)
    updated["warnings"] = warnings
    validate_report(updated)
    return updated


def with_facts(report: Report, category: FactCategory, facts: dict[str, object]) -> Report:
    """Return the Report with one fact category replaced by measured facts."""

    validate_report(report)
    updated = deepcopy(report)
    updated[category] = facts
    validate_report(updated)
    return updated


def replace_refusal(
    report: Report,
    *,
    boundary: str,
    stage: str,
    summary: str,
    fact: dict[str, object],
    basis: dict[str, object] | None = None,
) -> Report:
    """Replace only refusal state while retaining every accumulated fact.

    A refusal Galley inferred rather than observed carries its basis. The threshold and the
    documents behind it travel with the refusal, so an agent can weigh an inference without
    reading Galley's source.
    """

    validate_report(report)
    command = cast(str, cast(dict[str, object], report["galley"])["command"])
    refused = deepcopy(report)
    refused["outcome"] = "refused"
    refused["refusal"] = _refusal(command, boundary, stage, summary, fact, basis)
    validate_report(refused)
    return refused


def _refusal(
    command: str,
    boundary: str,
    stage: str,
    summary: str,
    fact: dict[str, object],
    basis: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "boundary": boundary,
        "authority": command,
        "stage": stage,
        "artifact_written": False,
        "summary": summary,
        "fact": fact,
        "basis_for_inference": basis,
    }


def validate_report(report: Report) -> None:
    """Reject any object outside the canonical Report schema."""

    REPORT_VALIDATOR.validate(report)


def report_json(report: Report) -> str:
    """Serialize one validated Report as stable JSON."""

    validate_report(report)
    return json.dumps(report, indent=2, sort_keys=True)


def finish_report(report: Report, run: ReportRun) -> Report:
    finalized = deepcopy(report)
    galley = cast(dict[str, object], finalized["galley"])
    finished_at, duration_ms = _finish_timing(run)
    galley["finished_at"] = timestamp(finished_at)
    galley["duration_ms"] = duration_ms
    validate_report(finalized)
    return finalized


def _envelope(command: ReportCommand, profile: dict[str, object], run: ReportRun) -> Report:
    finished_at, duration_ms = _finish_timing(run)
    return {
        "galley": {
            "version": __version__,
            "command": command,
            "run_id": str(uuid4()),
            "started_at": timestamp(run.started_at),
            "finished_at": timestamp(finished_at),
            "duration_ms": duration_ms,
            "report_schema": "galley/report/1",
            "dependencies": {},
        },
        "outcome": "completed",
        "refusal": None,
        "profile": profile,
        "source": None,
        "extraction": None,
        "canonical_document": None,
        "preparation": None,
        "artifact": None,
        "compatibility": [],
        "observations": [],
        "warnings": [],
        "reading_verdict": {"value": "not_tested", "predicted": None},
    }


def _finish_timing(run: ReportRun) -> tuple[datetime, int]:
    finished_at = run.clock.utc_now()
    duration_ms = max(0, (run.clock.monotonic_ns() - run.started_clock) // 1_000_000)
    return finished_at, duration_ms

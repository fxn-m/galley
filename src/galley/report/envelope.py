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


class ReportAssembly(dict[str, object]):
    """Accumulate one run's Report behind a small construction interface."""

    def __init__(self, report: Report, run: ReportRun) -> None:
        super().__init__(report)
        self._run = run
        self._validated_payload: str | None = None

    @classmethod
    def completed(
        cls,
        command: ReportCommand,
        profile: dict[str, object],
        *,
        run: ReportRun | None = None,
    ) -> Self:
        """Begin a Report for a workflow whose Device Profile resolved."""

        active_run = run or ReportRun.start()
        return cls(_envelope(command, resolved_profile_facts(profile), active_run), active_run)

    def add_facts(self, category: FactCategory, facts: dict[str, object]) -> Self:
        """Replace one fact category without validating an intentionally partial Report."""

        self[category] = deepcopy(facts)
        return self

    def add_dependency(self, name: str, version: str) -> Self:
        """Record one dependency version in insertion order."""

        galley = cast(dict[str, object], self["galley"])
        dependencies = cast(dict[str, str], galley["dependencies"])
        dependencies[name] = version
        return self

    def add_evaluation(
        self,
        *,
        compatibility: list[dict[str, object]],
        observations: list[dict[str, object]],
    ) -> Self:
        """Replace the profile joins as one ordered observation."""

        self["compatibility"] = deepcopy(compatibility)
        self["observations"] = deepcopy(observations)
        return self

    def add_warnings(self, warnings: list[dict[str, object]]) -> Self:
        """Replace construction events while preserving their observed order."""

        self["warnings"] = deepcopy(warnings)
        return self

    def complete(self) -> Self:
        """Validate the complete Report at a workflow's public seam."""

        validate_report(self)
        return self

    def finish(self) -> Self:
        """Update timing and validate immediately before public emission."""

        self.complete()
        finished = type(self)(deepcopy(dict(self)), self._run)
        _set_timing(finished, self._run)
        return finished.complete()

    def validation_is_current(self, payload: str) -> bool:
        """Say whether this exact nested state already passed the complete schema."""

        return self._validated_payload == payload

    def remember_validation(self, payload: str | None) -> None:
        """Remember the exact nested state accepted by the complete schema."""

        self._validated_payload = payload

    def refuse(
        self,
        *,
        boundary: str,
        stage: str,
        summary: str,
        fact: dict[str, object],
        basis: dict[str, object] | None = None,
    ) -> Self:
        """Return a validated refusal without changing the accumulated completed path."""

        refused = type(self)(deepcopy(dict(self)), self._run)
        command = cast(str, cast(dict[str, object], refused["galley"])["command"])
        refused["outcome"] = "refused"
        refused["refusal"] = _refusal(
            command, boundary, stage, summary, deepcopy(fact), deepcopy(basis)
        )
        return refused.complete()


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


def unknown_profile_report(
    command: ReportCommand,
    requested: str,
    known_profiles: list[str],
    *,
    run: ReportRun | None = None,
) -> ReportAssembly:
    """Create a refused Report without reading the workflow subject."""

    active_run = run or ReportRun.start()
    report = ReportAssembly(
        _envelope(command, unresolved_profile_facts(requested), active_run), active_run
    )
    return report.refuse(
        boundary="unknown-profile",
        stage="profile-resolution",
        summary=f"unknown Device Profile: {requested}",
        fact={"requested": requested, "known_profiles": known_profiles},
    )


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

    payload = _validation_payload(report)
    if (
        payload is not None
        and isinstance(report, ReportAssembly)
        and report.validation_is_current(payload)
    ):
        return
    REPORT_VALIDATOR.validate(report)
    if isinstance(report, ReportAssembly):
        report.remember_validation(payload)


def _validation_payload(report: Report) -> str | None:
    """Fingerprint nested Report state so unchanged public crossings reuse validation."""

    try:
        return json.dumps(report, sort_keys=True, separators=(",", ":"))
    except TypeError, ValueError:
        return None


def report_json(report: Report) -> str:
    """Serialize one validated Report as stable JSON."""

    validate_report(report)
    return json.dumps(report, indent=2, sort_keys=True)


def _set_timing(report: Report, run: ReportRun) -> None:
    galley = cast(dict[str, object], report["galley"])
    finished_at, duration_ms = _finish_timing(run)
    galley["finished_at"] = timestamp(finished_at)
    galley["duration_ms"] = duration_ms


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

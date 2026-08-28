"""Evaluate Device Profile Compatibility Requirements against measured artifact facts."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from galley.json_reading import integer, mapping, text
from galley.report.quantities import projected, quantity, reported

Verdict = Literal["true", "false", "unknown", "unevaluable", "not_applicable"]
VERDICTS: tuple[Verdict, ...] = ("true", "false", "unknown", "unevaluable", "not_applicable")


def to_verdict(value: object) -> Verdict:
    """Narrow a profile-stated verdict, never inventing one the vocabulary lacks."""

    for verdict in VERDICTS:
        if verdict == value:
            return verdict
    return "unknown"


def aggregate(results: Sequence[Verdict]) -> Verdict:
    """Combine per-subject verdicts: a known failure outranks any uncertainty."""

    if not results:
        return "not_applicable"
    for verdict in VERDICTS:
        if verdict != "true" and verdict in results:
            return verdict
    return "true"


@dataclass(frozen=True)
class Assessment:
    """A Requirement Verdict a measurement module reached against profile support data."""

    verdict: Verdict
    applicable: bool
    measurement: dict[str, object] | None = None


Relation = Literal["lower-bound", "indeterminate"]
LOWER_BOUND: Relation = "lower-bound"
INDETERMINATE: Relation = "indeterminate"


@dataclass(frozen=True)
class Instrument:
    """One quantity a Compatibility Requirement can be evaluated against.

    A `relation` makes the quantity a projection of a future artifact rather than a measurement
    of a real one. Only a lower bound already above the limit settles anything: it proves the
    limit is broken. Every other projection leaves the verdict `unknown`, because a projection
    below a limit proves nothing.
    """

    value: int
    unit: str
    definition: str
    applicable: bool = True
    reliable: bool = True
    note: str = ""
    relation: Relation | None = None


def evaluate_requirements(
    profile: dict[str, object],
    instruments: Mapping[str, Instrument],
    assessments: Mapping[str, Assessment] | None = None,
) -> list[dict[str, object]]:
    """Return one Requirement Verdict per profile requirement, ordered by requirement id."""

    profile_version = str(profile["profile_version"])
    requirements = cast(list[dict[str, object]], profile["requirements"])
    reached = assessments or {}
    results = [
        _result(
            requirement,
            profile_version,
            instruments.get(str(requirement.get("id"))),
            reached.get(str(requirement.get("id"))),
        )
        for requirement in requirements
    ]
    return sorted(results, key=lambda result: str(result["requirement_id"]))


def _result(
    requirement: dict[str, object],
    profile_version: str,
    instrument: Instrument | None,
    assessment: Assessment | None,
) -> dict[str, object]:
    limit = mapping(requirement.get("limit"))
    unit = text(limit.get("units"))
    verdict, applicability, measurement = _verdict(requirement, instrument, assessment, limit)
    return {
        "requirement_id": str(requirement.get("id")),
        "verdict": verdict,
        "failure_mode": str(requirement.get("failure_mode")),
        "authority": str(requirement.get("authority")),
        "applicability": applicability,
        "measurement": measurement,
        "enforced_limit": _limit(limit.get("enforced"), unit),
        "observed_limit": _limit(limit.get("observed"), unit),
        "profile_version": profile_version,
    }


def _verdict(
    requirement: dict[str, object],
    instrument: Instrument | None,
    assessment: Assessment | None,
    limit: dict[str, object],
) -> tuple[Verdict, bool | None, dict[str, object] | None]:
    declared = text(requirement.get("verdict"))
    if declared is not None and declared in VERDICTS:
        return declared, None, None
    if assessment is not None:
        return assessment.verdict, assessment.applicable, assessment.measurement
    if instrument is None:
        return "unknown", None, None
    if not instrument.applicable:
        return "not_applicable", False, None
    measurement = _measurement(instrument)
    if not instrument.reliable:
        return "unknown", True, measurement
    enforced = integer(limit.get("enforced"))
    if enforced is None:
        return "unknown", True, measurement
    if instrument.relation is not None:
        return _projected_verdict(instrument, enforced), True, measurement
    return ("true" if instrument.value <= enforced else "false"), True, measurement


def _projected_verdict(instrument: Instrument, enforced: int) -> Verdict:
    """Let a projection settle a requirement only where it genuinely proves the answer."""

    if instrument.relation == LOWER_BOUND and instrument.value > enforced:
        return "false"
    return "unknown"


def _measurement(instrument: Instrument) -> dict[str, object]:
    measurement = (
        quantity(instrument.value, instrument.unit)
        if instrument.relation is None
        else projected(instrument.value, instrument.unit, instrument.relation)
    )
    measurement["definition"] = instrument.definition
    if instrument.note:
        measurement["note"] = instrument.note
    return measurement


def _limit(value: object, unit: str | None) -> dict[str, object] | None:
    """Represent a Device Profile limit as a quantity the profile reports, not one Galley took."""

    number = integer(value)
    return None if number is None else reported(number, unit)

"""Audit an existing EPUB artifact without modifying it."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

from galley.epub.archive import (
    ArchiveError,
    EpubArchive,
    UnreadableReason,
    open_archive,
    unreadable_reason,
)
from galley.profile.compatibility import evaluate_requirements
from galley.epub.reading import read_artifact
from galley.tools.epubcheck import check_conformance
from galley.images.facts import assess, gather_images, image_facts, image_observations
from galley.document.link_kinds import RECORDED_LINKS_PER_BLOCK, profile_counting_rule
from galley.document.preservation import unavailable_text_preservation
from galley.epub.link_facts import link_facts, link_instruments, navigation_observations
from galley.epub.links import document_identifiers, measure_documents
from galley.epub.text import visible_spine_segments
from galley.locations import display_path
from galley.observations import merged_observations
from galley.report.envelope import (
    Report,
    ReportRun,
    completed_report,
    replace_refusal,
    with_dependency,
    with_evaluation,
    with_facts,
)
from galley.report.quantities import quantity

READ_CHUNK = 1 << 20
ARTIFACT_STAGE = "artifact-acquisition"


@dataclass(frozen=True)
class Unreadable:
    """One EPUB that could not be opened, and whatever was measured before it stopped."""

    reason: UnreadableReason
    detail: str
    facts: dict[str, object] | None = None


@dataclass(frozen=True)
class ArtifactAssessment:
    """Everything the read-only audit workflow measured on one real EPUB."""

    facts: dict[str, object]
    compatibility: list[dict[str, object]]
    observations: list[dict[str, object]]
    text_segments: tuple[str, ...]
    epubcheck_version: str | None = None


def audit_report(profile: dict[str, object], subject: Path, *, run: ReportRun) -> Report:
    """Assess one EPUB read-only and return the canonical audit Report."""

    display = display_path(subject)
    report = with_facts(completed_report("audit", profile, run=run), "artifact", {"path": display})
    assessed = assess_artifact(profile, subject, display=display)
    if isinstance(assessed, Unreadable):
        return unreadable_artifact(report, display, assessed)
    return with_assessment(report, assessed)


def unreadable_artifact(report: Report, display: str, unreadable: Unreadable) -> Report:
    """Refuse an EPUB that could not be read, keeping whatever was measured before it stopped."""

    kept = report if unreadable.facts is None else with_facts(report, "artifact", unreadable.facts)
    return _unreadable(kept, display, unreadable.reason, unreadable.detail)


def with_assessment(
    report: Report,
    assessment: ArtifactAssessment,
    *,
    observations: list[dict[str, object]] | None = None,
) -> Report:
    """Join one artifact assessment into whichever command's Report measured it.

    `prepare` measures its own candidate through this same workflow, so the artifact facts and
    Requirement Verdicts a prepared book carries are the ones `audit` would reach on the
    published bytes rather than a second, preparation-only reading of them. It supplies its own
    observations because it also holds source-side ones this measurement cannot settle; `audit`
    has only a book, so it keeps the ones the assessment reached.
    """

    joined = with_facts(report, "artifact", assessment.facts)
    joined = with_evaluation(
        joined,
        compatibility=assessment.compatibility,
        observations=assessment.observations if observations is None else observations,
    )
    if assessment.epubcheck_version is None:
        return joined
    return with_dependency(joined, "epubcheck", assessment.epubcheck_version)


def assess_artifact(
    profile: dict[str, object], subject: Path, *, display: str
) -> ArtifactAssessment | Unreadable:
    """Measure one real EPUB against a Device Profile, naming it by its published path.

    A prepared candidate is measured in temporary space but published elsewhere, so the path a
    Report states is supplied rather than taken from the file that was read.
    """

    try:
        byte_size, digest = _measure(subject)
    except OSError as error:
        return Unreadable(unreadable_reason(error), str(error))
    measured: dict[str, object] = {
        "byte_size": quantity(byte_size, "bytes"),
        "path": display,
        "sha256": digest,
    }
    try:
        opened = open_archive(subject)
    except ArchiveError as error:
        return Unreadable(error.reason, error.detail, measured)
    with opened as archive:
        opened_archive = EpubArchive(archive)
        reading = read_artifact(
            path=display,
            byte_size=byte_size,
            digest=digest,
            archive=opened_archive,
        )
        members = opened_archive.names
        evidence = gather_images(opened_archive, reading)
    facts = reading.facts
    measurement = measure_documents(
        reading.documents,
        identifiers={path: document_identifiers(root) for path, root in reading.documents},
        members=members,
        rule=profile_counting_rule(profile, RECORDED_LINKS_PER_BLOCK),
        chapters=reading.chapters,
        complete=reading.malformed_documents == 0,
    )
    facts["links"] = link_facts(measurement)
    facts["images"] = image_facts(profile, evidence)
    facts["text_preservation"] = unavailable_text_preservation()
    conformance = check_conformance(subject)
    facts["conformance"] = {**conformance.facts, "non_requirements": _non_requirements(profile)}
    return ArtifactAssessment(
        facts=facts,
        compatibility=evaluate_requirements(
            profile,
            link_instruments(measurement, chapters=len(reading.chapters)),
            assess(profile, evidence),
        ),
        observations=merged_observations(
            profile,
            [
                *navigation_observations(profile, measurement),
                *image_observations(profile, evidence),
            ],
        ),
        text_segments=visible_spine_segments(reading.spine_documents),
        epubcheck_version=conformance.version,
    )


def _non_requirements(profile: dict[str, object]) -> list[dict[str, object]]:
    """Show every non-requirement the Device Profile records beside the conformance result."""

    entries = cast(list[dict[str, object]], profile["non_requirements"])
    return sorted(
        (
            {
                "id": _sentence(entry.get("id")),
                "profile_version": profile["profile_version"],
                "rationale": _sentence(entry.get("rationale")),
                "statement": _sentence(entry.get("statement")),
            }
            for entry in entries
        ),
        key=lambda entry: str(entry["id"]),
    )


def _sentence(value: object) -> str | None:
    return " ".join(value.split()) if isinstance(value, str) else None


def _measure(subject: Path) -> tuple[int, str]:
    digest = sha256()
    byte_size = 0
    with subject.open("rb") as handle:
        while chunk := handle.read(READ_CHUNK):
            digest.update(chunk)
            byte_size += len(chunk)
    return byte_size, digest.hexdigest()


def _unreadable(report: Report, path: str, reason: UnreadableReason, detail: str) -> Report:
    return replace_refusal(
        report,
        boundary="unreadable-artifact",
        stage="artifact-acquisition",
        summary=f"cannot read EPUB: {path}",
        fact={"detail": detail, "path": path, "reason": reason},
    )

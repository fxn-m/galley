"""One preparation's result, and every boundary that ends it before a book is published.

Each refusal keeps the facts the run had already gathered and states what it did not do. A run
that stopped is only useful if it says where and why. Every
one of them retains its evidence, including the previews a reader would need to see what went
wrong, and none of them publishes an EPUB.
"""

from dataclasses import dataclass, field
from typing import cast

from galley.workflows.audit import Unreadable, unreadable_artifact
from galley.images.records import image_refusal, preservation_refusal
from galley.workflows.inspect import Inspection
from galley.locations import display_path
from galley.tools.packaging import PACKAGING_STAGE, Packaging
from galley.output.publication import ARTIFACT_STAGE, Collision, Publication
from galley.report.envelope import Report, replace_refusal
from galley.document.preservation import TextPreservation
from galley.transforms.working_copy import WorkingCopy

NOTE_STAGE = "note-conversion"
COMPATIBILITY_STAGE = "artifact-compatibility"
TEXT_PRESERVATION_STAGE = "text-preservation"
WELL_FORMEDNESS_STAGE = "artifact-well-formedness"


@dataclass(frozen=True)
class Preparation:
    """One preparation: its Report, the evidence it retained, and the EPUB it may publish."""

    report: Report
    document: dict[str, object] | None = None
    baseline: str | None = None
    extraction: str | None = None
    """The extractor's own cleaned HTML, where this source had an extraction stage at all."""
    publication: Publication | None = None
    retains_evidence: bool = False
    """Whether source handling began, and so whether this run has evidence worth retaining.

    A refusal reached before the source was read has produced nothing to keep, and writing an
    evidence directory beside an output it declined to touch would be a side effect the run
    itself denies having. Every refusal after that point retains what it gathered.
    """
    previews: dict[str, bytes] = field(default_factory=dict[str, bytes])
    """Deterministic image previews, which a refused run retains as diagnostic evidence too."""


def packaging_refused(report: Report, inspection: Inspection, packaging: Packaging) -> Preparation:
    """Refuse a candidate Pandoc never produced, keeping every fact gathered before it."""

    return Preparation(
        replace_refusal(
            report,
            boundary="packaging-failure",
            stage=PACKAGING_STAGE,
            summary=f"cannot package the Canonical Document as EPUB3: {packaging.detail}",
            fact={
                "detail": packaging.detail,
                "reason": packaging.reason,
                "tool": packaging.facts["tool"],
            },
        ),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
    )


def images_unprepared(inspection: Inspection, copy: WorkingCopy) -> Preparation:
    """Refuse before packaging when a referenced image never became bytes this run could package.

    Nothing was packaged, so `preparation` states nothing: the transforms ran on a working copy
    that was discarded. The refusal names every reference that failed and why, which is what a
    repair needs and what a book built around the gap would have hidden.
    """

    return Preparation(
        image_refusal(inspection.report, copy.images),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
    )


def images_unpreserved(
    report: Report,
    inspection: Inspection,
    lost: dict[str, object],
    previews: dict[str, bytes],
) -> Preparation:
    """Refuse a book that does not carry every image its Canonical Document referenced."""

    return Preparation(
        preservation_refusal(report, lost),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
        previews=previews,
    )


def compatibility_refused(
    report: Report,
    inspection: Inspection,
    previews: dict[str, bytes],
) -> Preparation | None:
    """Refuse false Requirement Verdicts whose Device Profile grants refusal authority."""

    results = cast(list[dict[str, object]], report["compatibility"])
    refusing_verdicts = [
        result
        for result in results
        if result["verdict"] == "false" and result["authority"] == "refuse"
    ]
    if not refusing_verdicts:
        return None
    identifiers = ", ".join(str(verdict["requirement_id"]) for verdict in refusing_verdicts)
    return Preparation(
        replace_refusal(
            report,
            boundary="compatibility",
            stage=COMPATIBILITY_STAGE,
            summary=f"the built artifact does not meet Compatibility Requirements: {identifiers}",
            fact={"false_verdicts": refusing_verdicts},
        ),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
        previews=previews,
    )


def content_malformed(
    report: Report,
    inspection: Inspection,
    malformed: list[str],
    previews: dict[str, bytes],
) -> Preparation:
    """Refuse a book carrying a chapter that is not well-formed XML, and name that chapter.

    This runs before Text Preservation deliberately. A chapter no parser can read yields no text
    to measure, so the run would otherwise refuse for the words it could not find rather than for
    the document it could not read. An observed failure reported 4,179 lost tokens that had not
    moved. Every claim downstream of the reading is unreliable in
    this state, so the honest answer is the earlier one.
    """

    return Preparation(
        replace_refusal(
            report,
            boundary="malformed-content-document",
            stage=WELL_FORMEDNESS_STAGE,
            summary=(
                "the built artifact carries a content document that is not well-formed XML: "
                f"{', '.join(malformed)}"
            ),
            fact={"malformed_documents": malformed},
        ),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
        previews=previews,
    )


def text_unpreserved(
    report: Report,
    inspection: Inspection,
    preservation: TextPreservation,
    previews: dict[str, bytes],
) -> Preparation:
    """Refuse a candidate whose measured text lost undeclared baseline tokens."""

    missing = preservation.unexpected_facts
    identifiers = ", ".join(str(entry["token"]) for entry in missing)
    return Preparation(
        replace_refusal(
            report,
            boundary="text-preservation",
            stage=TEXT_PRESERVATION_STAGE,
            summary=f"the built artifact unexpectedly lost baseline tokens: {identifiers}",
            fact={"unexpected_missing": missing},
        ),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
        previews=previews,
    )


def notes_mismatched(
    report: Report,
    inspection: Inspection,
    mismatch: dict[str, object],
    previews: dict[str, bytes],
) -> Preparation:
    """Refuse a book whose note representation the built artifact does not agree with.

    One file per note exists because the alternative misdirects silently. A count that does not
    survive packaging is that same failure arriving by another route, so the candidate is
    discarded rather than published with a note the reader cannot reach.
    """

    return Preparation(
        replace_refusal(
            report,
            boundary="note-representation-mismatch",
            stage=NOTE_STAGE,
            summary=(
                "the built book does not carry the note representation preparation produced: "
                f"{', '.join(cast(list[str], mismatch['disagreements']))}"
            ),
            fact=mismatch,
        ),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
        previews=previews,
    )


def candidate_unreadable(
    report: Report, inspection: Inspection, publication: Publication, assessed: Unreadable
) -> Preparation:
    """Refuse a candidate the audit workflow could not read, and publish nothing."""

    return Preparation(
        unreadable_artifact(report, display_path(publication.output), assessed),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
    )


def artifact_collided(report: Report, inspection: Inspection, collision: Collision) -> Preparation:
    """Refuse rather than replace a published Ready Artifact holding different bytes.

    A Ready Artifact is immutable, and the hash-suffixed name is the last name available, so a
    clash here is genuinely two different books competing for one path. Overwriting one would
    destroy evidence a Delivery Record may already reference; naming both digests lets the
    clash be seen instead.
    """

    return Preparation(
        replace_refusal(
            report,
            boundary="ready-artifact-collision",
            stage=ARTIFACT_STAGE,
            summary=(
                "a different Ready Artifact already holds this name: "
                f"{display_path(collision.path)}"
            ),
            fact=collision.facts(),
        ),
        inspection.document,
        inspection.baseline,
        inspection.extraction,
        retains_evidence=True,
    )

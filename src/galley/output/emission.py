"""Sequence every side effect one command owns, and publish the artifact last of all.

Report output and artifact publication are different obligations: one describes the run, the
other makes a book visible. This module owns their ordering — input protection first over every
owned destination, evidence before the Report, the artifact only once every other output is
complete — so a refusal at any point leaves the artifact discarded and unpublished.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from galley.outcomes import ExitCode
from galley.output.evidence import STAGE as EVIDENCE_STAGE
from galley.output.evidence import EvidenceBundle, discard_evidence, publish_evidence
from galley.output.policy import (
    ReportEmission,
    apply_report_output_policy,
    internal_error_report,
)
from galley.output.publication import ARTIFACT_STAGE, Publication, discard, publish
from galley.report.envelope import Report, ReportRun, finish_report


class OwnedOutput(Protocol):
    """Anything that names every path it would write, so each can be protected before any is."""

    @property
    def destinations(self) -> list[Path]: ...


def emit_outputs(
    report: Report,
    *,
    source: Path | None,
    additional_inputs: Sequence[Path] = (),
    report_out: Path | None,
    overwrite: bool,
    run: ReportRun,
    evidence: EvidenceBundle | None = None,
    artifact: Publication | None = None,
) -> ReportEmission:
    """Apply report-output policy, then publish the evidence and artifact the run completed.

    The order is the whole point. Every owned destination is protected from the inputs first;
    the evidence is written next, into a hidden staging directory where it is staged at all; the
    Report lands last inside that bundle; and only then are the bundle and the artifact each
    made visible in one rename. A reader therefore never sees a half-written bundle, never sees
    a half-written book, and never sees a Ready Artifact whose evidence is not already complete.
    """

    protected = _owned_by(artifact, ARTIFACT_STAGE)
    emission = apply_report_output_policy(
        report,
        source=source,
        additional_inputs=additional_inputs,
        output=report_out,
        overwrite=overwrite,
        run=run,
        evidence=evidence,
        protected=protected,
    )
    if emission.exit_code != ExitCode.COMPLETED:
        _discard(evidence, artifact)
        return emission
    try:
        publish_evidence(evidence)
    except OSError as error:
        _discard(evidence, artifact)
        refusal = internal_error_report(
            emission.report,
            evidence.directory if evidence is not None else Path(),
            error,
            operation="publish-evidence",
            stage=EVIDENCE_STAGE,
        )
        return ReportEmission(finish_report(refusal, run), ExitCode.INTERNAL_ERROR)
    if artifact is None:
        return emission
    try:
        publish(artifact)
    except OSError as error:
        discard(artifact)
        refusal = internal_error_report(
            emission.report,
            artifact.output,
            error,
            operation="publish-artifact",
            stage=ARTIFACT_STAGE,
        )
        return ReportEmission(finish_report(refusal, run), ExitCode.INTERNAL_ERROR)
    return emission


def _discard(evidence: EvidenceBundle | None, artifact: Publication | None) -> None:
    """Leave nothing behind: neither a staged bundle nor a staged book a refusal will not use."""

    discard_evidence(evidence)
    if artifact is not None:
        discard(artifact)


def _owned_by(output: OwnedOutput | None, stage: str) -> list[tuple[Path, str]]:
    return [] if output is None else [(path, stage) for path in output.destinations]

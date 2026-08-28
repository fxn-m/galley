"""Localise one Markdown source's remote images into a Repair Set the ordinary path prepares.

The order is the whole discipline. Classification and the evidence directory are settled first,
because both are free and a run that cannot write must not fetch anything. The source is read
once, exactly as `inspect` reads it. Only then is the network touched — once per distinct
locator, under the localisation network bounds — and the first reference that fails ends the run with nothing
written, because half a Repair Set is worse than none: the half that exists looks finished.

What comes out is not a special input. It is the three Repair Inputs an agent-assisted `prepare`
already accepts, with the Canonical Document's image `src` values pointing at bytes on this
machine.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from galley.documents import CommandDocument
from galley.json_reading import mapping, text
from galley.localisation.records import Retrieval, localisation_record, refused
from galley.localisation.references import (
    Reference,
    Unlocalisable,
    localised_document,
    remote_references,
)
from galley.localisation.refusals import LocalisationRefusal
from galley.localisation.repair_set import RepairSet, unusable_directory, write_repair_set
from galley.localisation.retrieval import retrieval, unretrieved
from galley.locations import display_path
from galley.profile.loading import list_profiles
from galley.report.envelope import Report, ReportRun, finish_report
from galley.sources import MARKDOWN, accepted_routes, classify
from galley.tools.fetching import PUBLIC_ONLY, Addresses
from galley.workflows.inspect import read_markdown, source_digest
from galley.workflows.parsed import projected

REFUSED = "refused"


def unknown_profile_record(requested: str, run: ReportRun) -> CommandDocument:
    """Refuse an unknown Device Profile before a source is read, naming the profiles that exist."""

    return refused(
        localisation_record(run, requested=requested),
        LocalisationRefusal(
            boundary="unknown-profile",
            stage="profile-resolution",
            summary=f"unknown Device Profile: {requested}",
            fact={
                "requested": requested,
                "known_profiles": [str(profile["id"]) for profile in list_profiles()],
            },
        ),
    )


@dataclass
class _Localising:
    """One localisation as it stands: what was asked for, and what it has settled so far.

    Every step of the run needs the same five things the caller named and the same growing list
    of what has been retrieved, and every step can end in a document. Holding them together is
    what lets each step below take one argument and state the run in one line.
    """

    profile: dict[str, object]
    source: Path
    evidence: Path
    overwrite: bool
    permitted: Addresses
    run: ReportRun
    digest: str | None = None
    retrievals: list[Retrieval] = field(default_factory=list[Retrieval])

    def record(
        self, repair_set: dict[str, object] | None = None, directory: Path | None = None
    ) -> CommandDocument:
        """State this run as it stands, so a refusal keeps what it had already established.

        A refusal names no Repair Set and no directory, because it wrote neither.
        """

        return localisation_record(
            self.run,
            requested=str(self.profile["id"]),
            profile=self.profile,
            source=self.source,
            source_digest=self.digest,
            evidence=repair_set,
            retrievals=tuple(self.retrievals),
            directory=directory,
        )


def localise_source(
    profile: dict[str, object],
    source: str,
    *,
    evidence: Path,
    overwrite: bool,
    permitted: Addresses = PUBLIC_ONLY,
    run: ReportRun,
) -> CommandDocument:
    """Retrieve one Markdown source's remote images into `evidence`, or say why it stopped."""

    kind = classify(source)
    if kind.id != MARKDOWN:
        return refused(
            localisation_record(run, requested=str(profile["id"]), profile=profile),
            LocalisationRefusal(
                boundary="unsupported-source-kind",
                stage="source-classification",
                summary=(
                    "localise reads a Markdown source, whose images resolve against nothing "
                    f"remote until it says so: {kind.statement} ({source})"
                ),
                fact={
                    "accepted": [MARKDOWN],
                    "kind": kind.id,
                    "routes": accepted_routes(),
                    "source": source,
                },
            ),
        )
    localising = _Localising(profile, Path(source), evidence, overwrite, permitted, run)
    unusable = unusable_directory(evidence, localising.source, overwrite=overwrite)
    if unusable is not None:
        return refused(localising.record(), unusable)
    return _read(localising)


def _read(localising: _Localising) -> CommandDocument:
    """Read the source exactly as `inspect` reads it, then select what has to be retrieved."""

    inspection = projected(
        localising.profile,
        read_markdown(
            localising.profile, localising.source, run=localising.run, command="localise"
        ),
    )
    localising.digest = source_digest(inspection.report)
    if inspection.document is None or inspection.report["outcome"] == REFUSED:
        return refused(localising.record(), _inherited(inspection.report))
    selected = remote_references(inspection.document)
    if isinstance(selected, Unlocalisable):
        return refused(
            localising.record(),
            LocalisationRefusal(
                boundary="unlocalisable-reference",
                stage="image-selection",
                summary=f"cannot localise a reference this source carries: {selected.detail}",
                fact={
                    "detail": selected.detail,
                    "locator": selected.locator,
                    "reason": selected.reason,
                },
            ),
        )
    if not selected:
        return refused(
            localising.record(),
            LocalisationRefusal(
                boundary="no-remote-images",
                stage="image-selection",
                summary=f"the source references no remote image: {display_path(localising.source)}",
                fact={"path": display_path(localising.source)},
            ),
        )
    return _retrieved(
        localising,
        selected,
        inspection=inspection.report,
        document=inspection.document,
        baseline=inspection.baseline or "",
    )


def _retrieved(
    localising: _Localising,
    selected: list[Reference],
    *,
    inspection: Report,
    document: dict[str, object],
    baseline: str,
) -> CommandDocument:
    """Retrieve each distinct locator once, and stop at the first one that does not arrive."""

    for reference in selected:
        attempt = retrieval(reference, localising.permitted)
        localising.retrievals.append(attempt)
        if not attempt.retrieved:
            return refused(localising.record(), unretrieved(attempt))
    repair = _repair_set(localising, inspection, document, baseline)
    unwritten = write_repair_set(repair, overwrite=localising.overwrite)
    if unwritten is not None:
        return refused(localising.record(), unwritten)
    return localising.record(repair.facts(), localising.evidence)


def _repair_set(
    localising: _Localising, inspection: Report, document: dict[str, object], baseline: str
) -> RepairSet:
    """Assemble the Repair Inputs and the images, each locator pointing at its own bytes."""

    retrieved = [attempt for attempt in localising.retrievals if attempt.retrieved]
    return RepairSet(
        directory=localising.evidence,
        report=finish_report(inspection, localising.run),
        document=localised_document(
            document,
            {attempt.reference.locator: attempt.path(localising.evidence) for attempt in retrieved},
        ),
        baseline=baseline,
        images={str(attempt.name): cast(bytes, attempt.data) for attempt in retrieved},
    )


def _inherited(report: Report) -> LocalisationRefusal:
    """Restate the boundary the source read stopped at, rather than inventing one of its own."""

    stated = mapping(report.get("refusal"))
    return LocalisationRefusal(
        boundary=text(stated.get("boundary")) or "unreadable-source",
        stage=text(stated.get("stage")) or "source-acquisition",
        summary=text(stated.get("summary")) or "the source could not be read",
        fact=mapping(stated.get("fact")),
    )

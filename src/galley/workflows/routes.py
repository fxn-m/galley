"""Decide one named source's route before reading it, and refuse the kinds 0.1.0 does not read.

Both workflows make the same decision the same way: classify the locator, refuse a kind 0.1.0
does not read, and only then touch the source. This module is that decision's single home, so
`inspect` and `prepare` can only ever disagree about what follows classification, never about
classification itself.
"""

from galley.profile.loading import list_profiles
from galley.report.envelope import (
    Report,
    ReportCommand,
    ReportRun,
    completed_report,
    replace_refusal,
    unknown_profile_report,
)
from galley.sources import SourceKind, accepted_routes, classify

CLASSIFICATION_STAGE = "source-classification"


def routed_source(
    profile: dict[str, object], source: str, *, run: ReportRun, command: ReportCommand
) -> SourceKind | Report:
    """Classify one named source, or return the refusal Report for a kind 0.1.0 does not read."""

    kind = classify(source)
    if not kind.supported:
        return unsupported_report(profile, source, kind, run=run, command=command)
    return kind


def unknown_profile(command: ReportCommand, requested: str, *, run: ReportRun) -> Report:
    """Refuse an unknown Device Profile, naming the profiles that exist."""

    known = [str(profile["id"]) for profile in list_profiles()]
    return unknown_profile_report(command, requested, known, run=run)


def unsupported_report(
    profile: dict[str, object],
    source: str,
    kind: SourceKind,
    *,
    run: ReportRun,
    command: ReportCommand,
) -> Report:
    """Refuse a source kind 0.1.0 does not read, naming the routes it does.

    The Device Profile resolved; only the source did not. Its facts stay in the Report so an
    agent can tell this refusal from an unknown profile without reading the boundary.
    """

    return replace_refusal(
        completed_report(command, profile, run=run),
        boundary="unsupported-source-kind",
        stage=CLASSIFICATION_STAGE,
        summary=f"unsupported source kind: {kind.statement} ({source})",
        fact={
            "accepted": accepted_routes(),
            "kind": kind.id,
            "reason": kind.reason,
            "source": source,
        },
    )

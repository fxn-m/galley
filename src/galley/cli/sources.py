"""Inspect one source, localise its images, and audit one existing artifact from the command line."""

from pathlib import Path
from typing import Annotated

import typer

from galley.cli.emission import emit, require_destination
from galley.cli.localise import localise_images
from galley.cli.prepare import prepare_artifact
from galley.output.evidence import EvidenceBundle
from galley.profile.loading import ProfileError, load_profile
from galley.report.envelope import ReportRun
from galley.sources import local_path
from galley.workflows.audit import audit_report
from galley.workflows.inspect import Inspection, inspect_source as run_inspection
from galley.workflows.routes import unknown_profile


def register(app: typer.Typer) -> None:
    """Attach the source and artifact commands to the Galley application."""

    _ = app.command("inspect")(inspect_source)
    _ = app.command("prepare")(prepare_artifact)
    _ = app.command("localise")(localise_images)
    _ = app.command("audit")(audit_artifact)


def inspect_source(
    source: Annotated[str, typer.Argument(help="Markdown path or Article-Like Page URL.")],
    profile_id: Annotated[str, typer.Option("--profile", help="Device Profile identifier.")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit the canonical Report.")] = False,
    report_out: Annotated[
        Path | None, typer.Option("--report-out", help="Write the canonical Report to a file.")
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace command-owned output files.")
    ] = False,
    evidence_dir: Annotated[
        Path | None,
        typer.Option("--evidence-dir", help="Retain the Report, Canonical Document and baseline."),
    ] = None,
) -> None:
    """Inspect a source without preparing an artifact."""

    require_destination(report_out, evidence_dir, overwrite=overwrite)
    run = ReportRun.start()
    try:
        profile = load_profile(profile_id)
    except ProfileError:
        inspection = Inspection(unknown_profile("inspect", profile_id, run=run))
    else:
        inspection = run_inspection(profile, source, run=run)
    evidence = (
        None
        if evidence_dir is None
        else EvidenceBundle(
            evidence_dir, inspection.document, inspection.baseline, inspection.extraction
        )
    )
    emit(
        inspection.report,
        local_path(source),
        report_out,
        as_json=as_json,
        overwrite=overwrite,
        run=run,
        evidence=evidence,
    )


def audit_artifact(
    epub: Annotated[Path, typer.Argument(help="EPUB artifact to audit.")],
    profile_id: Annotated[str, typer.Option("--profile", help="Device Profile identifier.")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit the canonical Report.")] = False,
    report_out: Annotated[
        Path | None, typer.Option("--report-out", help="Write the canonical Report to a file.")
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace command-owned output files.")
    ] = False,
) -> None:
    """Audit an existing EPUB read-only against a Device Profile."""

    require_destination(report_out, overwrite=overwrite)
    run = ReportRun.start()
    try:
        profile = load_profile(profile_id)
    except ProfileError:
        report = unknown_profile("audit", profile_id, run=run)
    else:
        report = audit_report(profile, epub, run=run)
    emit(report, epub, report_out, as_json=as_json, overwrite=overwrite, run=run)

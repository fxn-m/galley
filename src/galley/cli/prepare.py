"""Prepare one source into an audited EPUB3, to a named output or as a Ready Artifact.

The two modes differ in exactly two places and nowhere else: where the book is published, and
where its evidence is kept. Everything between — the source route, the whole preparation,
Compatibility, preservation and audit contract — is the same code, so `--ready` cannot become a
second, weaker pipeline.
"""

from pathlib import Path
from typing import Annotated, cast

import typer

from galley.cli.emission import emit
from galley.output.destinations import artifact_destinations, evidence_directory
from galley.output.evidence import EvidenceBundle
from galley.output.naming import ReadyOutput
from galley.output.publication import Destination, ExplicitOutput
from galley.profile.loading import ProfileError, load_profile
from galley.report.envelope import ReportRun
from galley.sources import local_path
from galley.workflows.prepare import Preparation, prepare_source
from galley.workflows.repair_inputs import IncompleteRepair, command_inputs, repair_inputs
from galley.workflows.routes import unknown_profile
from galley.workspace.ready import ReadyWorkspace, evidence_key, provenance, ready_workspace

COMPLETED = "completed"


def prepare_artifact(
    source: Annotated[str, typer.Argument(help="Markdown path or Article-Like Page URL.")],
    profile_id: Annotated[str, typer.Option("--profile", help="Device Profile identifier.")],
    output: Annotated[
        Path | None, typer.Option("--output", help="EPUB artifact to publish.")
    ] = None,
    ready: Annotated[
        bool, typer.Option("--ready", help="Publish an immutable Ready Artifact in the Workspace.")
    ] = False,
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", help="Galley Workspace to publish the Ready Artifact into."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Emit the canonical Report.")] = False,
    report_out: Annotated[
        Path | None, typer.Option("--report-out", help="Write the canonical Report to a file.")
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace command-owned output files.")
    ] = False,
    evidence_dir: Annotated[
        Path | None,
        typer.Option("--evidence-dir", help="Place the companion evidence directory."),
    ] = None,
    expected_missing_tokens: Annotated[
        Path | None,
        typer.Option("--expected-missing-tokens", help="Declare allowed missing token counts."),
    ] = None,
    expected_source_hash: Annotated[
        str | None,
        typer.Option("--expected-source-hash", help="The source hash an Inbox Check observed."),
    ] = None,
    inspection_report: Annotated[
        Path | None,
        typer.Option("--inspection-report", help="The Report the repaired document came from."),
    ] = None,
    canonical_document: Annotated[
        Path | None,
        typer.Option("--canonical-document", help="An agent-repaired Canonical Document."),
    ] = None,
    preservation_baseline: Annotated[
        Path | None,
        typer.Option("--preservation-baseline", help="The baseline retained before the repair."),
    ] = None,
) -> None:
    """Prepare a source into an audited EPUB3 and publish it with its evidence."""

    _require_one_mode(output, ready=ready, overwrite=overwrite, evidence_dir=evidence_dir)
    try:
        repair = repair_inputs(inspection_report, canonical_document, preservation_baseline)
    except IncompleteRepair as error:
        raise typer.BadParameter(str(error), param_hint="--inspection-report") from error
    run = ReportRun.start()
    home = ready_workspace(workspace) if ready else None
    destination: Destination = (
        ReadyOutput(home.artifacts) if home is not None else ExplicitOutput(cast(Path, output))
    )
    evidence = None if ready else evidence_directory(cast(Path, output), evidence_dir)
    try:
        profile = load_profile(profile_id)
    except ProfileError:
        preparation = Preparation(unknown_profile("prepare", profile_id, run=run))
    else:
        preparation = prepare_source(
            profile,
            source,
            destination=destination,
            protected=artifact_destinations(output),
            evidence=evidence,
            overwrite=overwrite,
            expected_missing_tokens=expected_missing_tokens,
            expected_source_hash=expected_source_hash,
            repair=repair,
            run=run,
        )
    emit(
        preparation.report,
        local_path(source),
        report_out,
        as_json=as_json,
        overwrite=overwrite,
        run=run,
        evidence=_bundle(preparation, home, evidence),
        artifact=preparation.publication,
        additional_inputs=command_inputs(expected_missing_tokens, repair),
    )


def _require_one_mode(
    output: Path | None, *, ready: bool, overwrite: bool, evidence_dir: Path | None
) -> None:
    """Accept exactly one destination mode, and refuse the options the other one owns."""

    if (output is None) == (not ready):
        raise typer.BadParameter(
            "requires exactly one of --output or --ready", param_hint="--ready"
        )
    if not ready:
        return
    if overwrite:
        raise typer.BadParameter(
            "a Ready Artifact is immutable and is never replaced", param_hint="--overwrite"
        )
    if evidence_dir is not None:
        raise typer.BadParameter(
            "Ready publication owns where its evidence is kept", param_hint="--evidence-dir"
        )


def _bundle(
    preparation: Preparation, home: ReadyWorkspace | None, evidence: Path | None
) -> EvidenceBundle | None:
    """Place this run's evidence where its outcome says it belongs.

    An explicit output keeps its companion directory beside the EPUB. A Ready publication keys
    its bundle by source provenance instead, so two sources that build identical bytes each keep
    their own immutable Report; a refused attempt goes to Galley-owned work storage, which the
    next attempt replaces, because a failure is the latest attempt rather than a published fact.
    """

    if home is None:
        if evidence is None or not preparation.retains_evidence:
            return None
        return _evidence(preparation, evidence)
    located, digest = provenance(preparation.report)
    if not located:
        return None
    key = evidence_key(located, digest)
    if preparation.report["outcome"] == COMPLETED:
        return _evidence(preparation, home.evidence(key), staged=home.staged_evidence(key))
    return _evidence(preparation, home.attempt(key), replaceable=True)


def _evidence(
    preparation: Preparation,
    directory: Path,
    *,
    staged: Path | None = None,
    replaceable: bool = False,
) -> EvidenceBundle:
    return EvidenceBundle(
        directory,
        preparation.document,
        preparation.baseline,
        preparation.extraction,
        preparation.previews,
        staged=staged,
        replaceable=replaceable,
    )

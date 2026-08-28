"""Emit one finished Report and every side effect the command that produced it owns."""

from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import typer

from galley.output.emission import emit_outputs
from galley.output.evidence import EvidenceBundle
from galley.output.publication import Publication
from galley.report.envelope import Report, ReportRun, report_json
from galley.report.render import render_report


def require_destination(
    report_out: Path | None, evidence_dir: Path | None = None, *, overwrite: bool
) -> None:
    """Reject `--overwrite` where the command owns no output it could replace."""

    if overwrite and report_out is None and evidence_dir is None:
        raise typer.BadParameter(
            "requires --report-out or --evidence-dir", param_hint="--overwrite"
        )


def emit(
    report: Report,
    subject: Path | None,
    report_out: Path | None,
    *,
    as_json: bool,
    overwrite: bool,
    run: ReportRun,
    evidence: EvidenceBundle | None = None,
    artifact: Publication | None = None,
    additional_inputs: Sequence[Path] = (),
) -> NoReturn:
    """Write every owned output in the fixed order, then render the same Report to stdout."""

    emission = emit_outputs(
        report,
        source=subject,
        additional_inputs=additional_inputs,
        report_out=report_out,
        overwrite=overwrite,
        run=run,
        evidence=evidence,
        artifact=artifact,
    )
    rendered = report_json(emission.report) if as_json else render_report(emission.report)
    typer.echo(rendered, nl=False)
    raise typer.Exit(emission.exit_code)

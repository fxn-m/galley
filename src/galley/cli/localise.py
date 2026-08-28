"""Retrieve a Markdown source's remote images into a Repair Set, from the command line."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from galley.documents import document_json, emitted
from galley.localisation.render import render_localisation
from galley.localisation.workflow import localise_source, unknown_profile_record
from galley.profile.loading import ProfileError, load_profile
from galley.report.envelope import ReportRun


def localise_images(
    source: Annotated[str, typer.Argument(help="Markdown path whose remote images to retrieve.")],
    profile_id: Annotated[str, typer.Option("--profile", help="Device Profile identifier.")],
    evidence_dir: Annotated[
        Path,
        typer.Option("--evidence-dir", help="Directory to write the Repair Set into."),
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit the versioned command document.")
    ] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing Repair Set.")
    ] = False,
) -> NoReturn:
    """Retrieve the remote images a Markdown source references, once, for an ordinary repair."""

    run = ReportRun.start()
    try:
        profile = load_profile(profile_id)
    except ProfileError:
        document = unknown_profile_record(profile_id, run)
    else:
        document = localise_source(
            profile, source, evidence=evidence_dir, overwrite=overwrite, run=run
        )
    emission = emitted(document, run)
    rendered = (
        document_json(emission.document) if as_json else render_localisation(emission.document)
    )
    typer.echo(rendered, nl=False)
    raise typer.Exit(emission.exit_code)

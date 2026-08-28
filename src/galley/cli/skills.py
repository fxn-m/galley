"""Install and remove Galley's Agent Skills from the command line."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from galley.documents import CommandDocument, document_json, emitted
from galley.installation.install import install_skills
from galley.installation.render import render_installation
from galley.installation.uninstall import uninstall_skills
from galley.report.envelope import ReportRun

skill_app = typer.Typer(help="Install and remove Galley's Agent Skills.")

TARGET_OPTION = typer.Option(
    "--target", help="Skills directory to manage instead of the standard user location."
)
FORCE_OPTION = typer.Option(
    "--force", help="Replace the two Galley skill directories even when they are not Galley's."
)
JSON_OPTION = typer.Option("--json", help="Emit the versioned command document.")


def register(app: typer.Typer) -> None:
    """Attach the skill lifecycle commands to the Galley application."""

    app.add_typer(skill_app, name="skill")


@skill_app.command("install")
def skill_install(
    target: Annotated[Path | None, TARGET_OPTION] = None,
    force: Annotated[bool, FORCE_OPTION] = False,
    as_json: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Install both version-matched Agent Skills into a discoverable target."""

    run = ReportRun.start()
    _emit(install_skills(target, force=force, run=run), run, as_json=as_json)


@skill_app.command("uninstall")
def skill_uninstall(
    target: Annotated[Path | None, TARGET_OPTION] = None,
    as_json: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Remove the files a Galley installation put in the target, and nothing else."""

    run = ReportRun.start()
    _emit(uninstall_skills(target, run=run), run, as_json=as_json)


def _emit(document: CommandDocument, run: ReportRun, *, as_json: bool) -> NoReturn:
    emission = emitted(document, run)
    rendered = (
        document_json(emission.document) if as_json else render_installation(emission.document)
    )
    typer.echo(rendered, nl=False)
    raise typer.Exit(emission.exit_code)

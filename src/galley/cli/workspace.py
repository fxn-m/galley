"""Validate Workspace Configuration and check configured Inboxes from the command line."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from galley.report.envelope import ReportRun
from galley.workspace.check import check_inboxes
from galley.documents import CommandDocument, document_json, emitted
from galley.workspace.render import render_document
from galley.workspace.validate import validate_workspace_configuration

config_app = typer.Typer(help="Validate the visible Workspace Configuration.")
inbox_app = typer.Typer(help="Check the configured Inboxes for supported sources.")

WORKSPACE_OPTION = typer.Option(
    "--workspace", help="Galley Workspace to resolve instead of GALLEY_HOME or the default."
)
JSON_OPTION = typer.Option("--json", help="Emit the versioned command document.")


def register(app: typer.Typer) -> None:
    """Attach the Workspace commands to the Galley application."""

    app.add_typer(config_app, name="config")
    app.add_typer(inbox_app, name="inbox")


@config_app.command("validate")
def config_validate(
    workspace: Annotated[Path | None, WORKSPACE_OPTION] = None,
    as_json: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Report what the Workspace Configuration resolves to, without writing anything."""

    run = ReportRun.start()
    _emit(validate_workspace_configuration(workspace, run=run), run, as_json=as_json)


@inbox_app.command("check")
def inbox_check(
    workspace: Annotated[Path | None, WORKSPACE_OPTION] = None,
    as_json: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Inventory every configured Inbox once, without watching or processing one source."""

    run = ReportRun.start()
    _emit(check_inboxes(workspace, run=run), run, as_json=as_json)


def _emit(document: CommandDocument, run: ReportRun, *, as_json: bool) -> NoReturn:
    emission = emitted(document, run)
    rendered = document_json(emission.document) if as_json else render_document(emission.document)
    typer.echo(rendered, nl=False)
    raise typer.Exit(emission.exit_code)

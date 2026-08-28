"""Probe the configured X4 and plan or perform one Delivery from the command line."""

from math import isfinite
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from galley.delivery.attempt import perform_delivery
from galley.delivery.device import DEFAULT_TIMEOUT_SECONDS, check_device
from galley.delivery.preflight import DeliveryRequest, plan_delivery
from galley.delivery.records import emit_record
from galley.delivery.render import render_delivery_record, render_device_status
from galley.report.envelope import ReportRun
from galley.documents import CommandDocument, document_json, emitted

DELIVERY_TIMEOUT_SECONDS = 30.0

device_app = typer.Typer(help="Inspect the configured CrossPoint device.")

WORKSPACE_OPTION = typer.Option(
    "--workspace", help="Galley Workspace to resolve instead of GALLEY_HOME or the default."
)
HOST_OPTION = typer.Option("--host", help="CrossPoint HOST[:PORT], overriding configuration.")
DESTINATION_OPTION = typer.Option(
    "--destination", help="Absolute CrossPoint folder, overriding configuration."
)
PLAN_OPTION = typer.Option("--plan", help="Read the device and destination without uploading.")
OVERWRITE_OPTION = typer.Option(
    "--overwrite", help="Permit replacing a different file of the same name at the destination."
)
JSON_OPTION = typer.Option("--json", help="Emit the versioned command document.")


def register(app: typer.Typer) -> None:
    """Attach the device and Delivery commands to the Galley application."""

    app.add_typer(device_app, name="device")
    _ = app.command("deliver")(deliver)


@device_app.command("status")
def device_status(
    workspace: Annotated[Path | None, WORKSPACE_OPTION] = None,
    host: Annotated[str | None, HOST_OPTION] = None,
    timeout: Annotated[float, typer.Option("--timeout", help="Status timeout in seconds.")] = (
        DEFAULT_TIMEOUT_SECONDS
    ),
    as_json: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Report what the configured CrossPoint device is, without reading or writing a book."""

    run = ReportRun.start()
    document = check_device(workspace, host, _timeout(timeout), run=run)
    emission = emitted(document, run)
    _echo(document_json(emission.document) if as_json else render_device_status(emission.document))
    raise typer.Exit(emission.exit_code)


def deliver(
    ready: Annotated[Path, typer.Argument(help="Ready Artifact inside the Workspace.")],
    workspace: Annotated[Path | None, WORKSPACE_OPTION] = None,
    host: Annotated[str | None, HOST_OPTION] = None,
    destination: Annotated[str | None, DESTINATION_OPTION] = None,
    plan: Annotated[bool, PLAN_OPTION] = False,
    overwrite: Annotated[bool, OVERWRITE_OPTION] = False,
    timeout: Annotated[
        float, typer.Option("--timeout", help="Plan and Delivery timeout in seconds.")
    ] = DELIVERY_TIMEOUT_SECONDS,
    as_json: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Plan or perform one Delivery of one Ready Artifact, persisting an immutable record.

    Invoking this command is itself the authorization to write: there is no terminal prompt, so
    the approval an Agent Skill obtains from a human stays outside the CLI where it belongs.
    """

    run = ReportRun.start()
    request = DeliveryRequest(
        artifact=ready,
        workspace=workspace,
        host=host,
        destination=destination,
        timeout_seconds=_timeout(timeout),
        overwrite=overwrite,
    )
    attempted = plan_delivery(request, run) if plan else perform_delivery(request, run)
    _record(attempted, run, as_json=as_json)


def _record(document: CommandDocument, run: ReportRun, *, as_json: bool) -> NoReturn:
    """Persist the record before rendering it, so an outcome is never reported unrecorded.

    A Workspace that could not hold a record has already refused, before the device was
    touched. If the write fails anyway the outcome stands: reporting a confirmed Delivery as
    refused would claim nothing was written about a book that is on the device, so the loss of
    the record is reported on stderr instead of being folded into the Delivery's own verdict.
    """

    emission = emit_record(document, run)
    if emission.unwritten is not None:
        typer.echo(emission.unwritten.summary, err=True)
    _echo(
        document_json(emission.document) if as_json else render_delivery_record(emission.document)
    )
    raise typer.Exit(emission.exit_code)


def _timeout(seconds: float) -> float:
    """Hold every timeout to a finite positive number, so no invocation can wait forever."""

    if not isfinite(seconds) or seconds <= 0:
        raise typer.BadParameter(
            "must be a finite number of seconds above zero", param_hint="--timeout"
        )
    return seconds


def _echo(rendered: str) -> None:
    typer.echo(rendered, nl=False)

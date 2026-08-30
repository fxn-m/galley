"""Do everything a Delivery does before it writes, and decide the one action it would take.

Planning and Delivery share this whole path deliberately: a plan is worth reading only if it is
the same work the transfer will do, and a retry is only idempotent because it starts here again
rather than remembering what happened last time. Nothing in this module writes to the
device, and the upload endpoint is not so much as named.

The order is chosen so the cheapest and most consequential refusals come first. Where to write
is settled from configuration, then the book is proved to be a Ready Artifact of this Workspace
using only local reads, and only then is a packet sent.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from galley.delivery.artifacts import Deliverable, deliverable
from galley.delivery.connection import resolve_connection
from galley.delivery.crosspoint import (
    CrossPointClient,
    LISTING_STAGE,
    Listing,
    RemoteEntry,
)
from galley.delivery.probing import probe
from galley.delivery.records import (
    PLAN,
    Mode,
    opened_record,
    prepare_storage,
    with_action,
    with_connection,
    with_destination,
)
from galley.delivery.refusals import DeliveryRefusal
from galley.report.envelope import ReportRun
from galley.documents import CommandDocument, with_facts, with_refusal
from galley.workspace.ready import ReadyWorkspace
from galley.workspace.resolution import Workspace, resolve_workspace

Action = Literal["upload-new", "already-delivered", "overwrite"]

UPLOAD_NEW: Action = "upload-new"
# Typed as the literal rather than as `Action`, because this exact string is also the Delivery
# outcome an already-present artifact produces, and one spelling is better than two.
ALREADY_DELIVERED: Literal["already-delivered"] = "already-delivered"
OVERWRITE: Action = "overwrite"


@dataclass(frozen=True)
class DeliveryRequest:
    """Everything one `deliver` invocation was asked to do, before anything is resolved."""

    artifact: Path
    workspace: Path | None = None
    host: str | None = None
    destination: str | None = None
    timeout_seconds: float = 30.0
    overwrite: bool = False


@dataclass(frozen=True)
class Preflight:
    """The record so far, and the decision a Delivery would act on when one was reached."""

    document: CommandDocument
    workspace: Workspace
    client: CrossPointClient | None = None
    book: Deliverable | None = None
    destination: str = ""
    action: Action | None = None


def preflight(mode: Mode, request: DeliveryRequest, run: ReportRun) -> Preflight:
    """Resolve, verify and probe everything one Delivery rests on, and decide its action."""

    workspace = resolve_workspace(request.workspace)
    document = opened_record(mode, run, workspace, overwrite=request.overwrite)
    storage = prepare_storage(workspace)
    if isinstance(storage, DeliveryRefusal):
        return Preflight(with_refusal(document, storage), workspace)
    connection = resolve_connection(workspace, request.host, request.destination)
    if isinstance(connection, DeliveryRefusal):
        return Preflight(with_refusal(document, connection), workspace)
    document = with_connection(document, connection)
    destination = connection.destination.value

    book = deliverable(ReadyWorkspace(workspace), request.artifact)
    if isinstance(book, DeliveryRefusal):
        return Preflight(with_refusal(document, book), workspace, destination=destination)
    document = with_destination(
        with_facts(document, {"artifact": book.facts()}),
        remote_path=remote_path(destination, book),
    )

    probed = probe(document, connection.host.value, request.timeout_seconds)
    document = probed.document
    if not probed.reached or probed.client is None:
        return Preflight(
            document,
            workspace,
            client=probed.client,
            book=book,
            destination=destination,
        )
    return _listed(
        document,
        workspace,
        probed.client,
        book,
        destination,
        request.overwrite,
    )


def remote_path(destination: str, book: Deliverable) -> str:
    """Name where on the device this artifact would sit, in the device's own spelling."""

    prefix = "" if destination == "/" else destination
    return f"{prefix}/{book.path.name}"


def _listed(
    document: CommandDocument,
    workspace: Workspace,
    client: CrossPointClient,
    book: Deliverable,
    destination: str,
    overwrite: bool,
) -> Preflight:
    """Read the destination once, and turn what is already there into one exact action."""

    listing = client.listing(destination).value
    if isinstance(listing, DeliveryRefusal):
        return Preflight(
            with_refusal(document, listing),
            workspace,
            client=client,
            book=book,
            destination=destination,
        )
    document = with_destination(document, preflight=listing.facts(book.path.name))
    decided = _action(listing, book, destination, overwrite=overwrite)
    if isinstance(decided, DeliveryRefusal):
        return Preflight(
            with_refusal(document, decided),
            workspace,
            client=client,
            book=book,
            destination=destination,
        )
    return Preflight(
        with_action(document, planned=decided),
        workspace,
        client=client,
        book=book,
        destination=destination,
        action=decided,
    )


def _action(
    listing: Listing, book: Deliverable, destination: str, *, overwrite: bool
) -> Action | DeliveryRefusal:
    """Decide between a new upload, an idempotent success, a replacement and a refusal.

    Identity at the destination is filename plus byte size, which is all CrossPoint's listing
    offers. Same name and same size is the artifact already being there, so it is success with
    nothing sent. Same name and a different size is a genuine collision: two different books
    cannot both be that filename, and choosing between them is the user's call, not Galley's.
    """

    existing = listing.matching(book.path.name)
    if existing is None:
        return UPLOAD_NEW
    if existing.byte_size == book.byte_size:
        return ALREADY_DELIVERED
    if overwrite:
        return OVERWRITE
    return _collision(existing, book, destination)


def _collision(existing: RemoteEntry, book: Deliverable, destination: str) -> DeliveryRefusal:
    return DeliveryRefusal(
        boundary="destination-collision",
        stage=LISTING_STAGE,
        summary=(
            f"{destination} already holds a different {existing.name} "
            f"({existing.byte_size} bytes there, {book.byte_size} bytes here) "
            "and overwrite was not requested"
        ),
        fact={
            "destination": destination,
            "name": existing.name,
            "remote_byte_size": existing.byte_size,
            "local_byte_size": book.byte_size,
        },
    )


def plan_delivery(request: DeliveryRequest, run: ReportRun) -> CommandDocument:
    """Plan one Delivery: the whole preflight, stopping before the one request that writes."""

    return preflight(PLAN, request, run).document

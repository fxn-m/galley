"""Perform one approved Delivery, and report success only from the device's own listing.

An HTTP response alone is not evidence that a book arrived. An attempt therefore consists of the
same preflight a plan performs, one multipart upload, then a
fresh destination listing — and `delivered` is claimed only when that listing shows the exact
filename at the exact byte size. Anything else, once the upload request has been made, is an
Unconfirmed Delivery: the device may or may not have retained the bytes, and Galley does not
guess which. The Ready Artifact is untouched throughout, so a retry simply starts again.
"""

from galley.delivery.artifacts import Deliverable
from galley.delivery.crosspoint import Listing, destination_listing
from galley.delivery.preflight import ALREADY_DELIVERED, DeliveryRequest, Preflight, preflight
from galley.delivery.records import DELIVER, with_action, with_destination
from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget
from galley.delivery.upload import Transfer, upload
from galley.report.envelope import ReportRun
from galley.documents import UNCONFIRMED, CommandDocument, Outcome, with_outcome, with_refusal

CONFIRMATION_STAGE = "delivery-confirmation"

DELIVERED: Outcome = "delivered"


def perform_delivery(request: DeliveryRequest, run: ReportRun) -> CommandDocument:
    """Deliver one Ready Artifact, or say exactly how far the attempt got."""

    prepared = preflight(DELIVER, request, run)
    if prepared.action is None or prepared.book is None or prepared.target is None:
        return prepared.document
    if prepared.action == ALREADY_DELIVERED:
        return with_outcome(prepared.document, ALREADY_DELIVERED)
    return _confirmed(prepared, prepared.target, prepared.book)


def _confirmed(prepared: Preflight, target: DeliveryTarget, book: Deliverable) -> CommandDocument:
    """Upload once, then ask the device what it now holds and believe only that."""

    transfer = upload(target, prepared.destination, book.path)
    document = with_action(prepared.document, upload_began=True, transport_status=transfer.status)
    listing = destination_listing(target, prepared.destination)
    if isinstance(listing, DeliveryRefusal):
        return _unconfirmed(document, book, transfer, listing.summary)
    document = with_destination(document, postflight=listing.facts(book.path.name))
    return _judged(document, book, transfer, listing)


def _judged(
    document: CommandDocument, book: Deliverable, transfer: Transfer, listing: Listing
) -> CommandDocument:
    """Turn the fresh listing into the one outcome it supports, and no stronger one."""

    entry = listing.matching(book.path.name)
    if entry is None:
        return _unconfirmed(document, book, transfer, "the destination does not list the book")
    if entry.byte_size != book.byte_size:
        return _unconfirmed(
            document,
            book,
            transfer,
            f"the destination lists {entry.name} at {entry.byte_size} bytes, not {book.byte_size}",
        )
    return with_outcome(with_action(document, confirmation=entry.facts()), DELIVERED)


def _unconfirmed(
    document: CommandDocument, book: Deliverable, transfer: Transfer, reason: str
) -> CommandDocument:
    """Record an Unconfirmed Delivery, stating what is known and refusing to infer the rest."""

    detail = f"; {transfer.detail}" if transfer.detail else ""
    unconfirmed = with_refusal(
        document,
        DeliveryRefusal(
            boundary="unconfirmed-delivery",
            stage=CONFIRMATION_STAGE,
            summary=(
                f"the upload was sent but {book.path.name} could not be confirmed at the "
                f"destination: {reason}{detail}. The Ready Artifact is unchanged and this "
                "Delivery can be retried."
            ),
            fact={
                "name": book.path.name,
                "byte_size": book.byte_size,
                "transport_status": transfer.status,
                "reason": reason,
            },
        ),
    )
    return with_outcome(unconfirmed, UNCONFIRMED)

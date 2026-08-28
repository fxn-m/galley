"""Build and persist the immutable Delivery Record every plan and every attempt leaves behind.

A Delivery Record is the command document `deliver` emits — not a second object beside one. The
spec's field list and the command-document envelope are the same list, so splitting them would
have meant two run identities, two outcomes and two refusals describing one event. What is its
own is the outcome vocabulary: `planned`, `delivered`, `already-delivered`, `refused` and
`unconfirmed` are Delivery facts, and never the preparation Report's completed/refused pair.

Records accumulate. Every plan and every attempt writes a separate file, nothing is ever
replaced, and Galley performs no cleanup — so the collection is flat and each record
is named by its own id, which begins with its UTC start so a directory listing reads in the
order the attempts happened.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from galley.delivery.connection import ResolvedConnection
from galley.delivery.refusals import DeliveryRefusal
from galley.json_reading import mapping
from galley.locations import display_path
from galley.report.envelope import ReportRun
from galley.documents import (
    DELIVERY_RECORD_SCHEMA,
    CommandDocument,
    command_document,
    document_json,
    emitted,
    with_facts,
)
from galley.outcomes import ExitCode
from galley.workspace.layout import delivery_directory, directory_state
from galley.workspace.resolution import Workspace

COMMAND = "deliver"
STORAGE_STAGE = "delivery-record-storage"
RECORD_SUFFIX = ".json"
STAGED_PREFIX = "."
STAGED_SUFFIX = ".galley-candidate"
IDENTIFIER_LENGTH = 12

Mode = Literal["plan", "deliver"]

PLAN: Mode = "plan"
DELIVER: Mode = "deliver"


@dataclass(frozen=True)
class RecordEmission:
    """One finished Delivery Record: its outcome, and where it was written if it was."""

    document: CommandDocument
    exit_code: ExitCode
    stored: Path | None
    unwritten: DeliveryRefusal | None


@dataclass(frozen=True)
class Storage:
    """Where one Workspace keeps its Delivery Records, and how a new one is named."""

    workspace: Path

    @property
    def collection(self) -> Path:
        """Name the flat collection every plan and attempt adds one immutable record to."""

        return delivery_directory(self.workspace)

    def record(self, identifier: str) -> Path:
        """Name one record by its own id, which sorts records into the order they happened."""

        return self.collection / f"{identifier}{RECORD_SUFFIX}"

    def staged(self, identifier: str) -> Path:
        """Name the hidden sibling a record is written to before it becomes visible."""

        return self.collection / f"{STAGED_PREFIX}{identifier}{RECORD_SUFFIX}{STAGED_SUFFIX}"


def record_identifier(started_at: datetime) -> str:
    """Name one record uniquely, starting with the moment its command began."""

    return f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:IDENTIFIER_LENGTH]}"


def opened_record(
    mode: Mode, run: ReportRun, workspace: Workspace, *, overwrite: bool
) -> CommandDocument:
    """Open one Delivery Record holding everything known before configuration is even read.

    A record exists from the first boundary onwards, because a refusal is as much a Delivery
    fact as a transfer is: a run that never learned where to write still has to say so somewhere
    a reader can find it.
    """

    return command_document(
        COMMAND,
        DELIVERY_RECORD_SCHEMA,
        run,
        {
            "record_id": record_identifier(run.started_at),
            "mode": mode,
            "workspace": workspace.facts(),
            "configuration": None,
            "connection": None,
            "overwrite_requested": overwrite,
            "artifact": None,
            "device": None,
            "destination": {
                "path": None,
                "remote_path": None,
                "preflight": None,
                "postflight": None,
            },
            "action": {
                "planned": None,
                "upload_began": False,
                "transport_status": None,
                "confirmation": None,
            },
        },
        outcome="planned",
    )


def with_connection(document: CommandDocument, connection: ResolvedConnection) -> CommandDocument:
    """Record where this invocation resolved to write, and what decided each half of it."""

    destination = mapping(document["destination"])
    return with_facts(
        document,
        {
            "configuration": connection.configuration,
            "connection": connection.facts(),
            "destination": {**destination, "path": connection.destination.value},
        },
    )


def with_action(document: CommandDocument, **changes: object) -> CommandDocument:
    """Replace one part of the action facts without restating the rest of them."""

    return with_facts(document, {"action": {**mapping(document["action"]), **changes}})


def with_destination(document: CommandDocument, **changes: object) -> CommandDocument:
    """Replace one part of the destination facts without restating the rest of them."""

    return with_facts(document, {"destination": {**mapping(document["destination"]), **changes}})


def prepare_storage(workspace: Workspace) -> Storage | DeliveryRefusal:
    """Make sure this Workspace can hold a record before anything worth recording happens.

    Every plan and attempt needs an immutable record, so a Workspace that cannot keep one has to
    refuse — and it has to refuse *here*, before the device is touched,
    because refusing after a confirmed upload would report "nothing was written" about a book
    that is sitting on the device.
    """

    storage = Storage(workspace.path)
    try:
        storage.collection.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return _unwritable(storage, str(error))
    if directory_state(storage.collection, writable=True) != "usable":
        return _unwritable(storage, directory_state(storage.collection, writable=True))
    return storage


def _unwritable(storage: Storage, detail: str) -> DeliveryRefusal:
    return DeliveryRefusal(
        boundary="delivery-record-unwritable",
        stage=STORAGE_STAGE,
        summary=f"the Workspace cannot hold a Delivery Record at {display_path(storage.collection)}",
        fact={"collection": display_path(storage.collection), "detail": detail},
    )


def emit_record(document: CommandDocument, run: ReportRun) -> RecordEmission:
    """Stamp, persist and only then hand back the record the command is about to render.

    The record reaches disk before its structured data reaches a reader, so a caller who sees an
    outcome can always find the record that states it. `prepare_storage` has already
    refused a Workspace that cannot hold one, so a failure here means the Workspace broke during
    the run — and the outcome is never rewritten to hide it. Rewriting a confirmed Delivery as a
    refusal would claim nothing was written about a book that is on the device.
    """

    emission = emitted(document, run)
    stored = persist(emission.document, Storage(_workspace_path(emission.document)))
    if isinstance(stored, DeliveryRefusal):
        return RecordEmission(emission.document, emission.exit_code, None, stored)
    return RecordEmission(emission.document, emission.exit_code, stored, None)


def persist(document: CommandDocument, storage: Storage) -> Path | DeliveryRefusal:
    """Write one record atomically: a hidden sibling first, then a rename into the collection."""

    identifier = str(document["record_id"])
    staged = storage.staged(identifier)
    try:
        storage.collection.mkdir(parents=True, exist_ok=True)
        _ = staged.write_text(document_json(document) + "\n", encoding="utf-8")
        target = storage.record(identifier)
        _ = staged.replace(target)
    except OSError as error:
        _discard(staged)
        return DeliveryRefusal(
            boundary="delivery-record-unwritable",
            stage=STORAGE_STAGE,
            summary=f"could not write the Delivery Record into {display_path(storage.collection)}",
            fact={"collection": display_path(storage.collection), "detail": str(error)},
        )
    return target


def _discard(staged: Path) -> None:
    """Leave no half-written record behind when the write itself failed."""

    try:
        staged.unlink(missing_ok=True)
    except OSError:
        return


def _workspace_path(document: CommandDocument) -> Path:
    """Read which Workspace a finished record belongs to from the record itself."""

    return Path(str(mapping(document["workspace"])["path"]))

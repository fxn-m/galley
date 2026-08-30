"""Build the versioned command documents Galley's non-Report commands emit.

Workspace, Inbox, device and Delivery facts are not one of the Report's five source/artifact
categories, so forcing them into the Report would mean either lying about what a Report is or
growing it a sixth category that inspect, prepare and audit never fill. Each of these commands
gets its own validated document instead, sharing only the envelope: run identity, one outcome,
one structured refusal. Human output is rendered from these same facts and is never a second
source of truth.

This is a shared kernel primitive rather than Workspace knowledge, which is why it sits at the
root: `workspace/` and `delivery/` both emit into this family, and putting the envelope inside
either one would make the other import a package it has no other business in.
"""

import json
from dataclasses import dataclass
from functools import cache
from typing import Literal, Protocol, cast
from uuid import uuid4

from galley import __version__
from galley.outcomes import ExitCode
from galley.report.clock import timestamp
from galley.report.envelope import ReportRun
from galley.json_reading import mapping, text
from galley.validation import SchemaValidator, load_schema

CONFIG_VALIDATION_SCHEMA = "galley/config-validation/1"
INBOX_CHECK_SCHEMA = "galley/inbox-check/1"
DEVICE_STATUS_SCHEMA = "galley/device-status/1"
DELIVERY_RECORD_V1_SCHEMA = "galley/delivery-record/1"
DELIVERY_RECORD_SCHEMA = "galley/delivery-record/2"
LOCALISATION_SCHEMA = "galley/localisation/1"
SKILL_INSTALLATION_SCHEMA = "galley/skill-installation/1"
SCHEMA_FILES = {
    CONFIG_VALIDATION_SCHEMA: "config-validation.json",
    INBOX_CHECK_SCHEMA: "inbox-check.json",
    DEVICE_STATUS_SCHEMA: "device-status.json",
    DELIVERY_RECORD_V1_SCHEMA: "delivery-record.json",
    DELIVERY_RECORD_SCHEMA: "delivery-record-v2.json",
    LOCALISATION_SCHEMA: "localisation.json",
    SKILL_INSTALLATION_SCHEMA: "skill-installation.json",
}

CommandName = Literal[
    "config validate",
    "inbox check",
    "device status",
    "deliver",
    "localise",
    "skill install",
    "skill uninstall",
]

# Every document in this family carries one outcome, but the vocabulary is the command's own. A
# Delivery Record states Delivery facts — `planned`, `delivered`, `already-delivered`,
# `unconfirmed` — and never borrows the preparation Report's completed/refused pair to say them.
Outcome = Literal[
    "completed", "refused", "planned", "delivered", "already-delivered", "unconfirmed"
]

REFUSED: Outcome = "refused"
UNCONFIRMED: Outcome = "unconfirmed"

CommandDocument = dict[str, object]


@dataclass(frozen=True)
class DocumentEmission:
    """One finished command document paired with its public process outcome."""

    document: CommandDocument
    exit_code: ExitCode


def command_document(
    command: CommandName,
    schema_id: str,
    run: ReportRun,
    facts: CommandDocument,
    *,
    outcome: Outcome = "completed",
) -> CommandDocument:
    """Create one validated command document envelope around a command's own facts."""

    document: CommandDocument = {
        "galley": {
            "version": __version__,
            "command": command,
            "run_id": str(uuid4()),
            "started_at": timestamp(run.started_at),
            "finished_at": timestamp(run.started_at),
            "duration_ms": 0,
            "document_schema": schema_id,
        },
        "outcome": outcome,
        "refusal": None,
        **facts,
    }
    validate_document(document)
    return document


def with_facts(document: CommandDocument, facts: CommandDocument) -> CommandDocument:
    """Return the document with one or more of its own fact fields replaced."""

    validate_document(document)
    updated: CommandDocument = {**document, **facts}
    validate_document(updated)
    return updated


def with_outcome(document: CommandDocument, outcome: Outcome) -> CommandDocument:
    """Return the document under a different outcome of its own command's vocabulary."""

    validate_document(document)
    updated: CommandDocument = {**document, "outcome": outcome}
    validate_document(updated)
    return updated


class Refusal(Protocol):
    """Anything that already knows why one command stopped, and where."""

    @property
    def boundary(self) -> str: ...
    @property
    def stage(self) -> str: ...
    @property
    def summary(self) -> str: ...
    @property
    def fact(self) -> dict[str, object]: ...


def with_refusal(document: CommandDocument, refusal: Refusal) -> CommandDocument:
    """Replace only refusal state, retaining every fact established before the boundary."""

    validate_document(document)
    galley = cast(dict[str, object], document["galley"])
    refused: CommandDocument = {
        **document,
        "outcome": REFUSED,
        "refusal": {
            "boundary": refusal.boundary,
            "authority": galley["command"],
            "stage": refusal.stage,
            "summary": refusal.summary,
            "fact": refusal.fact,
        },
    }
    validate_document(refused)
    return refused


def emitted(document: CommandDocument, run: ReportRun) -> DocumentEmission:
    """Stamp the finishing time onto one document and allocate its public exit code."""

    galley = cast(dict[str, object], document["galley"])
    finished_at = run.clock.utc_now()
    finished: CommandDocument = {
        **document,
        "galley": {
            **galley,
            "finished_at": timestamp(finished_at),
            "duration_ms": max(0, (run.clock.monotonic_ns() - run.started_clock) // 1_000_000),
        },
    }
    validate_document(finished)
    return DocumentEmission(finished, _exit_code(finished["outcome"]))


def _exit_code(outcome: object) -> ExitCode:
    """Allocate the public process outcome one document's own outcome earns.

    An Unconfirmed Delivery gets its own code because it is neither success nor failure: the
    device may or may not have retained the bytes, and a caller must be able to tell that apart
    from a refusal that definitely wrote nothing.
    """

    if outcome == REFUSED:
        return ExitCode.REFUSED
    if outcome == UNCONFIRMED:
        return ExitCode.DELIVERY_UNCONFIRMED
    return ExitCode.COMPLETED


def refusal_lines(document: CommandDocument) -> list[str]:
    """Render the boundary a document stopped at, and nothing when it did not stop.

    This is the one field every document in the family carries and renders identically, so it
    lives with the envelope rather than being restated by each package that emits one.
    """

    refusal = document.get("refusal")
    if not isinstance(refusal, dict):
        return []
    stated = cast(dict[str, object], refusal)
    return [f"Boundary: {stated['boundary']}", str(stated["summary"])]


def document_json(document: CommandDocument) -> str:
    """Serialize one validated command document as stable JSON."""

    validate_document(document)
    return json.dumps(document, indent=2, sort_keys=True)


def validate_document(document: CommandDocument) -> None:
    """Reject any object outside the schema its own envelope claims."""

    galley = mapping(document.get("galley"))
    _validator(text(galley.get("document_schema")) or "").validate(document)


@cache
def _validator(schema_id: str) -> SchemaValidator:
    """Load the one packaged schema a document's own envelope names."""

    name = SCHEMA_FILES.get(schema_id)
    if name is None:
        raise ValueError(f"unknown command document schema: {schema_id!r}")
    return load_schema(name)[1]

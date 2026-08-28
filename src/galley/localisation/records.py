"""Build the `galley/localisation/1` document one localisation emits.

The document is the point of the command as much as the bytes are. A flag on `prepare` would
fetch invisibly inside a build; this records, for every reference, the locator it came from, the
addresses that host resolved to, how the transport ended, and what the bytes turned out to be —
so an agent and a human can see exactly what was pulled from where before any of it enters a book.

A refused run keeps the references it had already settled. Nothing was written, so each of them
names a null path: the record says what happened, never what would have.
"""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from galley.digests import bytes_digest
from galley.documents import (
    LOCALISATION_SCHEMA,
    CommandDocument,
    command_document,
    with_refusal,
)
from galley.localisation.references import Reference
from galley.localisation.refusals import LocalisationRefusal
from galley.localisation.repair_set import image_path
from galley.locations import display_path
from galley.report.envelope import ReportRun
from galley.sources import MARKDOWN

LOCALISE = "localise"
RETRIEVED = "retrieved"


@dataclass(frozen=True)
class Retrieval:
    """One reference's whole story: what was asked for, and what arrived."""

    reference: Reference
    outcome: str
    detail: str = ""
    addresses: tuple[str, ...] = ()
    status: int | None = None
    data: bytes | None = None
    media_type: str | None = None
    name: str | None = None
    """The file name the bytes take under `images/`, once a media type has named its extension."""

    @property
    def retrieved(self) -> bool:
        """Say whether this reference produced bytes Galley could measure as an image."""

        return self.outcome == RETRIEVED and self.data is not None

    def facts(self, directory: Path | None) -> dict[str, object]:
        """State this reference exactly as it ended, naming a file only where one was written."""

        located = None if directory is None or self.name is None else self.path(directory)
        return {
            "identifier": self.reference.identifier,
            "locator": self.reference.locator,
            "host": urlsplit(self.reference.locator).hostname,
            "addresses": list(self.addresses),
            "occurrences": self.reference.occurrences,
            "transport": {
                "outcome": self.outcome,
                "status": self.status,
                "detail": self.detail,
            },
            "path": located,
            "sha256": None if self.data is None else bytes_digest(self.data),
            "byte_size": None if self.data is None else len(self.data),
            "media_type": self.media_type,
        }

    def path(self, directory: Path) -> str:
        """Name the file these bytes were written to, under the evidence directory's `images/`."""

        return display_path(image_path(directory, str(self.name)))


def localisation_record(
    run: ReportRun,
    *,
    requested: str,
    profile: dict[str, object] | None = None,
    source: Path | None = None,
    source_digest: str | None = None,
    evidence: dict[str, object] | None = None,
    retrievals: tuple[Retrieval, ...] = (),
    directory: Path | None = None,
) -> CommandDocument:
    """Assemble one localisation document from whatever this run had settled when it ended."""

    return command_document(
        LOCALISE,
        LOCALISATION_SCHEMA,
        run,
        {
            "profile": {
                "requested": requested,
                "resolved": profile is not None,
                "id": None if profile is None else profile["id"],
            },
            "source": (
                None
                if source is None
                else {
                    "kind": MARKDOWN,
                    "path": display_path(source),
                    "sha256": source_digest,
                }
            ),
            "evidence": evidence,
            "references": [retrieval.facts(directory) for retrieval in retrievals],
        },
    )


def refused(document: CommandDocument, refusal: LocalisationRefusal) -> CommandDocument:
    """Refuse one localisation, retaining every fact it had established before it stopped."""

    return with_refusal(document, refusal)

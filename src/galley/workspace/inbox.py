"""Inventory one configured Inbox, reading nothing but what a candidate's identity needs.

This is the whole of Inbox Check's contact with a user's source locations, and it is read-only
in the strict sense: it lists directories and reads file bytes to hash them, and it creates,
moves, renames and edits nothing. It also never follows a directory symlink, so an Inbox cannot
be talked into walking out of itself or around a loop.

Which files are candidates is release data, not a rule spelled here: the suffix set comes from
the source kinds `inspect` and `prepare` already read, so the three commands cannot disagree
about what a Markdown source is.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from galley.digests import file_digest
from galley.locations import display_path, resolved
from galley.report.clock import timestamp
from galley.sources import SourceKind, local_kind
from galley.workspace.configuration import InboxDefinition
from galley.workspace.evidence import CandidateEvidence
from galley.workspace.layout import directory_state

CoverageStatus = Literal["checked", "unavailable"]


@dataclass(frozen=True)
class Unlisted:
    """One directory an Inbox walk could not read, which makes its coverage incomplete."""

    path: Path
    reason: str

    @property
    def detail(self) -> str:
        """State what stopped the walk and exactly where, for the coverage that reports it."""

        return f"{self.reason}: {display_path(self.path)}"


@dataclass(frozen=True)
class Candidate:
    """One supported source an Inbox Check observed, identified by resolved path and hash."""

    inbox: str
    display: Path
    path: Path
    kind: SourceKind
    byte_size: int
    modified_at: str
    sha256: str

    @property
    def resolved_path(self) -> str:
        """Name the resolved path this candidate is identified by, the one way it is written.

        Ready evidence records the same string, so a check derives state by comparing what a
        Report names against exactly what this candidate reports rather than a second rendering.
        """

        return display_path(self.path)

    def facts(self, inboxes: list[str], derived: CandidateEvidence) -> dict[str, object]:
        """Describe one candidate, naming every Inbox that can see it, not only its owner.

        What the evidence derived is supplied rather than found here: the walk reads sources,
        and what has already been published is a question about the Workspace this Inbox is
        checked from. A refused attempt is carried beside the state, never folded into it.
        """

        return {
            "primary_inbox": self.inbox,
            "inboxes": inboxes,
            "display_path": str(self.display),
            "resolved_path": self.resolved_path,
            "source_kind": self.kind.id,
            "byte_size": self.byte_size,
            "modified_at": self.modified_at,
            "sha256": self.sha256,
            "state": derived.state,
            "latest_attempt": derived.attempt,
        }


@dataclass(frozen=True)
class Coverage:
    """Exactly what one Inbox was able to report, so partial discovery is never hidden."""

    name: str
    path: Path
    recursive: bool
    status: CoverageStatus
    supported_count: int = 0
    ignored_count: int = 0
    error: str | None = None

    def facts(self) -> dict[str, object]:
        """Report coverage as measured, including the access error that ended it."""

        return {
            "name": self.name,
            "resolved_path": display_path(self.path),
            "recursive": self.recursive,
            "status": self.status,
            "supported_count": self.supported_count,
            "ignored_count": self.ignored_count,
            "error": self.error,
        }


@dataclass(frozen=True)
class Inventory:
    """One Inbox's coverage and the candidates it saw, before Inboxes are reconciled."""

    coverage: Coverage
    candidates: tuple[Candidate, ...]


def inventory(inbox: InboxDefinition) -> Inventory:
    """Inventory one configured Inbox, reporting what it saw and what stopped it.

    The *first* failure is the one reported, so the same broken Inbox always names the same
    directory rather than whichever one the walk happened to reach last. A supported file that
    cannot be read counts in neither total: it is not a candidate and it is not an ignored
    unsupported file, so it is named in the error instead of being absorbed into a count.
    """

    state = directory_state(inbox.path)
    if state != "usable":
        error = f"{state}: {display_path(inbox.path)}"
        return Inventory(_coverage(inbox, "unavailable", error=error), ())
    candidates: dict[Path, Candidate] = {}
    ignored = 0
    error: str | None = None
    for found in _files(inbox):
        observed = found if isinstance(found, Unlisted) else _observed(inbox.name, found)
        if observed is None:
            ignored += 1
        elif isinstance(observed, Unlisted):
            error = error or observed.detail
        else:
            _ = candidates.setdefault(observed.path, observed)
    status: CoverageStatus = "checked" if error is None else "unavailable"
    coverage = _coverage(inbox, status, supported=len(candidates), ignored=ignored, error=error)
    return Inventory(coverage, tuple(candidates.values()))


def _coverage(
    inbox: InboxDefinition,
    status: CoverageStatus,
    *,
    supported: int = 0,
    ignored: int = 0,
    error: str | None = None,
) -> Coverage:
    return Coverage(inbox.name, inbox.path, inbox.recursive, status, supported, ignored, error)


def _files(inbox: InboxDefinition) -> Iterator[Path | Unlisted]:
    """Yield every visible regular file this Inbox covers, or the error that hid some of them.

    Hidden entries are ignored whatever they are, a directory symlink is never followed, and a
    directory that cannot be listed is yielded as an error rather than silently skipped — an
    Inbox that quietly omitted part of itself would report coverage it does not have.
    """

    pending = [inbox.path]
    while pending:
        current = pending.pop(0)
        try:
            entries = sorted(current.iterdir())
        except OSError as failure:
            yield Unlisted(current, type(failure).__name__)
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                if inbox.recursive and not entry.is_symlink():
                    pending.append(entry)
                continue
            if entry.is_file():
                yield entry


def _observed(name: str, path: Path) -> Candidate | Unlisted | None:
    """Read one visible file as a candidate, or say that it is not one, or that it would not read.

    None means the file is simply not a source Galley reads, which is an ordinary ignored file.
    An `Unlisted` means it is one and could not be read, which is a hole in this Inbox's coverage.
    """

    if not local_kind(path).supported:
        return None
    return _candidate(name, path)


def _candidate(name: str, path: Path) -> Candidate | Unlisted:
    try:
        stat = path.stat()
        digest = file_digest(path)
    except OSError as failure:
        return Unlisted(path, type(failure).__name__)
    modified = datetime.fromtimestamp(stat.st_mtime, UTC)
    return Candidate(
        inbox=name,
        display=path,
        path=resolved(path),
        kind=local_kind(path),
        byte_size=stat.st_size,
        modified_at=timestamp(modified),
        sha256=digest,
    )

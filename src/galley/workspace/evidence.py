"""Read the immutable Reports beside Ready Artifacts, and derive a candidate's state from them.

Galley keeps no index, no mutable status file and no job database, so what is already ready is a
question about evidence on disk, asked afresh every time. The collection is scanned once per
check and indexed by the source path each Report names; the candidate's own hash then decides
between the three states without a second pass over the Workspace.

Nothing here is taken on its word. `already-ready` is the only state that claims a finished book
exists, so it is the only one that opens the artifact: a Report whose EPUB has been deleted or
replaced describes a publication that is no longer there, and reporting it as ready would send a
reader to a book that is missing. Evidence that cannot be read answers nothing rather than
standing in for an answer — and says so, because damage a check hides is damage a reader cannot
act on. Nothing is deleted, repaired or rebuilt on the way past.

A refused attempt is read too, from the Galley-owned work storage a retry replaces. It is the
most recent thing that happened at one exact provenance, reported beside the state and never
instead of it: failure is not a fourth state a candidate can be in.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from galley.digests import file_digest
from galley.json_reading import mapping, text
from galley.locations import display_path
from galley.workspace.bundles import REPORT_NAME, published_bundles, retained_document
from galley.workspace.ready import ReadyWorkspace, evidence_key

CandidateState = Literal["new", "changed", "already-ready"]

NEW: CandidateState = "new"
CHANGED: CandidateState = "changed"
ALREADY_READY: CandidateState = "already-ready"

Problem = Literal[
    "unreadable-report",
    "incomplete-report",
    "artifact-missing",
    "artifact-unreadable",
    "artifact-mismatched",
]

UNREADABLE_REPORT: Problem = "unreadable-report"
INCOMPLETE_REPORT: Problem = "incomplete-report"
ARTIFACT_MISSING: Problem = "artifact-missing"
ARTIFACT_UNREADABLE: Problem = "artifact-unreadable"
ARTIFACT_MISMATCHED: Problem = "artifact-mismatched"


@dataclass(frozen=True)
class Damaged:
    """One evidence bundle that is not the immutable record a Ready publication left."""

    bundle: Path
    problem: Problem
    artifact: Path | None = None

    def facts(self) -> dict[str, object]:
        """Name the bundle, what is wrong with it, and the book it claimed if it named one."""

        return {
            "problem": self.problem,
            "evidence_path": display_path(self.bundle),
            "artifact_path": None if self.artifact is None else display_path(self.artifact),
        }


@dataclass(frozen=True)
class ReadyRecord:
    """One published Ready Artifact, as the source pair and the book its own Report names."""

    bundle: Path
    source: str
    source_sha256: str
    artifact: Path
    artifact_sha256: str

    def absence(self) -> Damaged | None:
        """Ask whether the book this Report named is still there at all — one stat, per record.

        A Report is immutable, but the Workspace holding it is an ordinary directory a user can
        empty. Asking is cheap enough to ask of every record the scan reads, so a vanished book
        is reported whatever state the candidate that produced it turns out to be in.
        """

        if self.artifact.is_file():
            return None
        return Damaged(self.bundle, ARTIFACT_MISSING, self.artifact)

    def damage(self) -> Damaged | None:
        """Ask whether that book is also still itself, which costs a read of the whole EPUB.

        Hashing is what stops a replaced artifact from being reported as ready, and it is the
        one question here that is not cheap — so it is asked only of a candidate whose exact
        source pair already matched, never of the collection.
        """

        absent = self.absence()
        if absent is not None:
            return absent
        try:
            current = file_digest(self.artifact)
        except OSError:
            return Damaged(self.bundle, ARTIFACT_UNREADABLE, self.artifact)
        if current != self.artifact_sha256:
            return Damaged(self.bundle, ARTIFACT_MISMATCHED, self.artifact)
        return None


@dataclass(frozen=True)
class CandidateEvidence:
    """Everything the retained evidence says about one candidate at one exact provenance."""

    state: CandidateState
    attempt: dict[str, object] | None = None
    damage: Damaged | None = None


@dataclass(frozen=True)
class ReadyEvidence:
    """Every readable Ready Report in one Workspace, and the damage the scan already found."""

    home: ReadyWorkspace
    by_source: dict[str, tuple[ReadyRecord, ...]]
    damaged: tuple[Damaged, ...]

    def derive(self, source: str, content_sha256: str) -> CandidateEvidence:
        """Say whether one exact source pair is new, changed, or already published.

        A renamed or copied source is new however familiar its bytes are, because the index is
        the resolved path: recurring content under a path that has never been prepared has never
        been prepared. Reverting a file to a hash prepared earlier finds that pair's own Report
        still sitting in the collection, so it is recognised rather than built again.

        Damaged evidence is reported and then treated as absent, which is what keeps it from
        answering: a pair whose artifact has gone falls back to `changed` where the path has
        sound evidence under another hash, and to `new` where it does not.
        """

        records = self.by_source.get(source, ())
        exact = next((found for found in records if found.source_sha256 == content_sha256), None)
        attempt = _attempt(self.home.attempt(evidence_key(source, content_sha256)))
        damage = None if exact is None else exact.damage()
        if exact is not None and damage is None:
            return CandidateEvidence(ALREADY_READY, attempt)
        changed = any(found.source_sha256 != content_sha256 for found in records)
        return CandidateEvidence(CHANGED if changed else NEW, attempt, damage)


def ready_evidence(home: ReadyWorkspace) -> ReadyEvidence:
    """Scan the Ready evidence collection once per check, never once per candidate.

    Every bundle is asked whether the book it names is still on disk, because that answer costs
    one stat and a vanished book has to be reported whether or not a candidate still points at
    it — a source edited or removed since publication would otherwise hide the loss.
    """

    indexed: dict[str, list[ReadyRecord]] = {}
    damaged: list[Damaged] = []
    for bundle in published_bundles(home):
        read = _record(bundle)
        if isinstance(read, ReadyRecord):
            indexed.setdefault(read.source, []).append(read)
            damaged.extend(found for found in [read.absence()] if found is not None)
        elif read is not None:
            damaged.append(read)
    return ReadyEvidence(home, {source: tuple(r) for source, r in indexed.items()}, tuple(damaged))


def problem_facts(found: Sequence[Damaged]) -> list[dict[str, object]]:
    """Report every distinct evidence problem once, in one order that does not depend on a walk.

    Unreadable bundles are found by the scan and damaged artifacts by the candidates that
    claimed them, so the same bundle can arrive twice; a reader wants the problem once.
    """

    unique = {(display_path(item.bundle), item.problem): item for item in found}
    return [unique[key].facts() for key in sorted(unique)]


def _record(bundle: Path) -> ReadyRecord | Damaged | None:
    """Read one bundle's Report as a published local source, or say what it is instead.

    An Article-Like Page's Report names a locator rather than a path, so it indexes nothing an
    Inbox Check will ever ask about and is not damage. A Report that will not open or parse, or
    that does not record the source pair and the book every Ready publication records, is.
    """

    document = retained_document(bundle / REPORT_NAME)
    if document is None:
        return Damaged(bundle, UNREADABLE_REPORT)
    source = mapping(document.get("source"))
    located = text(source.get("path"))
    if located is None:
        return None if text(source.get("url")) else Damaged(bundle, INCOMPLETE_REPORT)
    artifact = mapping(document.get("artifact"))
    content = text(source.get("sha256"))
    artifact_path = text(artifact.get("path"))
    artifact_digest = text(artifact.get("sha256"))
    if not (content and artifact_path and artifact_digest):
        return Damaged(bundle, INCOMPLETE_REPORT)
    return ReadyRecord(bundle, located, content, Path(artifact_path), artifact_digest)


def _attempt(directory: Path) -> dict[str, object] | None:
    """Read the latest refused attempt at one provenance, which the next attempt replaces.

    Work evidence is replaceable by design, so this is always the last attempt rather than a
    history of them, and a candidate carrying one is still eligible for retry. A directory that
    holds nothing readable simply reports no attempt.
    """

    document = retained_document(directory / REPORT_NAME)
    if document is None:
        return None
    refusal = mapping(document.get("refusal"))
    boundary = text(refusal.get("boundary"))
    if boundary is None:
        return None
    galley = mapping(document.get("galley"))
    return {
        "boundary": boundary,
        "stage": text(refusal.get("stage")) or "",
        "summary": text(refusal.get("summary")) or "",
        "finished_at": text(galley.get("finished_at")) or "",
    }

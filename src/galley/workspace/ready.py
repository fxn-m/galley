"""Resolve where one Ready publication puts its artifact, its evidence and its failed attempts.

Ready publication needs the Workspace, not the Workspace Configuration: `work`, `ready` and
`delivery` are fixed roles beneath a Galley Workspace rather than anything a user configures, so
reading `galley.toml` here would add a way to fail without adding a fact.

Evidence is keyed by source provenance, independently of the artifact's filename. That is what
lets two different sources that build byte-identical books each keep their own immutable Report
without either one mutating the other's, and it is the collection a later Inbox Check scans to
decide what is already ready.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from galley.json_reading import mapping, text
from galley.report.envelope import Report
from galley.workspace.layout import ready_directory, ready_evidence_directory, work_directory
from galley.workspace.resolution import Workspace, resolve_workspace

KEY_LENGTH = 24
STAGED_PREFIX = "."
STAGED_SUFFIX = ".galley-candidate"


@dataclass(frozen=True)
class ReadyWorkspace:
    """The Galley-owned locations one Ready publication writes into."""

    workspace: Workspace

    @property
    def artifacts(self) -> Path:
        """Name the directory immutable Ready Artifacts are published into."""

        return ready_directory(self.workspace.path)

    @property
    def collection(self) -> Path:
        """Name the collection of immutable Ready evidence a later check scans for state."""

        return ready_evidence_directory(self.workspace.path)

    def evidence(self, key: str) -> Path:
        """Name one immutable Ready evidence bundle, keyed by its source provenance."""

        return self.collection / key

    def staged_evidence(self, key: str) -> Path:
        """Name the hidden sibling a Ready bundle is built in before it becomes visible."""

        return self.collection / f"{STAGED_PREFIX}{key}{STAGED_SUFFIX}"

    def attempt(self, key: str) -> Path:
        """Name where a refused attempt's evidence is retained, which a retry replaces."""

        return work_directory(self.workspace.path) / key


def ready_workspace(chosen: Path | None) -> ReadyWorkspace:
    """Resolve the Galley Workspace one Ready publication belongs to."""

    return ReadyWorkspace(resolve_workspace(chosen))


def evidence_key(source: str, content_sha256: str) -> str:
    """Key one evidence bundle by the exact source provenance that produced it.

    The pair is the resolved source path — or the page locator, for a source with no local
    bytes — and the content hash beside it. A renamed or copied source is therefore a different
    provenance even when its bytes recur, which is what keeps a Report source-specific.
    """

    return sha256(f"{source}\n{content_sha256}".encode()).hexdigest()[:KEY_LENGTH]


def provenance(report: Report) -> tuple[str, str]:
    """Read the source provenance one finished Report records, whichever route produced it.

    A Markdown source is its resolved path and the digest of its bytes. An Article-Like Page has
    no local bytes to hash, so it is its locator and the digest of the Canonical Document the
    extraction produced — the first thing about that page Galley can hash at all.
    """

    source = mapping(report.get("source"))
    canonical = mapping(report.get("canonical_document"))
    located = text(source.get("path")) or text(source.get("url")) or ""
    digest = text(source.get("sha256")) or text(canonical.get("sha256")) or ""
    return located, digest

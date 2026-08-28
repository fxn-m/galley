"""Publish a prepared EPUB only once every other output this command owns is complete.

A candidate is built in temporary space, which may be on another filesystem, so it is staged
beside its final path first. Publication is then one rename: the artifact is never visible
half-written, and a refusal discards the staged bytes rather than leaving a partial book behind.

Where that final path is depends on the mode. An explicit output names it before any work
starts; a Ready publication cannot, because the name may carry the artifact's own hash and the
bytes do not exist until packaging is done. Both arrive here as a `Destination` that is asked
for its `Publication` once, at the moment the candidate exists.
"""

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from galley.locations import display_path

ARTIFACT_STAGE = "artifact-output"
CANDIDATE_SUFFIX = ".galley-candidate"


@dataclass(frozen=True)
class Publication:
    """One EPUB output path, and the staged candidate waiting to become it."""

    output: Path
    staged: Path | None = None
    reuse: bool = False
    """Whether these exact bytes are already published here, so nothing is written at all.

    Identical bytes are reused rather than rewritten: the artifact is immutable, so replacing it
    with a copy of itself would be a write with no effect and a window in which it did not
    exist. The run still publishes its own source-specific evidence bundle.
    """

    @property
    def destinations(self) -> list[Path]:
        """Name every path publication would write, so each can be protected before any is."""

        if self.reuse:
            return []
        return [self.output, candidate_path(self.output)]


@dataclass(frozen=True)
class Collision:
    """Two different books competing for one Ready Artifact name, which is never resolved."""

    path: Path
    existing_sha256: str
    candidate_sha256: str

    def facts(self) -> dict[str, object]:
        """Name the occupied path and both digests, so the clash can be seen rather than told."""

        return {
            "candidate_sha256": self.candidate_sha256,
            "existing_sha256": self.existing_sha256,
            "path": display_path(self.path),
        }


class Destination(Protocol):
    """Where one preparation would publish its EPUB, decided once the candidate exists.

    The title is offered as well as the bytes because a Ready Artifact takes its name from the
    book: the Canonical Document has already settled that name, from the document's own metadata
    or from its source stem, so nothing here has to invent one.
    """

    def publication_for(self, candidate: Path, title: str) -> Publication | Collision: ...


@dataclass(frozen=True)
class ExplicitOutput:
    """The path the user named, which was settled and protected before any work began."""

    output: Path

    def publication_for(self, candidate: Path, title: str) -> Publication | Collision:
        """Name the same output whatever the candidate and the book turned out to be."""

        _ = (candidate, title)
        return Publication(self.output)


def candidate_path(output: Path) -> Path:
    """Name the hidden staging path beside one output, on the same filesystem it lives on."""

    return output.with_name(f".{output.name}{CANDIDATE_SUFFIX}")


def stage(publication: Publication, candidate: Path) -> Publication:
    """Copy one temporary candidate beside its output so publication is a single rename."""

    if publication.reuse:
        return publication
    staged = candidate_path(publication.output)
    staged.parent.mkdir(parents=True, exist_ok=True)
    _ = staged.write_bytes(candidate.read_bytes())
    return replace(publication, staged=staged)


def publish(publication: Publication) -> None:
    """Make the prepared EPUB visible at its final path in one atomic step."""

    if publication.staged is not None:
        os.replace(publication.staged, publication.output)


def discard(publication: Publication) -> None:
    """Remove a staged candidate a refusal will never publish."""

    if publication.staged is not None:
        publication.staged.unlink(missing_ok=True)


def occupied(publication: Publication, *, overwrite: bool) -> Path | None:
    """Name the first destination already occupied, unless replacement was asked for.

    The staged path is checked as well as the output: it belongs to this command, and a file
    already sitting there would be replaced by work the user never authorized.
    """

    if overwrite:
        return None
    return next((path for path in publication.destinations if path.exists()), None)


def occupied_fact(path: Path) -> dict[str, object]:
    """Describe one occupied artifact destination the way every Report names a path."""

    return {"path": display_path(path)}

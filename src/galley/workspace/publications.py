"""Find the immutable Report that published one Ready Artifact, from the artifact alone.

An Inbox Check asks the Ready evidence collection what it knows about a *source*; Delivery asks
it what it knows about a *book*. The collection is keyed by source provenance, so the second
question is a scan rather than a lookup — and it deliberately does not go through the candidate
index, which drops an Article-Like Page's Report because that Report names no local source path.
A book built from a page is a Ready Artifact like any other and must be deliverable.
"""

from dataclasses import dataclass
from pathlib import Path

from galley.digests import file_digest
from galley.json_reading import mapping, text
from galley.locations import display_path
from galley.workspace.bundles import REPORT_NAME, published_bundles, retained_document
from galley.workspace.ready import ReadyWorkspace


@dataclass(frozen=True)
class PublishedArtifact:
    """One Ready Artifact as the immutable evidence bundle that published it describes it."""

    bundle: Path
    report: Path
    artifact: Path
    artifact_sha256: str
    profile: dict[str, object]

    def report_sha256(self) -> str:
        """Hash the preparation Report a Delivery Record references, so the reference is exact."""

        return file_digest(self.report)


def published_artifact(home: ReadyWorkspace, artifact: Path) -> PublishedArtifact | None:
    """Return the evidence bundle whose Report names this exact artifact, or nothing.

    Identity is the resolved path each Report already records, so a second name for the same
    file finds the same bundle. Two bundles may legitimately name one artifact — identical bytes
    published from different provenances are reused rather than rebuilt — and either one is a
    complete answer to "was this book prepared, and what was it", so the first in the stable
    scan order is taken rather than treating the pair as ambiguity.
    """

    wanted = display_path(artifact)
    for bundle in published_bundles(home):
        document = retained_document(bundle / REPORT_NAME)
        if document is None:
            continue
        facts = mapping(document.get("artifact"))
        digest = text(facts.get("sha256"))
        if text(facts.get("path")) != wanted or digest is None:
            continue
        return PublishedArtifact(bundle, bundle / REPORT_NAME, artifact, digest, _profile(document))
    return None


def _profile(document: dict[str, object]) -> dict[str, object]:
    """Name the Device Profile the book was prepared for, which Delivery reports but never uses."""

    profile = mapping(document.get("profile"))
    software = mapping(profile.get("observed_software"))
    firmware = text(software.get("version")) if software.get("kind") == "firmware" else None
    return {
        "id": text(profile.get("id")) or "",
        "profile_version": text(profile.get("profile_version")) or "",
        "firmware_observed": firmware or "",
    }

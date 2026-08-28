"""Verify that the book a Delivery names really is a Ready Artifact of this Workspace.

Delivery is the one command that sends bytes off the machine, so what it accepts is deliberately
narrow: exactly one regular EPUB sitting directly inside the resolved Workspace's `ready`
directory, with the immutable preparation Report that published it still present and the bytes
still the bytes that Report recorded. Every one of those questions is answered locally, before a
single packet is sent, because a book that is not a Ready Artifact must never reach the device.

The path is resolved first, so a symlink is judged by where it actually leads. That is what
makes "directly inside ready" also mean "cannot escape ready".
"""

from dataclasses import dataclass
from pathlib import Path

from galley.delivery.refusals import DeliveryRefusal
from galley.digests import file_digest
from galley.locations import display_path, resolved
from galley.workspace.publications import PublishedArtifact, published_artifact
from galley.workspace.ready import ReadyWorkspace

ARTIFACT_STAGE = "ready-artifact"
EPUB_SUFFIX = ".epub"


@dataclass(frozen=True)
class Deliverable:
    """One verified Ready Artifact and the immutable preparation evidence behind it."""

    path: Path
    sha256: str
    byte_size: int
    publication: PublishedArtifact
    report_sha256: str

    def facts(self) -> dict[str, object]:
        """Reference the artifact and its preparation evidence, copying neither."""

        return {
            "path": display_path(self.path),
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "report_path": display_path(self.publication.report),
            "report_sha256": self.report_sha256,
            "evidence_path": display_path(self.publication.bundle),
            "profile": self.publication.profile,
        }


def deliverable(home: ReadyWorkspace, chosen: Path) -> Deliverable | DeliveryRefusal:
    """Accept one Ready Artifact for Delivery, or say exactly which boundary it failed."""

    artifact = resolved(chosen.expanduser())
    unusable = _unusable(artifact, home)
    if unusable is not None:
        return unusable
    publication = published_artifact(home, artifact)
    if publication is None:
        return DeliveryRefusal(
            boundary="missing-preparation-evidence",
            stage=ARTIFACT_STAGE,
            summary=(
                f"no immutable Ready evidence in this Workspace names {display_path(artifact)}"
            ),
            fact={
                "artifact": display_path(artifact),
                "collection": display_path(home.collection),
            },
        )
    try:
        digest = file_digest(artifact)
        byte_size = artifact.stat().st_size
    except OSError as error:
        return DeliveryRefusal(
            boundary="unreadable-ready-artifact",
            stage=ARTIFACT_STAGE,
            summary=f"the Ready Artifact could not be read: {display_path(artifact)}",
            fact={"artifact": display_path(artifact), "detail": str(error)},
        )
    if digest != publication.artifact_sha256:
        return DeliveryRefusal(
            boundary="artifact-mismatched",
            stage=ARTIFACT_STAGE,
            summary=(
                "the Ready Artifact is no longer the book its preparation Report recorded: "
                f"{display_path(artifact)}"
            ),
            fact={
                "artifact": display_path(artifact),
                "observed_sha256": digest,
                "recorded_sha256": publication.artifact_sha256,
                "report": display_path(publication.report),
            },
        )
    return Deliverable(artifact, digest, byte_size, publication, publication.report_sha256())


def _unusable(artifact: Path, home: ReadyWorkspace) -> DeliveryRefusal | None:
    """Refuse anything that is not one regular EPUB directly inside this Workspace's ready."""

    if not artifact.is_file():
        return DeliveryRefusal(
            boundary="unusable-ready-artifact",
            stage=ARTIFACT_STAGE,
            summary=f"not a regular file: {display_path(artifact)}",
            fact={"artifact": display_path(artifact)},
        )
    if artifact.suffix.lower() != EPUB_SUFFIX:
        return DeliveryRefusal(
            boundary="unusable-ready-artifact",
            stage=ARTIFACT_STAGE,
            summary=f"not an EPUB: {display_path(artifact)}",
            fact={"artifact": display_path(artifact), "suffix": artifact.suffix},
        )
    artifacts = resolved(home.artifacts)
    if artifact.parent != artifacts:
        return DeliveryRefusal(
            boundary="artifact-outside-ready",
            stage=ARTIFACT_STAGE,
            summary=(
                f"a Ready Artifact must sit directly inside {display_path(artifacts)}, "
                f"and this one resolves to {display_path(artifact)}"
            ),
            fact={"artifact": display_path(artifact), "ready": display_path(artifacts)},
        )
    return None

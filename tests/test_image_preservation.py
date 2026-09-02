"""Mapping failures no bundled profile and no real source can produce, specified directly.

Image Preservation refuses on a book that lost an image. Getting a real Pandoc run to lose one
would mean breaking the writer, so the comparison is specified against artifact facts written
here — the same approach `test_note_conversion` takes to the note mismatch it guards.
"""

from pathlib import Path
from typing import Any

from galley.images.preparation import ImagePreparation, ImageReference
from galley.images.records import image_mismatch, preservation_refusal
from galley.images.resources import NORMALISED, Packaged, PackagedResource
from galley.images.measurement import ImageMeasurement
from galley.report.envelope import ReportAssembly
from galley.profile.loading import load_profile

PROFILE = load_profile("x4-crosspoint")
PNG = ImageMeasurement(media_type="image/png", intact=True, width=8, height=8)


def reference(identifier: str, digest: str, *, cover: bool = False) -> ImageReference:
    packaged = Packaged(
        path=Path(f"/tmp/{identifier}.png"), digest=digest, byte_size=8, measurement=PNG
    )
    resource = PackagedResource(
        source=f"/tmp/{identifier}-source.png",
        digest=f"source-{digest}",
        byte_size=8,
        measurement=PNG,
        support="false",
        fits=True,
        transform=NORMALISED,
        packaged=packaged,
    )
    return ImageReference(
        identifier=identifier,
        src=f"{identifier}.png",
        alt=None,
        title=None,
        resource=resource,
        cover=cover,
    )


def artifact(*resources: dict[str, Any]) -> dict[str, object]:
    return {"images": {"resources": list(resources)}}


def resource(digest: str, *, referenced: bool = True, cover: bool = False) -> dict[str, Any]:
    return {
        "cover": cover,
        "measured_media_type": "image/png",
        "path": f"EPUB/media/{digest}.png",
        "referenced": referenced,
        "sha256": digest,
    }


def test_a_book_carrying_every_reference_is_not_refused() -> None:
    preparation = ImagePreparation(ast={}, references=[reference("image-1", "one")])

    mismatch: Any = image_mismatch(artifact(resource("one")), preparation)

    assert mismatch["unmapped"] == []
    assert mismatch["references"]["value"] == 1


def test_a_reference_whose_resource_the_archive_lacks_is_unmapped() -> None:
    preparation = ImagePreparation(ast={}, references=[reference("image-1", "one")])

    mismatch: Any = image_mismatch(artifact(resource("other")), preparation)

    assert mismatch["unmapped"] == [
        {"reason": "absent-resource", "reference": "image-1", "src": "image-1.png"}
    ]


def test_a_resource_no_content_document_points_at_is_unmapped() -> None:
    """A resource nothing references is a file in the archive the reader never meets."""

    preparation = ImagePreparation(ast={}, references=[reference("image-1", "one")])

    mismatch: Any = image_mismatch(artifact(resource("one", referenced=False)), preparation)

    assert [entry["reason"] for entry in mismatch["unmapped"]] == ["unreferenced-resource"]


def test_a_cover_the_package_does_not_declare_is_unmapped() -> None:
    """The cover must be the OPF cover image, not merely an image in the book."""

    preparation = ImagePreparation(ast={}, references=[reference("cover-image", "one", cover=True)])

    mismatch: Any = image_mismatch(artifact(resource("one", cover=False)), preparation)

    assert [entry["reason"] for entry in mismatch["unmapped"]] == ["cover-not-declared"]


def test_the_refusal_names_every_reference_the_book_does_not_carry() -> None:
    preparation = ImagePreparation(
        ast={}, references=[reference("image-1", "one"), reference("image-2", "two")]
    )
    mismatch: Any = image_mismatch(artifact(resource("one")), preparation)

    refused = preservation_refusal(ReportAssembly.completed("prepare", PROFILE), mismatch)

    refusal: Any = refused["refusal"]
    assert refused["outcome"] == "refused"
    assert refusal["boundary"] == "image-preservation"
    assert refusal["stage"] == "image-preparation"
    assert refusal["artifact_written"] is False
    assert "image-2.png (absent-resource)" in refusal["summary"]
    assert refusal["fact"]["unmapped"] == mismatch["unmapped"]

"""State what preparation did to one document's images, as Report facts and as a refusal.

A complete record exists for every image plus summary totals, with each source reference connected
to the resource the published book carries. Both sides of that connection are
measured independently — preparation writes the bytes and `audit` reads the archive — so the join
is by content hash rather than by name: Pandoc renames media on its way into the package, and a
name-based mapping would prove nothing about the bytes.
"""

from statistics import median_high
from typing import cast

from galley.json_reading import mapping, sequence, text
from galley.images.normalisation import pillow_versions
from galley.images.default_cover import DEFAULT_COVER
from galley.images.preparation import IMAGE_STAGE, ImagePreparation, ImageReference
from galley.images.resources import NORMALISED, REASONS
from galley.images.measurement import measurement_facts
from galley.report.envelope import Report, replace_refusal, with_dependency
from galley.report.quantities import quantity

PRESERVATION_BOUNDARY = "image-preservation"
REDUCTION = (
    "How far preparation reduced this document's figures to fit the panel, over every image "
    "reference except the cover. A scale is the packaged width against the source width, and the "
    "median takes the upper of the two middle values where the count is even. It states what the "
    "document leans on and how far it was reduced, and settles no question of legibility. Two "
    "device reads reached opposite verdicts; the more heavily reduced one was called very clear."
)
UNMAPPED = (
    "Every Canonical Document image reference must map to an image resource the built book "
    "carries and a content document references. A reference that does not is exactly the "
    "disappearance Image Preservation exists to catch, so the candidate is discarded."
)


def image_refusal(report: Report, preparation: ImagePreparation) -> Report:
    """Refuse a book whose images preparation could not carry, naming each one.

    Galley refuses rather than dropping the reference: an image the reader cannot see is a silent
    loss, so the decision happens at the point where the resource fails
    rather than after a package has been built around the gap.
    """

    summary = "; ".join(
        f"{failure.src} ({REASONS.get(failure.reason, failure.reason)})"
        for failure in preparation.failures
    )
    return replace_refusal(
        report,
        boundary="image-processing-failure",
        stage=IMAGE_STAGE,
        summary=f"cannot prepare every referenced image: {summary}",
        fact={
            "failures": [
                {"reason": failure.reason, "reference": failure.identifier, "src": failure.src}
                for failure in preparation.failures
            ],
            "references": quantity(
                len(preparation.references) + len(preparation.failures), "references"
            ),
            "unprepared": quantity(len(preparation.failures), "references"),
        },
    )


def image_dependencies(report: Report, preparation: ImagePreparation) -> Report:
    """Record the exact tools whose output the book carries, and only the ones that ran.

    A run that preserved every image ran no encoder, so naming one in the envelope would say
    Pillow's bytes are in a book that holds none of them.
    """

    versions: dict[str, str] = {}
    if any(resource.transform == NORMALISED for resource in preparation.resources):
        versions["pillow"] = pillow_versions()["pillow"]
    for resource in preparation.resources:
        rendered = resource.packaged.renderer or {}
        version = text(rendered.get("version"))
        if version is not None:
            versions[str(rendered.get("tool"))] = version
    for name, version in sorted(versions.items()):
        report = with_dependency(report, name, version)
    return report


def image_records(
    preparation: ImagePreparation,
    artifact: dict[str, object] | None,
    previews: dict[str, dict[str, str]] | None = None,
) -> dict[str, object]:
    """Connect every source reference to the resource the published book carries.

    The artifact side is absent until a book has been measured, and a record says so rather than
    implying a mapping nobody has checked. The packaged hash sits beside the source hash because
    the two part company as soon as a transform runs: preserved bytes are one case, not the rule.
    """

    published = _published(artifact)
    rendered = previews or {}
    records = [
        _record(reference, published, rendered.get(reference.identifier))
        for reference in preparation.references
    ]
    return {
        "cover": _cover_facts(preparation),
        "preservation": _preservation(records, artifact),
        "records": records,
        "reduction": _reduction(preparation),
        "totals": {
            "normalised": quantity(preparation.normalised, "images"),
            "preserved": quantity(preparation.preserved, "images"),
            "references": quantity(len(preparation.references), "references"),
            "resources": quantity(len(preparation.resources), "images"),
            "unprepared": quantity(len(preparation.failures), "references"),
        },
    }


def image_mismatch(facts: dict[str, object], preparation: ImagePreparation) -> dict[str, object]:
    """Return the references the built book does not carry, so preparation can refuse them.

    Every expected identity is compared against what `audit` decoded from the archive, not
    against what packaging believed it wrote. A cover counts as carried when the package points
    at it; a document image must also be referenced by a content document, since an unreferenced
    resource is a file the reader never meets.
    """

    published = _published(facts)
    unmapped: list[dict[str, object]] = []
    for reference in preparation.references:
        reason = _unmapped_reason(reference, published)
        if reason is not None:
            unmapped.append(
                {"reason": reason, "reference": reference.identifier, "src": reference.src}
            )
    return {
        "references": quantity(len(preparation.references), "references"),
        "unmapped": unmapped,
    }


def preservation_refusal(report: Report, mismatch: dict[str, object]) -> Report:
    """Refuse a book that lost an image, naming every reference the archive does not carry."""

    unmapped = cast(list[dict[str, object]], mismatch["unmapped"])
    summary = "; ".join(f"{entry['src']} ({entry['reason']})" for entry in unmapped)
    return replace_refusal(
        report,
        boundary=PRESERVATION_BOUNDARY,
        stage=IMAGE_STAGE,
        summary=f"the built book does not carry every image it references: {summary}",
        fact={**mismatch, "definition": UNMAPPED},
    )


def _unmapped_reason(
    reference: ImageReference, published: dict[str, dict[str, object]]
) -> str | None:
    resource = published.get(reference.resource.packaged.digest)
    if resource is None:
        return "absent-resource"
    if reference.cover:
        return None if resource.get("cover") is True else "cover-not-declared"
    return None if resource.get("referenced") is True else "unreferenced-resource"


def _preservation(
    records: list[dict[str, object]], artifact: dict[str, object] | None
) -> dict[str, object]:
    """State whether every reference mapped, and never claim it before a book has been read."""

    if artifact is None:
        return {"claimed": False, "reason": "no artifact has been measured yet"}
    mapped = [record for record in records if record["artifact"] is not None]
    return {
        "claimed": True,
        "definition": UNMAPPED,
        "mapped": quantity(len(mapped), "references"),
        "references": quantity(len(records), "references"),
        "unmapped": quantity(len(records) - len(mapped), "references"),
    }


def _reduction(preparation: ImagePreparation) -> dict[str, object]:
    """Summarise how far this document's figures were reduced, in one place rather than N.

    The Report has per-image scales, but an agent deciding whether to tell a reader that a
    document leans on pictures had to walk every record to reach them — and
    at twenty-eight records that is arithmetic nobody should redo. The aggregate is the same
    measurement, stated once.

    It is deliberately not a verdict and there is no threshold anywhere in it. Device reads rule
    one out: the document whose figures the reader called "very clear" was
    reduced *harder* than the one they called "just too small", so a rule keyed on any of these
    numbers would have fired on the wrong book.

    The cover is excluded because it is not a figure the work leans on. It stays a reference in
    `records` like any other, where preservation still accounts for it.
    """

    scales = sorted(
        reference.resource.packaged.scale_percent
        for reference in preparation.references
        if not reference.cover
    )
    return {
        "definition": REDUCTION,
        "images": quantity(len(scales), "images"),
        "reduced": quantity(sum(1 for scale in scales if scale < 100), "images"),
        "scale": _scale(scales),
    }


def _scale(scales: list[int]) -> dict[str, object] | None:
    """State the reduction's spread, or nothing at all where there was no figure to reduce."""

    if not scales:
        return None
    return {
        "maximum": quantity(scales[-1], "percent"),
        "median": quantity(median_high(scales), "percent"),
        "minimum": quantity(scales[0], "percent"),
    }


def _record(
    reference: ImageReference,
    published: dict[str, dict[str, object]],
    previews: dict[str, str] | None,
) -> dict[str, object]:
    resource = reference.resource
    packaged = resource.packaged
    return {
        "alt": reference.alt,
        "artifact": published.get(packaged.digest),
        "cover": reference.cover,
        **({} if reference.origin is None else {"origin": reference.origin}),
        "device_support": resource.support,
        "fits_panel": resource.fits,
        "packaged": {
            **measurement_facts(packaged.measurement),
            "byte_size": quantity(packaged.byte_size, "bytes"),
            "frames": quantity(packaged.frames, "frames"),
            "renderer": packaged.renderer,
            "scale": quantity(packaged.scale_percent, "percent"),
            "sha256": packaged.digest,
        },
        "previews": previews,
        "reference": reference.identifier,
        "source": {
            **measurement_facts(resource.measurement),
            "byte_size": quantity(resource.byte_size, "bytes"),
            "path": resource.source,
            "sha256": resource.digest,
        },
        "srcset_candidates": list(reference.candidates),
        "src": reference.src,
        "title": reference.title,
        "transform": resource.transform,
    }


def _cover_facts(preparation: ImagePreparation) -> dict[str, object] | None:
    """State whether the packaged cover is a Default Cover or a source `cover-image`."""

    cover = preparation.cover
    if cover is None or cover.origin is None:
        return None
    facts: dict[str, object] = {"origin": cover.origin}
    if cover.origin == DEFAULT_COVER:
        facts["title"] = cover.presented_title
        facts["author"] = cover.presented_author
    return facts


def _published(artifact: dict[str, object] | None) -> dict[str, dict[str, object]]:
    """Index the artifact's own measured resources by content, or state none where none is read."""

    if artifact is None:
        return {}
    resources = sequence(mapping(artifact.get("images")).get("resources"))
    published: dict[str, dict[str, object]] = {}
    for entry in resources:
        resource = mapping(entry)
        digest = text(resource.get("sha256"))
        if digest is not None:
            published[digest] = {
                "cover": resource.get("cover"),
                "measured_media_type": resource.get("measured_media_type"),
                "path": resource.get("path"),
                "referenced": resource.get("referenced"),
                "sha256": digest,
            }
    return published

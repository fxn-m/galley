"""Join measured image bytes to the Device Profile's verified support matrices."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import sha256

from galley.profile.compatibility import Assessment, Verdict, aggregate
from galley.epub.archive import EpubArchive
from galley.epub.reading import PackageReading
from galley.images.inline import inline_label
from galley.images.support import applies_to, device_support, support_for
from galley.images.measurement import (
    ImageMeasurement,
    ImageReference,
    image_references,
    measure_image,
    measurement_facts,
)
from galley.images.normalisation import IMAGE_ENCODING, IMAGE_FIT, image_rule, pillow_versions
from galley.images.preparation import ImagePreparation
from galley import observations as registry
from galley.observations import enabled_observations, observation
from galley.profile.loading import activation_entry, image_requirements
from galley.report.quantities import quantity, reported

JUDGED_BY_AGENT = (registry.DIAGRAM_TEXT, registry.COLOUR_MEANING)

TRUNCATED = "the resource bytes end before the format's own end marker"
NO_PRESERVATION = (
    "Audit was given no Canonical Document, so no source image reference set exists to map "
    "against. Package reference integrity is reported instead."
)
IMAGE_PREPARATION = "image-preparation"
IMAGES_PREPARED = (
    "Every referenced image was resolved from the source document's own directory and measured "
    "from its bytes. Compatible fitting source bytes are packaged unchanged when the profile "
    "activates preservation; anything else is decoded once into the profile-selected 8-bit PNG "
    "colour model, fitted without upscaling, and remeasured. Source, prepared, and viewing bytes "
    "are reported separately; conversion makes no claim that source colour meaning or fidelity "
    "survived."
)
IMAGES_ABSENT = (
    "The Canonical Document references no image. Nothing was resolved because there was nothing "
    "to resolve."
)


@dataclass(frozen=True)
class Image:
    """One measured image resource and how the package points at it."""

    path: str
    declared_media_type: str
    byte_size: int
    digest: str
    measurement: ImageMeasurement
    cover: bool
    referenced: bool

    @property
    def displayed(self) -> bool:
        """Report whether the device would ever put this resource on the panel."""

        return self.referenced or self.cover


@dataclass
class ImageEvidence:
    """Everything one pass over the artifact's images established."""

    images: list[Image] = field(default_factory=list[Image])
    references: list[ImageReference] = field(default_factory=list[ImageReference])
    members: frozenset[str] = frozenset()

    @property
    def displayed(self) -> list[Image]:
        return [image for image in self.images if image.displayed]


def gather_images(archive: EpubArchive, reading: PackageReading) -> ImageEvidence:
    """Measure every declared image resource from its bytes, in stable path order."""

    references = [
        reference for path, root in reading.documents for reference in image_references(root, path)
    ]
    targets = {reference.target for reference in references}
    images: list[Image] = []
    for path, declared in sorted(reading.resources):
        data = archive.read(path)
        if data is None:
            continue
        measurement = measure_image(data)
        if measurement.media_type is None and not declared.startswith("image/"):
            continue
        images.append(
            Image(
                path=path,
                declared_media_type=declared,
                byte_size=len(data),
                digest=sha256(data).hexdigest(),
                measurement=measurement,
                cover=path == reading.cover_path,
                referenced=path in targets,
            )
        )
    return ImageEvidence(images=images, references=references, members=archive.names)


def assess(profile: dict[str, object], evidence: ImageEvidence) -> dict[str, Assessment]:
    """Return one Requirement Verdict per image requirement from measured bytes."""

    assessments: dict[str, Assessment] = {}
    for requirement_id in image_requirements(profile):
        subject = [
            image
            for image in evidence.displayed
            if applies_to(profile, requirement_id, image.measurement)
        ]
        if not subject:
            assessments[requirement_id] = Assessment(verdict="not_applicable", applicable=False)
            continue
        results: list[Verdict] = [
            support_for(profile, requirement_id, image.measurement) for image in subject
        ]
        assessments[requirement_id] = Assessment(
            verdict=aggregate(results),
            applicable=True,
            measurement=_tally(results, len(subject)),
        )
    return assessments


def image_facts(profile: dict[str, object], evidence: ImageEvidence) -> dict[str, object]:
    """Describe every measured image, its references, and what audit does not claim."""

    resources = [_resource(profile, image) for image in evidence.images]
    unsupported = [
        resource
        for resource in resources
        if resource["displayed"] is True and resource["device_support"] != "true"
    ]
    return {
        "image_preservation": {"claimed": False, "reason": NO_PRESERVATION},
        "not_device_verified": quantity(len(unsupported), "images"),
        "references": [
            {
                "alt": reference.alt,
                "document": reference.document,
                "resolved": reference.target is not None and reference.target in evidence.members,
                "src": inline_label(reference.src),
                "target": reference.target,
            }
            for reference in evidence.references
        ],
        "resources": resources,
        "unresolved_references": [
            {"document": reference.document, "src": inline_label(reference.src)}
            for reference in evidence.references
            if reference.target is None or reference.target not in evidence.members
        ],
    }


def image_transform(profile: dict[str, object], preparation: ImagePreparation) -> dict[str, object]:
    """State what image preparation resolved and the profile limits it applied."""

    encoding = activation_entry(profile, IMAGE_ENCODING)
    fit = activation_entry(profile, IMAGE_FIT)
    rule = image_rule(profile)
    return {
        "name": IMAGE_PREPARATION,
        "fired": bool(preparation.references),
        "activation": IMAGE_ENCODING,
        "device_judged": encoding.get("device_judged") is True,
        "justified_by": encoding.get("justified_by"),
        "fit": {
            "activation": IMAGE_FIT,
            "device_judged": fit.get("device_judged") is True,
            "justified_by": fit.get("justified_by"),
            "max_height": _limit(rule.max_height),
            "max_width": _limit(rule.max_width),
        },
        "normalised": quantity(preparation.normalised, "images"),
        "preserved": quantity(preparation.preserved, "images"),
        "references": quantity(len(preparation.references), "references"),
        "resources": quantity(len(preparation.resources), "images"),
        "tools": pillow_versions(),
        "note": IMAGES_PREPARED if preparation.references else IMAGES_ABSENT,
    }


def image_observations(
    profile: dict[str, object], evidence: ImageEvidence
) -> list[dict[str, object]]:
    """Emit the image observations this Device Profile activates."""

    enabled = enabled_observations(profile)
    displayed = evidence.displayed
    applicable = bool(displayed) or bool(evidence.references)
    unrenderable = [
        image for image in displayed if device_support(profile, image.measurement) != "true"
    ]
    results: list[dict[str, object]] = []
    if registry.UNRENDERABLE_IMAGES in enabled:
        results.append(
            observation(
                registry.UNRENDERABLE_IMAGES,
                applicability=bool(displayed),
                fired=bool(unrenderable) if displayed else None,
                measurement=quantity(len(unrenderable), "images"),
                locations=[image.path for image in unrenderable],
                note="Measured artifact encodings joined to every applicable support matrix.",
            )
        )
    if registry.ALT_TEXT_FALLBACK in enabled:
        blank = _blank_alt(evidence, {image.path for image in unrenderable})
        results.append(
            observation(
                registry.ALT_TEXT_FALLBACK,
                applicability=applicable,
                fired=bool(blank) if applicable else None,
                measurement=quantity(len(blank), "images"),
                locations=blank,
                note="Fires only where an unrenderable image also lacks alt text to fall back on.",
            )
        )
    results.extend(
        observation(
            name,
            applicability=applicable,
            fired=None,
            measurement=None,
            locations=[image.path for image in displayed],
            note="Audit holds no agent judgement and no retained source image.",
        )
        for name in JUDGED_BY_AGENT
        if name in enabled
    )
    return results


def _blank_alt(evidence: ImageEvidence, unrenderable: set[str]) -> list[str]:
    return sorted(
        {
            reference.target
            for reference in evidence.references
            if reference.target is not None
            and reference.target in unrenderable
            and not (reference.alt or "").strip()
        }
    )


def _resource(profile: dict[str, object], image: Image) -> dict[str, object]:
    facts: dict[str, object] = {
        **measurement_facts(image.measurement),
        "byte_size": quantity(image.byte_size, "bytes"),
        "cover": image.cover,
        "declared_media_type": image.declared_media_type,
        "device_support": device_support(profile, image.measurement),
        "displayed": image.displayed,
        "path": image.path,
        "referenced": image.referenced,
        "sha256": image.digest,
    }
    if not image.measurement.intact:
        facts["note"] = TRUNCATED
    return facts


def _tally(results: Sequence[Verdict], total: int) -> dict[str, object]:
    measurement = quantity(total, "images")
    measurement["definition"] = "images measured from artifact bytes and joined to profile support"
    measurement["compatible"] = quantity(results.count("true"), "images")
    measurement["incompatible"] = quantity(results.count("false"), "images")
    measurement["unlisted"] = quantity(results.count("unknown"), "images")
    return measurement


def _limit(value: int | None) -> dict[str, object] | None:
    return None if value is None else reported(value, "pixels")

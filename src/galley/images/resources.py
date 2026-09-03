"""Turn one image reference into the bytes preparation hands to the writer.

Resolution, measurement and the preserve-or-normalise decision happen here, one reference at a
time: measure the referenced bytes first, preserve them when the profile
verifies the encoding and the panel already fits, and otherwise transform once. Nothing is
decided by a filename, and the file written into the packaging workspace always holds the exact
bytes measured — preserved or produced.
"""

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from galley.profile.compatibility import Verdict
from galley.images.normalisation import ImageRule, image_rule, normalise
from galley.images.support import device_support
from galley.images.measurement import ImageMeasurement, measure_image
from galley.images.resolution import ResourceOrigin, resolved_bytes

PRESERVED = "preserved"
NORMALISED = "normalised"
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png"}
PNG_EXTENSION = ".png"

REASONS = {
    "missing-resource": "the referenced file does not exist",
    "unreadable-resource": "the referenced file could not be read",
    "unfetchable-resource": "the referenced resource could not be retrieved from the page",
    "oversize-resource": "the referenced resource is larger than Galley will read",
    "unsupported-location": "the reference does not name a resource this source can resolve",
    "malformed-inline-reference": "the inline reference is not a data URI",
    "undecodable-inline-data": "the inline reference's payload does not decode",
    "unmeasurable-bytes": "the bytes are not an image in a format Galley measures",
    "decode-failure": "the image could not be decoded for conversion",
    "render-failure": "the SVG renderer could not rasterise this image",
    "renderer-unavailable": "the pinned SVG renderer is not installed",
    "rasterisation-not-activated": "this Device Profile does not activate SVG rasterisation",
    "unexpected-encoding": "the conversion did not produce the encoding the profile asks for",
}


@dataclass(frozen=True)
class Packaged:
    """The file handed to the writer, and what its bytes measure as."""

    path: Path
    digest: str
    byte_size: int
    measurement: ImageMeasurement
    scale_percent: int = 100
    frames: int = 1
    renderer: dict[str, object] | None = None


@dataclass(frozen=True)
class PackagedResource:
    """One resolved source resource, what the profile makes of it, and what was packaged."""

    source: str
    digest: str
    byte_size: int
    measurement: ImageMeasurement
    support: Verdict
    fits: bool
    transform: str
    packaged: Packaged


@dataclass
class ResourcePreparation:
    """One image pass's resolution, profile rules and content-based resource reuse.

    Body references and the cover share this store. The first resource for a source digest
    supplies the packaged identity, preserving reading-order names when a cover reuses a figure.
    """

    profile: dict[str, object]
    origin: ResourceOrigin
    workspace: Path
    prepared: dict[str, PackagedResource] = field(default_factory=dict[str, PackagedResource])
    rule: ImageRule = field(init=False)

    def __post_init__(self) -> None:
        self.rule = image_rule(self.profile)

    def resolve(self, src: str, name: str) -> PackagedResource | str:
        resolved = resolved_bytes(self.origin, src)
        if isinstance(resolved, str):
            return resolved
        return self.hold(resolved.data, resolved.display, name)

    def hold(self, data: bytes, display: str, name: str) -> PackagedResource | str:
        resource = _packaged_bytes(
            data,
            display=display,
            profile=self.profile,
            rule=self.rule,
            workspace=self.workspace,
            name=name,
        )
        if isinstance(resource, str):
            return resource
        return self.prepared.setdefault(resource.digest, resource)


def _packaged_bytes(
    data: bytes,
    *,
    display: str,
    profile: dict[str, object],
    rule: ImageRule,
    workspace: Path,
    name: str,
) -> PackagedResource | str:
    """Measure and package bytes already in hand, or name the reason they produced none."""

    measurement = measure_image(data)
    if measurement.media_type is None:
        return "unmeasurable-bytes"
    support = device_support(profile, measurement)
    fits = rule.fits(measurement)
    stated = _stated(rule, measurement, support, fits=fits)
    if stated is not None:
        packaged = _written(data, workspace / f"{name}{stated}", measurement)
        return _resource(data, display, measurement, support, fits, PRESERVED, packaged)
    transformed = normalise(data, measurement, rule, workspace / name)
    if transformed.data is None or transformed.measurement is None:
        return transformed.reason or "decode-failure"
    packaged = _written(
        transformed.data,
        workspace / f"{name}{PNG_EXTENSION}",
        transformed.measurement,
        scale_percent=transformed.scale_percent,
        frames=transformed.frames,
        renderer=None if transformed.renderer is None else transformed.renderer.facts,
    )
    return _resource(data, display, measurement, support, fits, NORMALISED, packaged)


def _stated(
    rule: ImageRule, measurement: ImageMeasurement, support: Verdict, *, fits: bool
) -> str | None:
    """Name the suffix these bytes would be preserved under, or nothing where they would not be.

    A compatible encoding Galley cannot name this way is normalised instead of preserved, rather
    than packaged under a suffix nobody chose.
    """

    if not (rule.preserve_compatible and support == "true" and fits and measurement.intact):
        return None
    return EXTENSIONS.get(measurement.media_type or "")


def _written(
    data: bytes,
    destination: Path,
    measurement: ImageMeasurement,
    *,
    scale_percent: int = 100,
    frames: int = 1,
    renderer: dict[str, object] | None = None,
) -> Packaged:
    """Write the exact bytes the writer will package, so the book's resource is the measured one."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    _ = destination.write_bytes(data)
    return Packaged(
        path=destination,
        digest=sha256(data).hexdigest(),
        byte_size=len(data),
        measurement=measurement,
        scale_percent=scale_percent,
        frames=frames,
        renderer=renderer,
    )


def _resource(
    data: bytes,
    display: str,
    measurement: ImageMeasurement,
    support: Verdict,
    fits: bool,
    transform: str,
    packaged: Packaged,
) -> PackagedResource:
    return PackagedResource(
        source=display,
        digest=sha256(data).hexdigest(),
        byte_size=len(data),
        measurement=measurement,
        support=support,
        fits=fits,
        transform=transform,
        packaged=packaged,
    )

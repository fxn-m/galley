"""Turn one image reference into the bytes preparation hands to the writer.

Resolution, measurement and the preserve-or-normalise decision happen here, one reference at a
time: measure the referenced bytes first, preserve them when the profile
verifies the encoding and the panel already fits, and otherwise transform once. Nothing is
decided by a filename, and the file written into the packaging workspace always holds the exact
bytes measured — preserved or produced.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import SplitResult, unquote, urlsplit

from galley.profile.compatibility import Verdict
from galley.images.inline import inline_bytes, inline_label, is_inline
from galley.images.normalisation import ImageRule, normalise
from galley.images.support import device_support
from galley.images.measurement import ImageMeasurement, measure_image
from galley.locations import display_path
from galley.tools.fetching import fetch_resource, fetchable

PRESERVED = "preserved"
NORMALISED = "normalised"
LOCAL_SCHEMES = frozenset({"", "file"})
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
class ResourceOrigin:
    """Where one Canonical Document's image references resolve from.

    A Markdown source resolves relative references against its own directory and retrieves
    nothing; an Article-Like Page has no directory and its references were already resolved to
    absolute locations by extraction, so it retrieves them from the page it came from. Keeping
    both in one value is what lets every step after resolution be the same step.
    """

    directory: Path | None = None
    retrieves: bool = False


@dataclass(frozen=True)
class Resolved:
    """The bytes one reference names, and the name they are reported under."""

    data: bytes
    display: str


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


def packaged_resource(
    src: str,
    *,
    profile: dict[str, object],
    rule: ImageRule,
    origin: ResourceOrigin,
    workspace: Path,
    name: str,
) -> PackagedResource | str:
    """Resolve, measure and package one reference's bytes, or name the reason it produced none."""

    resolved = _resolved(origin, src)
    if isinstance(resolved, str):
        return resolved
    data = resolved.data
    measurement = measure_image(data)
    if measurement.media_type is None:
        return "unmeasurable-bytes"
    support = device_support(profile, measurement)
    fits = rule.fits(measurement)
    stated = _stated(rule, measurement, support, fits=fits)
    if stated is not None:
        packaged = _written(data, workspace / f"{name}{stated}", measurement)
        return _resource(data, resolved.display, measurement, support, fits, PRESERVED, packaged)
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
    return _resource(data, resolved.display, measurement, support, fits, NORMALISED, packaged)


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


def _resolved(origin: ResourceOrigin, src: str) -> Resolved | str:
    """Produce the bytes one reference names, or the reason this source cannot produce them.

    An inline reference is answered before either origin, because it belongs to neither: its
    bytes travelled inside the document, so the same answer is right whichever route the document
    arrived by, and no socket and no file is involved.

    A retrieving origin resolves what it can retrieve and nothing else. Extraction has already
    resolved every reference against the page's own address, so anything left that is not an
    http or https locator is not part of the page — and a page must never be able to name a path
    on the machine preparing it and have those bytes read into a book. A data URI names no path,
    so admitting it takes nothing away from that.
    """

    if is_inline(src):
        inline = inline_bytes(src)
        return inline if isinstance(inline, str) else Resolved(inline, inline_label(src))
    split = urlsplit(src)
    if origin.retrieves:
        if not fetchable(split.scheme):
            return "unsupported-location"
        fetched = fetch_resource(src)
        if fetched.data is None:
            return fetched.reason or "unfetchable-resource"
        return Resolved(fetched.data, src)
    location = _location(origin.directory, split)
    if location is None:
        return "unsupported-location"
    try:
        return Resolved(location.read_bytes(), display_path(location))
    except FileNotFoundError:
        return "missing-resource"
    except OSError:
        return "unreadable-resource"


def _location(directory: Path | None, split: SplitResult) -> Path | None:
    """Resolve one reference against the source document's own directory, or refuse to guess.

    A source that is not a local file has no directory to resolve against, so a relative
    reference is unresolvable rather than resolvable somewhere arbitrary.
    """

    if split.scheme.lower() not in LOCAL_SCHEMES or split.netloc:
        return None
    path = unquote(split.path)
    if not path:
        return None
    if Path(path).is_absolute():
        return Path(path)
    return None if directory is None else directory / path

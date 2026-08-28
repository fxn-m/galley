"""Measure image encodings from actual resource bytes, never from declarations."""

from dataclasses import dataclass
from struct import unpack
from xml.etree.ElementTree import Element

from galley.epub.archive import classify_reference
from galley.report.quantities import quantity

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8"
JPEG_END = b"\xff\xd9"
GIF_SIGNATURES = (b"GIF87a", b"GIF89a")
GIF_TRAILER = b";"
RIFF = b"RIFF"
WEBP = b"WEBP"
XHTML_NS = "http://www.w3.org/1999/xhtml"

PNG_MEDIA_TYPE = "image/png"
JPEG_MEDIA_TYPE = "image/jpeg"
ALPHA_COLOUR_TYPES = frozenset({4, 6})
BASELINE_MARKERS = frozenset({0xC0, 0xC1})
PROGRESSIVE_MARKERS = frozenset({0xC2, 0xC6, 0xCA, 0xCE})
SOF_MARKERS = BASELINE_MARKERS | PROGRESSIVE_MARKERS | frozenset({0xC3, 0xC5, 0xC7, 0xC9, 0xCB})
STANDALONE_MARKERS = frozenset({0x01, *range(0xD0, 0xDA)})
COLOUR_MODELS = {1: "greyscale", 3: "rgb", 4: "cmyk"}


@dataclass(frozen=True)
class ImageMeasurement:
    """Every encoding fact one image's bytes establish on their own."""

    media_type: str | None
    intact: bool = False
    width: int | None = None
    height: int | None = None
    sample_depth: int | None = None
    colour_type: int | None = None
    scan_mode: str | None = None
    colour_model: str | None = None
    alpha: bool | None = None


@dataclass(frozen=True)
class ImageReference:
    """One `img` element a content document points at."""

    document: str
    src: str
    target: str | None
    alt: str | None


def measure_image(data: bytes) -> ImageMeasurement:
    """Read one resource's encoding facts from its bytes alone."""

    if data.startswith(PNG_SIGNATURE):
        return _png(data)
    if data.startswith(JPEG_SIGNATURE):
        return _jpeg(data)
    if data.startswith(GIF_SIGNATURES):
        return _gif(data)
    if data[:4] == RIFF and data[8:12] == WEBP:
        return ImageMeasurement(media_type="image/webp", intact=_riff_intact(data))
    if _is_svg(data):
        return ImageMeasurement(media_type="image/svg+xml", intact=True)
    return ImageMeasurement(media_type=None)


def measurement_facts(measurement: ImageMeasurement) -> dict[str, object]:
    """State one image exactly as its own bytes established it.

    Both sides of preparation say this in the same words: the source resource Galley resolved and
    the resource `audit` measured in the published book. Galley compares them, and a
    comparison between two differently-shaped records is a comparison nobody can read.
    """

    return {
        "alpha": measurement.alpha,
        "colour_model": measurement.colour_model,
        "colour_type": optional(measurement.colour_type, "colour type"),
        "height": optional(measurement.height, "pixels"),
        "intact": measurement.intact,
        "measured_media_type": measurement.media_type,
        "sample_depth": optional(measurement.sample_depth, "bits"),
        "scan_mode": measurement.scan_mode,
        "width": optional(measurement.width, "pixels"),
    }


def optional(value: int | None, unit: str) -> dict[str, object] | None:
    """Wrap one measured dimension, or state nothing where the bytes established nothing."""

    return None if value is None else quantity(value, unit)


def image_references(root: Element, document: str) -> list[ImageReference]:
    """Collect every image one content document references, with its alt text."""

    references: list[ImageReference] = []
    for element in root.iter(f"{{{XHTML_NS}}}img"):
        src = element.get("src")
        if src is None:
            continue
        kind, target = classify_reference(document, src)
        references.append(
            ImageReference(
                document=document,
                src=src,
                target=target if kind == "in-book" else None,
                alt=element.get("alt"),
            )
        )
    return references


def _png(data: bytes) -> ImageMeasurement:
    """Walk the PNG chunk stream so a truncated file is never read as a whole one."""

    header: tuple[int, int, int, int] | None = None
    transparency = False
    intact = False
    position = len(PNG_SIGNATURE)
    while position + 8 <= len(data):
        length = unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        start = position + 8
        end = start + length
        if end + 4 > len(data):
            break
        if kind == b"IHDR" and length >= 13:
            width, height = unpack(">II", data[start : start + 8])
            header = (width, height, data[start + 8], data[start + 9])
        elif kind == b"tRNS":
            transparency = True
        elif kind == b"IEND":
            intact = True
            break
        position = end + 4
    if header is None:
        return ImageMeasurement(media_type=PNG_MEDIA_TYPE)
    width, height, sample_depth, colour_type = header
    return ImageMeasurement(
        media_type=PNG_MEDIA_TYPE,
        intact=intact,
        width=width,
        height=height,
        sample_depth=sample_depth,
        colour_type=colour_type,
        alpha=colour_type in ALPHA_COLOUR_TYPES or transparency,
    )


def _jpeg(data: bytes) -> ImageMeasurement:
    intact = data.endswith(JPEG_END)
    position = 2
    length = len(data)
    while position + 3 < length:
        if data[position] != 0xFF:
            position += 1
            continue
        marker = data[position + 1]
        if marker in STANDALONE_MARKERS or marker == 0xFF:
            position += 2
            continue
        segment = unpack(">H", data[position + 2 : position + 4])[0]
        if marker in SOF_MARKERS and position + 10 <= length:
            return _jpeg_frame(data, position, marker, intact=intact)
        position += 2 + segment
    return ImageMeasurement(media_type=JPEG_MEDIA_TYPE, intact=intact)


def _jpeg_frame(data: bytes, position: int, marker: int, *, intact: bool) -> ImageMeasurement:
    height, width = unpack(">HH", data[position + 5 : position + 9])
    return ImageMeasurement(
        media_type=JPEG_MEDIA_TYPE,
        intact=intact,
        width=width,
        height=height,
        sample_depth=data[position + 4],
        scan_mode="baseline" if marker in BASELINE_MARKERS else "progressive",
        colour_model=COLOUR_MODELS.get(data[position + 9]),
        alpha=False,
    )


def _gif(data: bytes) -> ImageMeasurement:
    if len(data) < 10:
        return ImageMeasurement(media_type="image/gif")
    width, height = unpack("<HH", data[6:10])
    return ImageMeasurement(
        media_type="image/gif",
        intact=data.endswith(GIF_TRAILER),
        width=width,
        height=height,
    )


def _riff_intact(data: bytes) -> bool:
    if len(data) < 12:
        return False
    declared = unpack("<I", data[4:8])[0]
    return declared == len(data) - 8


def _is_svg(data: bytes) -> bool:
    head = data[:512].lstrip()
    if not head.startswith(b"<"):
        return False
    return b"<svg" in data[:2048].lower()

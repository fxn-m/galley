"""Turn one image the device cannot render into the safe form the Device Profile names.

The operation decodes once, preserves alpha, converts to an 8-bit profile-selected PNG, fits
inside the panel without upscaling, and rasterises SVG rather than packaging it. The tools are
Pillow for raster work because it originates no ancillary PNG chunk, and resvg for SVG
because nothing else keeps its renderer off the machine's own font and delegate configuration.

Neither library is asked what it produced. The output is remeasured with Galley's own stdlib
reader and checked against the colour type the profile asked for, because a decoded object is a
transformed view of the bytes and the Report's facts are about the bytes.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, __version__ as pillow_version, features

from galley.json_reading import integer, mapping, text
from galley.images.measurement import ImageMeasurement, measure_image
from galley.profile.loading import activation
from galley.tools.resvg import Rendering, rasterise

IMAGE_ENCODING = "image_encoding"
IMAGE_FIT = "image_fit"
PRESERVE_BYTES = "preserve_compatible_fitting_bytes"
RASTERIZE_SVG = "rasterize_svg"
MAX_WIDTH = "max_width_px"
MAX_HEIGHT = "max_height_px"
COLOUR_MODEL = "colour_model"
OPAQUE_TYPE = "opaque_colour_type"
ALPHA_TYPE = "alpha_colour_type"
VIEWING_LEVELS = "viewing_levels"

SVG_MEDIA_TYPE = "image/svg+xml"
PNG_FORMAT = "PNG"
GREY = "L"
GREY_ALPHA = "LA"
RGB = "RGB"
RGB_ALPHA = "RGBA"
OUTPUT_MODES = {
    "grayscale": (GREY, GREY_ALPHA),
    "rgb": (RGB, RGB_ALPHA),
}
ALPHA_MODES = frozenset({"LA", "PA", "RGBA", "La"})
TRANSPARENCY = "transparency"
COMPRESS_LEVEL = 9
SAMPLE_DEPTH = 8
LEVEL_MAXIMUM = 255
# Every accessor Pillow needs to state one version, chosen per name: WebP is a module, not a
# feature or a codec, so the obvious call raises rather than answering.
FEATURES = ("zlib_ng", "libjpeg_turbo")
CODECS = ("jpg", "zlib")
MODULES = ("webp",)


@dataclass(frozen=True)
class ImageRule:
    """Everything a Device Profile states about images, read once from its activations.

    Device values live in profile data. This rule carries them; nothing in preparation or
    normalisation restates a pixel count or a colour type of its own.
    """

    max_width: int | None
    max_height: int | None
    preserve_compatible: bool
    rasterize_svg: bool
    colour_model: str | None
    opaque_colour_type: int | None
    alpha_colour_type: int | None
    viewing_levels: int | None

    def fits(self, measurement: ImageMeasurement) -> bool:
        """Say whether these bytes already sit inside the panel the profile describes."""

        measured = ((measurement.width, self.max_width), (measurement.height, self.max_height))
        return all(
            limit is None or (value is not None and value <= limit) for value, limit in measured
        )

    def colour_type(self, *, alpha: bool) -> int | None:
        """Name the PNG colour type this profile asks for, by whether alpha survived."""

        return self.alpha_colour_type if alpha else self.opaque_colour_type

    def mode(self, *, alpha: bool) -> str | None:
        """Translate the profile's generic colour model to a Pillow output mode."""

        modes = OUTPUT_MODES.get(self.colour_model or "")
        return None if modes is None else modes[1 if alpha else 0]


@dataclass(frozen=True)
class Normalisation:
    """One transform attempt: the bytes it wrote, what they measure as, and what ran."""

    data: bytes | None = None
    measurement: ImageMeasurement | None = None
    frames: int = 1
    scale_percent: int = 100
    renderer: Rendering | None = None
    reason: str | None = None


def image_rule(profile: dict[str, object]) -> ImageRule:
    """Take the panel geometry, the safe encoding and the preservation decision from the profile."""

    fit = mapping(activation(profile, IMAGE_FIT))
    encoding = mapping(activation(profile, IMAGE_ENCODING))
    return ImageRule(
        max_width=integer(fit.get(MAX_WIDTH)),
        max_height=integer(fit.get(MAX_HEIGHT)),
        preserve_compatible=encoding.get(PRESERVE_BYTES) is True,
        rasterize_svg=encoding.get(RASTERIZE_SVG) is True,
        colour_model=text(encoding.get(COLOUR_MODEL)),
        opaque_colour_type=integer(encoding.get(OPAQUE_TYPE)),
        alpha_colour_type=integer(encoding.get(ALPHA_TYPE)),
        viewing_levels=integer(encoding.get(VIEWING_LEVELS)),
    )


def normalise(
    data: bytes, measurement: ImageMeasurement, rule: ImageRule, workspace: Path
) -> Normalisation:
    """Convert one image into the profile's safe form, or name the reason it could not be."""

    rendering: Rendering | None = None
    if measurement.media_type == SVG_MEDIA_TYPE:
        if not rule.rasterize_svg:
            return Normalisation(reason="rasterisation-not-activated")
        rendering = rasterise(data, workspace)
        if rendering.data is None:
            return Normalisation(renderer=rendering, reason=_render_failure(rendering))
        data = rendering.data
    try:
        with Image.open(BytesIO(data)) as opened:
            written, frames, scale, alpha = _converted(opened, rule)
    except OSError, ValueError, Image.DecompressionBombError:
        return Normalisation(renderer=rendering, reason="decode-failure")
    produced = measure_image(written)
    expected = rule.colour_type(alpha=alpha)
    if produced.colour_type != expected or produced.sample_depth != SAMPLE_DEPTH:
        return Normalisation(renderer=rendering, reason="unexpected-encoding")
    return Normalisation(
        data=written,
        measurement=produced,
        frames=frames,
        scale_percent=scale,
        renderer=rendering,
    )


def _converted(opened: Image.Image, rule: ImageRule) -> tuple[bytes, int, int, bool]:
    """Decode one frame, keep alpha, fit the panel without upscaling, and encode PNG."""

    frames = int(getattr(opened, "n_frames", 1))
    opened.seek(0)
    alpha = _transparent(opened)
    mode = rule.mode(alpha=alpha)
    if mode is None:
        raise ValueError("unknown output colour model")
    image = opened.convert(mode)
    width, height = image.size
    target = _target(width, height, rule)
    if target != (width, height):
        image = ImageOps.contain(image, target, Image.Resampling.LANCZOS)
    destination = BytesIO()
    image.save(
        destination,
        format=PNG_FORMAT,
        compress_level=COMPRESS_LEVEL,
        icc_profile=None,
        transparency=None,
    )
    scale = 100 if width == 0 else target[0] * 100 // width
    return destination.getvalue(), frames, scale, alpha


def _transparent(opened: Image.Image) -> bool:
    """Say whether this image actually carries transparency, not merely a channel for it.

    Galley preserves alpha; it does not add an alpha channel where nothing is transparent. A
    rasterised SVG arrives as RGBA whether or not anything in it is see-through, and packaging
    that as colour type 4 would report transparency the source never had.
    """

    if TRANSPARENCY in opened.info:
        return True
    if opened.mode not in ALPHA_MODES:
        return False
    channel = opened.convert("RGBA").getchannel("A")
    return min(channel.tobytes()) < LEVEL_MAXIMUM


def _target(width: int, height: int, rule: ImageRule) -> tuple[int, int]:
    """Fit inside the panel while preserving aspect ratio, and never enlarge what already fits."""

    limits = ((width, rule.max_width), (height, rule.max_height))
    ratios = [limit / measured for measured, limit in limits if limit is not None and measured]
    scale = min([1.0, *ratios])
    if scale >= 1.0:
        return width, height
    return max(1, int(width * scale)), max(1, int(height * scale))


def _render_failure(rendering: Rendering) -> str:
    return "renderer-unavailable" if rendering.version is None else "render-failure"


def pillow_versions() -> dict[str, str]:
    """Name every version behind Pillow's PNG bytes, not only Pillow's own.

    Pillow's wheels have shipped zlib-ng since 11.1.0, so the deflate implementation is a second
    variable behind one version number. Each name is read through the
    accessor that answers for it; asking the wrong one raises instead of returning a version.
    """

    stated = {"pillow": pillow_version}
    for name in FEATURES:
        stated[name] = str(features.version_feature(name))
    for name in CODECS:
        stated[f"{name}-codec"] = str(features.version_codec(name))
    for name in MODULES:
        stated[name] = str(features.version_module(name))
    return stated

"""Render the deterministic preview material an agent judges images from.

Two of the four image observations are the agent's to settle, and neither can be settled from
numbers: whether a diagram's text is still legible at panel size, and whether meaning carried by
colour survived the conversion path. The agent gets previews instead — a source preview,
the prepared bytes, and a viewing preview quantised to the panel's own level count.

The viewing preview is evidence about display, never about the artifact: the packaged resource
keeps its full 8-bit range, and nothing here is written into the book.
"""

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from galley.images.normalisation import (
    COMPRESS_LEVEL,
    GREY,
    LEVEL_MAXIMUM,
    PNG_FORMAT,
    ImageRule,
)
from galley.images.preparation import ImagePreparation, ImageReference
from galley.observations import COLOUR_MEANING, DIAGRAM_TEXT, enabled_observations, observation
from galley.report.quantities import quantity

PREVIEWS = "previews"
SOURCE = "source"
PREPARED = "prepared"
VIEWING = "viewing"
PREVIEW_NOTE = (
    "A source preview, the prepared bytes, and a viewing preview quantised to the panel's own "
    "level count. The viewing preview shows how the device would present these bytes; it is not "
    "the resource the book carries."
)


@dataclass(frozen=True)
class Preview:
    """One reference's preview material, named for the evidence directory."""

    reference: str
    files: dict[str, str]
    payloads: dict[str, bytes]


def previews(preparation: ImagePreparation, rule: ImageRule) -> list[Preview]:
    """Render every reference's previews, skipping any the renderers cannot produce."""

    rendered: list[Preview] = []
    for reference in preparation.references:
        preview = _preview(reference, rule)
        if preview is not None:
            rendered.append(preview)
    return rendered


def preview_payloads(rendered: list[Preview]) -> dict[str, bytes]:
    """Collect every preview file one run would write, keyed by its name in the bundle."""

    return {name: payload for preview in rendered for name, payload in preview.payloads.items()}


def preview_locations(rendered: list[Preview]) -> list[str]:
    """Name every preview file, for the observations an agent judges from them."""

    return [f"{PREVIEWS}/{name}" for preview in rendered for name in preview.payloads]


def preview_files(rendered: list[Preview]) -> dict[str, dict[str, str]]:
    """Map each reference to the previews it produced, for its own Report record."""

    return {preview.reference: preview.files for preview in rendered}


def _preview(reference: ImageReference, rule: ImageRule) -> Preview | None:
    """Render what can be rendered for one reference, and leave out what cannot.

    A source preview is a decode of the source's own bytes, so a format Pillow does not read —
    an SVG, before resvg has rasterised it — yields none. The prepared and viewing previews still
    do, and dropping all three because one is impossible would leave the agent with nothing.
    """

    resource = reference.resource
    stem = reference.identifier
    prepared = _read(resource.packaged.path)
    if prepared is None:
        return None
    rendered = (
        (SOURCE, f"{stem}-{SOURCE}.png", _rendered(_fitted, _read(Path(resource.source)), rule)),
        (PREPARED, f"{stem}-{PREPARED}{resource.packaged.path.suffix}", prepared),
        (VIEWING, f"{stem}-{VIEWING}.png", _rendered(_viewing, prepared, rule)),
    )
    payloads = {name: payload for _, name, payload in rendered if payload is not None}
    files = {kind: f"{PREVIEWS}/{name}" for kind, name, payload in rendered if payload is not None}
    return Preview(reference=stem, files=files, payloads=payloads)


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _rendered(
    render: Callable[[bytes, ImageRule], bytes | None], data: bytes | None, rule: ImageRule
) -> bytes | None:
    """Run one renderer over bytes it may not be able to read, and say nothing where it cannot."""

    if data is None:
        return None
    try:
        return render(data, rule)
    except OSError, ValueError, Image.DecompressionBombError:
        return None


def _fitted(data: bytes, rule: ImageRule) -> bytes | None:
    """Show the source at panel size with its own colour intact, for the colour comparison."""

    with Image.open(BytesIO(data)) as opened:
        opened.seek(0)
        image = opened.convert("RGB" if opened.mode not in {"L", "LA"} else opened.mode)
        return _encoded(_contained(image, rule))


def _viewing(data: bytes, rule: ImageRule) -> bytes | None:
    """Quantise the prepared bytes to the number of levels the Device Profile states.

    A profile that states no level count gets no viewing preview rather than one rendered at a
    level count Galley chose for it.
    """

    levels = rule.viewing_levels
    if levels is None or levels < 2:
        return None
    step = LEVEL_MAXIMUM / (levels - 1)
    table = bytes(round(round(value / step) * step) for value in range(LEVEL_MAXIMUM + 1))
    with Image.open(BytesIO(data)) as opened:
        opened.seek(0)
        image = _contained(opened.convert(GREY), rule)
        levelled = bytes(table[value] for value in image.tobytes())
        return _encoded(Image.frombytes(GREY, image.size, levelled))


def _contained(image: Image.Image, rule: ImageRule) -> Image.Image:
    width, height = rule.max_width, rule.max_height
    if width is None or height is None or (image.width <= width and image.height <= height):
        return image
    return ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)


def _encoded(image: Image.Image) -> bytes:
    destination = BytesIO()
    image.save(
        destination,
        format=PNG_FORMAT,
        compress_level=COMPRESS_LEVEL,
        icc_profile=None,
        transparency=None,
    )
    return destination.getvalue()


def preview_observations(
    profile: dict[str, object], rendered: list[Preview]
) -> list[dict[str, object]]:
    """Offer the agent's two image observations the material they are judged from.

    Both observations belong to the agent, so the CLI states applicability, evidence and nothing
    else. The entries replace the artifact layer's, which knows the resources but not the
    previews, rather than being appended beside them.
    """

    enabled = enabled_observations(profile)
    return [
        observation(
            name,
            applicability=bool(rendered),
            fired=None,
            measurement=quantity(len(rendered), "images"),
            locations=preview_locations(rendered),
            note=PREVIEW_NOTE,
        )
        for name in (COLOUR_MEANING, DIAGRAM_TEXT)
        if name in enabled and rendered
    ]

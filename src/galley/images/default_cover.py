"""Compose a deterministic Default Cover from a work's title and author.

A Default Cover is title-and-author presentation, not Cover Artwork and not a title page. It
uses the Device Profile's cover canvas and the bundled Atkinson Hyperlegible face. Preparation
rasterises the SVG through the same renderer it uses for any other cover.
"""

from collections.abc import Callable
from dataclasses import dataclass
from xml.sax.saxutils import escape

from galley.document.baseline import inline_text
from galley.images.inline import inline_label
from galley.images.resources import PackagedResource
from galley.json_reading import integer, mapping, sequence, text
from galley.profile.loading import activation

DEFAULT_COVER = "default-cover"
SOURCE_COVER = "source-cover-image"
COVER = "cover-image"

Resolve = Callable[[str, str], PackagedResource | str]
Hold = Callable[[bytes, str, str], PackagedResource | str]


@dataclass(frozen=True)
class PlannedCover:
    """The cover bytes to package, and how the Report should name them."""

    src: str
    origin: str
    resource: PackagedResource
    presented_title: str | None = None
    presented_author: str | None = None


@dataclass(frozen=True)
class CoverFailure:
    """A cover reference preparation could not carry into the book."""

    src: str
    reason: str


def plan_cover(
    ast: dict[str, object],
    *,
    title: str,
    author: str | None,
    profile: dict[str, object],
    resolve: Resolve,
    hold: Hold,
) -> PlannedCover | CoverFailure | None:
    """Use the source `cover-image` if present, otherwise compose a Default Cover.

    A source `cover-image` is removed from the working copy once it is resolved. Pandoc reads
    that metadata itself and would resolve the same relative name a second time, against the
    process it runs in rather than against the document; preparation states the resolved file to
    the writer instead, so one resolver decides which bytes are the cover.

    A Default Cover never enters the AST. It is composed from the envelope title and author and
    handed to the writer as `--epub-cover-image`, so a body image cannot become the cover by
    sitting first in the document.
    """

    meta = mapping(ast.get("meta"))
    stated = _metadata_text(meta.get(COVER))
    if stated:
        ast["meta"] = {key: value for key, value in meta.items() if key != COVER}
        label = inline_label(stated)
        resource = resolve(stated, COVER)
        if isinstance(resource, str):
            return CoverFailure(src=label, reason=resource)
        return PlannedCover(src=label, origin=SOURCE_COVER, resource=resource)
    composed = default_cover_svg(title, author, profile)
    if composed is None:
        return None
    resource = hold(composed, DEFAULT_COVER, COVER)
    if isinstance(resource, str):
        return CoverFailure(src=DEFAULT_COVER, reason=resource)
    return PlannedCover(
        src=DEFAULT_COVER,
        origin=DEFAULT_COVER,
        resource=resource,
        presented_title=title,
        presented_author=author,
    )


def _metadata_text(value: object) -> str:
    """Read one metadata value as the plain string it renders to, whatever Pandoc wrapped it in."""

    node = mapping(value)
    if text(node.get("t")) == "MetaString":
        return text(node.get("c")) or ""
    return inline_text(sequence(node.get("c"))).strip()


FONT_FAMILY = "Atkinson Hyperlegible"
BACKGROUND = "#ffffff"
FOREGROUND = "#000000"
# Atkinson Hyperlegible Regular is a wide face; this fraction of the font size is a conservative
# advance so wrapped lines stay inside the canvas rather than clipping at the margin.
ADVANCE = 0.6
TITLE_RATIO = 10
AUTHOR_RATIO = 20
MARGIN_RATIO = 10
LINE_HEIGHT = 1.2


def default_cover_svg(title: str, author: str | None, profile: dict[str, object]) -> bytes | None:
    """Draw one SVG Default Cover for this profile's canvas, or nothing where it has none."""

    canvas = _canvas(profile)
    if canvas is None:
        return None
    width, height = canvas
    margin = max(1, width // MARGIN_RATIO)
    usable = max(1, width - 2 * margin)
    title_size = max(1, width // TITLE_RATIO)
    author_size = max(1, width // AUTHOR_RATIO)
    title_lines = _wrapped(title, size=title_size, usable=usable)
    author_lines = _wrapped(author or "", size=author_size, usable=usable)
    title_height = _block_height(title_lines, title_size)
    author_height = _block_height(author_lines, author_size)
    gap = title_size if title_lines and author_lines else 0
    start = (height - title_height - gap - author_height) // 2 + title_size
    centre = width // 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BACKGROUND}"/>',
        *_texts(title_lines, x=centre, y=start, size=title_size),
        *_texts(
            author_lines,
            x=centre,
            y=start + title_height + gap,
            size=author_size,
        ),
        "</svg>",
    ]
    return "".join(parts).encode("utf-8")


def _canvas(profile: dict[str, object]) -> tuple[int, int] | None:
    """Read the profile's cover canvas, or nothing where the direction names no size."""

    direction = mapping(activation(profile, "cover_artwork"))
    canvas = mapping(direction.get("canvas"))
    width = integer(canvas.get("width_px"))
    height = integer(canvas.get("height_px"))
    if width is None or height is None:
        return None
    return width, height


def _wrapped(value: str, *, size: int, usable: int) -> list[str]:
    """Break one string onto lines that fit the canvas, without inventing a second title."""

    words = value.split()
    if not words:
        return []
    limit = max(1, int(usable / (size * ADVANCE)))
    lines = [words[0]]
    for word in words[1:]:
        candidate = f"{lines[-1]} {word}"
        if len(candidate) <= limit:
            lines[-1] = candidate
        else:
            lines.append(word)
    return lines


def _block_height(lines: list[str], size: int) -> int:
    if not lines:
        return 0
    return size + (len(lines) - 1) * _line_height(size)


def _line_height(size: int) -> int:
    return int(size * LINE_HEIGHT)


def _texts(lines: list[str], *, x: int, y: int, size: int) -> list[str]:
    return [
        f'<text x="{x}" y="{y + index * _line_height(size)}" text-anchor="middle" '
        f'font-family="{FONT_FAMILY}" font-size="{size}" fill="{FOREGROUND}">'
        f"{escape(line)}</text>"
        for index, line in enumerate(lines)
    ]

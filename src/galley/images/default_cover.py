"""Compose a deterministic Default Cover from a work's title and author.

A Default Cover is title-and-author presentation, not Cover Artwork and not a title page. It
uses the Device Profile's cover canvas and the bundled Atkinson Hyperlegible face. Preparation
rasterises the SVG through the same renderer it uses for any other cover.
"""

from xml.sax.saxutils import escape

from galley.json_reading import integer, mapping
from galley.profile.loading import activation

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

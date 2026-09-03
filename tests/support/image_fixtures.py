"""Build the image resources behavioural tests use, and the documents that reference them.

The compatible ones are written by hand from the format's own chunk structure rather than through
an imaging library, so a test asserting on measured bytes is asserting on bytes this file states
rather than on whatever an encoder chose today. The incompatible ones exist to be transformed
away, so they are written with Pillow: what matters about them is what they measure as on the way
in, which every test asserts rather than assumes.

The Markdown documents live here rather than beside the other fixtures because a document and the
resources it names have to agree: an image fixture renamed without its reference is a source that
refuses.
"""

import struct
import zlib
from pathlib import Path

from PIL import Image

# One document reaching every case a preserved image has: a PNG, a baseline JPEG, one resource
# referenced twice, and a title beside the alt text. The mislabelled file is a PNG called `.jpg`,
# so a run that trusted the extension would package it under the wrong media type.
PRESERVED_IMAGES = """---
title: An Illustrated Book
---

# Illustrated

A ![grey square](figure.png "Square title") beside a ![one grey pixel](photo.jpg) photograph.

The same ![grey square again](figure.png) once more, and a ![mislabelled](labelled.jpg) one.
"""

# Every input shape Galley normalises: a colour PNG that is oversize, a 16-bit PNG, a WebP
# carrying real transparency, a progressive JPEG, and an SVG. The cover is a compatible PNG, so a
# preserved image and five transformed ones sit in one document.
NORMALISED_IMAGES = """---
title: A Transformed Book
cover-image: cover.png
---

# Illustrated

An ![oversize](oversize.png) and a ![deep](deep.png) one.

A ![transparent](alpha.webp), a ![progressive](progressive.jpg) and a ![vector](diagram.svg) one.
"""

# One image with responsive candidates the source already resolved, plus a title and alt text.
RESPONSIVE_IMAGE = """# Illustrated

A ![grey square](figure.png "Square title"){srcset="figure.png 1x, wide.png 2x" sizes="100vw"}
inline.
"""

# A reference to a file that is not there. Nothing in the document says so; only resolution does.
MISSING_IMAGE = """# Illustrated

A ![gone](absent.png) reference.
"""

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
GREY = 0
GREY_ALPHA = 4
EIGHT_BIT = 8


def grayscale_png(
    path: Path,
    *,
    width: int = 2,
    height: int = 2,
    depth: int = EIGHT_BIT,
    colour_type: int = GREY,
) -> Path:
    """Write one greyscale PNG of the stated geometry, depth and colour type."""

    samples = 2 if colour_type == GREY_ALPHA else 1
    unit = depth // EIGHT_BIT
    row = bytes(range(1, width * samples * unit + 1))
    raw = b"".join(b"\x00" + row for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, depth, colour_type, 0, 0, 0)
    payload = (
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )
    _ = path.write_bytes(payload)
    return path


def baseline_jpeg(path: Path) -> Path:
    """Write one baseline greyscale JPEG, assembled from the format's own segments.

    The tables are the smallest legal ones rather than the standard Annex K set: one Huffman code
    of length one in each table, so the entire entropy-coded scan is a DC category of zero
    followed by an end-of-block. The image is one pixel, which is the only geometry a single
    minimum-coded unit describes honestly.
    """

    quantisation = bytes([0]) + bytes([16] * 64)
    frame = struct.pack(">BHHB", EIGHT_BIT, 1, 1, 1) + bytes([1, 0x11, 0])
    dc_table = bytes([0x00]) + bytes([1] + [0] * 15) + bytes([0x00])
    ac_table = bytes([0x10]) + bytes([1] + [0] * 15) + bytes([0x00])
    scan = bytes([1, 1, 0x00, 0, 63, 0])
    payload = (
        b"\xff\xd8"
        + _segment(0xDB, quantisation)
        + _segment(0xC0, frame)
        + _segment(0xC4, dc_table)
        + _segment(0xC4, ac_table)
        + _segment(0xDA, scan)
        + bytes([0b00111111])
        + b"\xff\xd9"
    )
    _ = path.write_bytes(payload)
    return path


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _segment(marker: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload


def colour_png(path: Path, *, width: int = 40, height: int = 30, depth: int = EIGHT_BIT) -> Path:
    """Write one colour PNG, at the sample depth the caller asks for."""

    mode = "RGB" if depth == EIGHT_BIT else "I;16"
    image = Image.new(mode, (width, height), (200, 40, 40) if depth == EIGHT_BIT else 4000)
    image.save(path, format="PNG")
    return path


def transparent_webp(path: Path, *, width: int = 24, height: int = 16) -> Path:
    """Write one WebP carrying real transparency, which the profile does not render."""

    image = Image.new("RGBA", (width, height), (10, 120, 200, 90))
    image.save(path, format="WEBP", lossless=True)
    return path


def progressive_jpeg(path: Path, *, width: int = 32, height: int = 24) -> Path:
    """Write one progressive RGB JPEG, the shape the profile calls silent misdirection."""

    Image.new("RGB", (width, height), (30, 90, 160)).save(path, format="JPEG", progressive=True)
    return path


def vector_svg(path: Path, *, width: int = 60, height: int = 40) -> Path:
    """Write one SVG with no text, so rasterisation does not depend on a font set."""

    _ = path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="{width}" height="{height}" fill="#777"/></svg>',
        encoding="utf-8",
    )
    return path

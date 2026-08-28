"""Build small hand-authored EPUB packages for read-only audit tests."""

from binascii import crc32
from collections.abc import Sequence
from pathlib import Path
from struct import pack
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

Entry = tuple[str, bytes]

MIMETYPE = "mimetype"
CONTAINER_PATH = "META-INF/container.xml"
PACKAGE_PATH = "EPUB/package.opf"
NAVIGATION_PATH = "EPUB/nav.xhtml"
CHAPTER_PATH = "EPUB/chapter-1.xhtml"
FIGURE_PATH = "EPUB/images/figure.png"
STYLE_PATH = "EPUB/styles/main.css"


CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

PACKAGE_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:uuid:8f1d6b0e-6d2a-4d51-9a7e-2c4b8d3f5a61</dc:identifier>
    <dc:title>Audit Fixture</dc:title>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-08-17T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter-1" href="chapter-1.xhtml" media-type="application/xhtml+xml"/>
    <item id="figure" href="images/figure.png" media-type="image/png"/>
    <item id="style" href="styles/main.css" media-type="text/css"/>
  </manifest>
  <spine>
    <itemref idref="chapter-1"/>
  </spine>
</package>
"""

NAVIGATION_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Audit Fixture</title></head>
  <body>
    <nav epub:type="toc" id="toc">
      <ol><li><a href="chapter-1.xhtml">Chapter One</a></li></ol>
    </nav>
  </body>
</html>
"""

CHAPTER_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Chapter One</title>
    <link rel="stylesheet" type="text/css" href="styles/main.css"/>
  </head>
  <body>
    <h1 id="start">Chapter One</h1>
    <p>A paragraph with an <a href="https://example.com/">external link</a>.</p>
    <p>A paragraph with a <a href="#start">same-document link</a>.</p>
    <p><img src="images/figure.png" alt="A one-pixel figure"/></p>
  </body>
</html>
"""

STYLE_CSS = "body { margin: 0; }\n"


def default_entries() -> list[Entry]:
    """Return the archive entries of a well-formed fixture EPUB."""

    return [
        (MIMETYPE, b"application/epub+zip"),
        (CONTAINER_PATH, CONTAINER_XML.encode("utf-8")),
        (PACKAGE_PATH, PACKAGE_OPF.encode("utf-8")),
        (NAVIGATION_PATH, NAVIGATION_XHTML.encode("utf-8")),
        (CHAPTER_PATH, CHAPTER_XHTML.encode("utf-8")),
        (FIGURE_PATH, png()),
        (STYLE_PATH, STYLE_CSS.encode("utf-8")),
    ]


def write_epub(path: Path, entries: Sequence[Entry] | None = None) -> Path:
    """Write one EPUB archive, storing the mimetype entry uncompressed."""

    members = default_entries() if entries is None else entries
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in members:
            compression = ZIP_STORED if name == MIMETYPE else ZIP_DEFLATED
            archive.writestr(name, data, compress_type=compression)
    return path


def replace(entries: Sequence[Entry], name: str, data: bytes) -> list[Entry]:
    """Return the entries with one member's bytes replaced."""

    return [(member, data if member == name else payload) for member, payload in entries]


def without(entries: Sequence[Entry], name: str) -> list[Entry]:
    """Return the entries with one member removed."""

    return [(member, payload) for member, payload in entries if member != name]


def plus(entries: Sequence[Entry], *added: Entry) -> list[Entry]:
    """Return the entries with additional members appended."""

    return [*entries, *added]


def chapter(body: str) -> bytes:
    """Build one content document with a caller-supplied body."""

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head><title>Chapter One</title></head>\n"
        f"<body>{body}</body>\n"
        "</html>\n"
    ).encode("utf-8")


def png(*, sample_depth: int = 8, colour_type: int = 0, width: int = 1, height: int = 1) -> bytes:
    """Build a PNG whose IHDR states an exact sample depth and colour type."""

    header = pack(">IIBBBBB", width, height, sample_depth, colour_type, 0, 0, 0)
    return b"".join((b"\x89PNG\r\n\x1a\n", _chunk(b"IHDR", header), _chunk(b"IEND", b"")))


def jpeg(*, progressive: bool = False, components: int = 3) -> bytes:
    """Build a JPEG whose frame header states an exact scan mode and colour model."""

    marker = b"\xff\xc2" if progressive else b"\xff\xc0"
    frame = pack(">BHHB", 8, 1, 1, components) + bytes(components * 3)
    return b"".join((b"\xff\xd8", marker, pack(">H", len(frame) + 2), frame, b"\xff\xd9"))


def webp(*, truncated: bool = False) -> bytes:
    """Build the smallest byte sequence a reader identifies as WebP."""

    payload = b"WEBPVP8 "
    declared = len(payload) + 4 if truncated else len(payload)
    return b"RIFF" + pack("<I", declared) + payload


def svg() -> bytes:
    """Build a minimal SVG document."""

    return b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>'


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return pack(">I", len(payload)) + kind + payload + pack(">I", crc32(kind + payload))

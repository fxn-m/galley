"""Read a prepared EPUB the way a device would, without trusting Pandoc's exit status."""

import zipfile
from pathlib import Path
from xml.etree import ElementTree

OPF = "{http://www.idpf.org/2007/opf}"
XHTML = "{http://www.w3.org/1999/xhtml}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTAINER = "META-INF/container.xml"
CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"


def names(artifact: Path) -> list[str]:
    """List every archive member, in the order the archive stores them."""

    with zipfile.ZipFile(artifact) as archive:
        return archive.namelist()


def package(artifact: Path) -> ElementTree.Element:
    """Resolve the OPF package document the container names."""

    with zipfile.ZipFile(artifact) as archive:
        root = ElementTree.fromstring(archive.read(CONTAINER))
        rootfile = root.find(f".//{CONTAINER_NS}rootfile")
        assert rootfile is not None
        path = rootfile.attrib["full-path"]
        return ElementTree.fromstring(archive.read(path))


def metadata(artifact: Path, name: str) -> list[str]:
    """Read one Dublin Core metadata value from the package document."""

    return [element.text or "" for element in package(artifact).iter(f"{DC}{name}")]


def epub_version(artifact: Path) -> str:
    """Name the EPUB version the package document declares."""

    return package(artifact).attrib["version"]


def spine_documents(artifact: Path) -> list[str]:
    """List the content documents the spine names, in reading order."""

    root = package(artifact)
    manifest = {item.attrib["id"]: item.attrib["href"] for item in root.iter(f"{OPF}item")}
    return [manifest[item.attrib["idref"]] for item in root.iter(f"{OPF}itemref")]


def navigation_entries(artifact: Path) -> list[str]:
    """List the visible reading-order entries the EPUB navigation document offers."""

    return [text for _, text in navigation_anchors(artifact)]


def navigation_anchors(artifact: Path) -> list[tuple[str, str]]:
    """List the navigation document's own links as href and visible text.

    Content-link processing must never reach these: they are the device's table-of-contents
    menu rather than prose, and a navigation document with no hrefs is a book with no way in.
    """

    toc = next(
        element
        for element in _navigation(artifact).iter(f"{XHTML}nav")
        if element.attrib.get("{http://www.idpf.org/2007/ops}type") == "toc"
    )
    return [
        (anchor.attrib.get("href", ""), "".join(anchor.itertext()).strip())
        for anchor in toc.iter(f"{XHTML}a")
    ]


def content_anchors(artifact: Path) -> list[tuple[str, str, str]]:
    """List every anchor the spine's content documents carry: document, href and visible text."""

    return [
        (href, anchor.attrib.get("href", ""), "".join(anchor.itertext()).strip())
        for href, root in _spine(artifact).items()
        for anchor in root.iter(f"{XHTML}a")
    ]


def anchor_identifiers(artifact: Path) -> list[tuple[str, str]]:
    """List every anchor's own identifier beside its href, for references that must stay stable."""

    return [
        (anchor.attrib.get("id", ""), anchor.attrib.get("href", ""))
        for _, root in _spine(artifact).items()
        for anchor in root.iter(f"{XHTML}a")
    ]


def media_resources(artifact: Path) -> dict[str, bytes]:
    """Map every image the package manifest declares to the bytes the archive holds.

    Read from the manifest rather than by guessing at member names, so a resource the package
    never declares cannot pass as one it does.
    """

    root = package(artifact)
    hrefs = [
        item.attrib["href"]
        for item in root.iter(f"{OPF}item")
        if item.attrib.get("media-type", "").startswith("image/")
    ]
    with zipfile.ZipFile(artifact) as archive:
        return {href: archive.read(_member(archive, href)) for href in hrefs}


def image_sources(artifact: Path) -> list[tuple[str, str, str]]:
    """List every image the content documents reference: document, src and alt text."""

    return [
        (href, image.attrib.get("src", ""), image.attrib.get("alt", ""))
        for href, root in _spine(artifact).items()
        for image in root.iter(f"{XHTML}img")
    ]


def content_text(artifact: Path) -> str:
    """Concatenate the reader-visible text of every spine content document, in reading order."""

    return " ".join(document_texts(artifact).values())


def document_texts(artifact: Path) -> dict[str, str]:
    """Map each spine document to its reader-visible text, in reading order.

    Only the body is read. A content document's `head` carries a `title` the reader never sees,
    and counting it as visible text would make a note page look as though it began with its
    filename.
    """

    return {
        href: " ".join("".join(_body(root).itertext()).split())
        for href, root in _spine(artifact).items()
    }


def _body(root: ElementTree.Element) -> ElementTree.Element:
    body = root.find(f"{XHTML}body")
    assert body is not None
    return body


def document_identifiers(artifact: Path) -> dict[str, list[str]]:
    """Map each spine document to the identifiers it offers as link targets."""

    return {
        href: [
            identifier for element in root.iter() if (identifier := element.get("id")) is not None
        ]
        for href, root in _spine(artifact).items()
    }


def headings(artifact: Path) -> list[tuple[str, str, list[str]]]:
    """List every top-level heading as its document, its visible text and its classes.

    One file per note leaves the first note's heading listed and titled, and every later one blank
    and unlisted, so what a heading says and what it is classed as are both load-bearing.
    """

    return [
        (href, "".join(heading.itertext()).strip(), heading.attrib.get("class", "").split())
        for href, root in _spine(artifact).items()
        for heading in root.iter(f"{XHTML}h1")
    ]


def element_texts(artifact: Path, tag: str) -> list[str]:
    """List the visible text of every element with one XHTML tag, across the spine in order.

    What a book *renders* a piece of content as is a device fact here, not a formatting taste:
    a heading drives pagination on CrossPoint and a blockquote is already spoken for by real
    quotations, so a test that only read the words could not tell any of the three apart.
    """

    return [
        " ".join("".join(element.itertext()).split())
        for root in _spine(artifact).values()
        for element in root.iter(f"{XHTML}{tag}")
    ]


def _spine(artifact: Path) -> dict[str, ElementTree.Element]:
    with zipfile.ZipFile(artifact) as archive:
        return {
            href: ElementTree.fromstring(archive.read(_member(archive, href)))
            for href in spine_documents(artifact)
        }


def _navigation(artifact: Path) -> ElementTree.Element:
    root = package(artifact)
    navigation = next(
        item.attrib["href"]
        for item in root.iter(f"{OPF}item")
        if "nav" in item.attrib.get("properties", "").split()
    )
    with zipfile.ZipFile(artifact) as archive:
        return ElementTree.fromstring(archive.read(_member(archive, navigation)))


def _member(archive: zipfile.ZipFile, href: str) -> str:
    return next(name for name in archive.namelist() if name.endswith(href))

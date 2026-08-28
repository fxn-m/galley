"""Parse EPUB container, package, and navigation documents read-only."""

from dataclasses import dataclass, field
from xml.etree.ElementTree import Element, ParseError, fromstring

from galley.epub.archive import EpubArchive, classify_reference, normalise_archive_path

CONTAINER_PATH = "META-INF/container.xml"
MIMETYPE_PATH = "mimetype"
EPUB_MIMETYPE = "application/epub+zip"
OPF_MEDIA_TYPE = "application/oebps-package+xml"
XHTML_MEDIA_TYPE = "application/xhtml+xml"
NCX_MEDIA_TYPE = "application/x-dtbncx+xml"

CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
XLINK_NS = "http://www.w3.org/1999/xlink"
REFERENCE_ATTRIBUTES = ("href", "src", "data", f"{{{XLINK_NS}}}href")


@dataclass(frozen=True)
class ManifestItem:
    """One declared package manifest item and its resolved archive member."""

    item_id: str
    href: str
    path: str | None
    media_type: str
    properties: tuple[str, ...]


@dataclass(frozen=True)
class SpineItem:
    """One spine itemref and whether the reader must follow it in order."""

    idref: str
    linear: bool


@dataclass(frozen=True)
class Container:
    """The facts an EPUB container document can establish."""

    present: bool
    malformed: bool
    rootfiles: tuple[str, ...] = ()
    package_path: str | None = None


@dataclass(frozen=True)
class Package:
    """The facts one package document can establish."""

    present: bool
    malformed: bool
    path: str | None = None
    version: str | None = None
    unique_identifier: str | None = None
    title: str | None = None
    items: tuple[ManifestItem, ...] = ()
    duplicate_ids: tuple[str, ...] = ()
    spine: tuple[SpineItem, ...] = ()
    toc_idref: str | None = None
    cover_id: str | None = None
    references: list[str] = field(default_factory=list[str])


def parse_xml(data: bytes) -> Element | None:
    """Parse one XML member, returning None when it is malformed."""

    try:
        return fromstring(data)
    except ParseError:
        return None


def read_container(archive: EpubArchive) -> Container:
    """Read the container document and select the package document path."""

    data = archive.read(CONTAINER_PATH)
    if data is None:
        return Container(present=False, malformed=False)
    root = parse_xml(data)
    if root is None:
        return Container(present=True, malformed=True)
    rootfiles: list[str] = []
    preferred: str | None = None
    for element in root.iter(f"{{{CONTAINER_NS}}}rootfile"):
        full_path = element.get("full-path")
        resolved = None if full_path is None else normalise_archive_path(full_path)
        if resolved is None:
            continue
        rootfiles.append(resolved)
        if preferred is None and element.get("media-type") == OPF_MEDIA_TYPE:
            preferred = resolved
    package_path = preferred if preferred is not None else (rootfiles[0] if rootfiles else None)
    return Container(
        present=True,
        malformed=False,
        rootfiles=tuple(rootfiles),
        package_path=package_path,
    )


def read_package(archive: EpubArchive, path: str) -> Package:
    """Read one package document's metadata, manifest, and spine."""

    data = archive.read(path)
    if data is None:
        return Package(present=False, malformed=False, path=path)
    root = parse_xml(data)
    if root is None:
        return Package(present=True, malformed=True, path=path)
    items, duplicate_ids, references = _read_manifest(root, path)
    spine_element = root.find(f"{{{OPF_NS}}}spine")
    spine = _read_spine(spine_element)
    return Package(
        present=True,
        malformed=False,
        path=path,
        version=root.get("version"),
        unique_identifier=_unique_identifier(root),
        title=_first_text(root, f"{{{DC_NS}}}title"),
        items=items,
        duplicate_ids=duplicate_ids,
        spine=spine,
        toc_idref=None if spine_element is None else spine_element.get("toc"),
        cover_id=_cover_id(root, items),
        references=references,
    )


def document_references(root: Element, base: str) -> list[tuple[str, str | None]]:
    """Collect every classified reference an XML document makes."""

    references: list[tuple[str, str | None]] = []
    for element in root.iter():
        for attribute in REFERENCE_ATTRIBUTES:
            value = element.get(attribute)
            if value is not None:
                references.append(classify_reference(base, value))
    return references


def navigation_entry_count(root: Element, kind: str) -> int:
    """Count the navigation targets one navigation document lists."""

    if kind == "ncx":
        return sum(1 for _ in root.iter(f"{{{NCX_NS}}}navPoint"))
    return sum(
        1
        for navigation in root.iter(f"{{{XHTML_NS}}}nav")
        for anchor in navigation.iter(f"{{{XHTML_NS}}}a")
        if anchor.get("href") is not None
    )


def _read_manifest(
    root: Element, path: str
) -> tuple[tuple[ManifestItem, ...], tuple[str, ...], list[str]]:
    items: list[ManifestItem] = []
    seen: list[str] = []
    duplicates: list[str] = []
    references: list[str] = []
    for element in root.iter(f"{{{OPF_NS}}}item"):
        item_id = element.get("id")
        href = element.get("href")
        if item_id is None or href is None:
            continue
        if item_id in seen and item_id not in duplicates:
            duplicates.append(item_id)
        seen.append(item_id)
        kind, resolved = classify_reference(path, href)
        items.append(
            ManifestItem(
                item_id=item_id,
                href=href,
                path=resolved,
                media_type=element.get("media-type") or "",
                properties=tuple((element.get("properties") or "").split()),
            )
        )
        if kind == "in-book" and resolved is not None:
            references.append(resolved)
    items.sort(key=lambda item: item.item_id)
    return tuple(items), tuple(sorted(duplicates)), references


def _read_spine(spine_element: Element | None) -> tuple[SpineItem, ...]:
    if spine_element is None:
        return ()
    return tuple(
        SpineItem(idref=idref, linear=element.get("linear") != "no")
        for element in spine_element.iter(f"{{{OPF_NS}}}itemref")
        if (idref := element.get("idref")) is not None
    )


def _cover_id(root: Element, items: tuple[ManifestItem, ...]) -> str | None:
    for item in items:
        if "cover-image" in item.properties:
            return item.item_id
    known = {item.item_id for item in items}
    for element in root.iter(f"{{{OPF_NS}}}meta"):
        if element.get("name") == "cover" and (content := element.get("content")) in known:
            return content
    return None


def _unique_identifier(root: Element) -> str | None:
    identifier_id = root.get("unique-identifier")
    for element in root.iter(f"{{{DC_NS}}}identifier"):
        if identifier_id is None or element.get("id") == identifier_id:
            return (element.text or "").strip() or None
    return None


def _first_text(root: Element, tag: str) -> str | None:
    for element in root.iter(tag):
        return (element.text or "").strip() or None
    return None

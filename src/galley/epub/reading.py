"""Turn a read-only EPUB package reading into canonical artifact facts."""

from dataclasses import dataclass, field
from hashlib import sha256
from typing import cast
from xml.etree.ElementTree import Element

from galley.epub.archive import EpubArchive
from galley.epub.package import (
    CONTAINER_PATH,
    NCX_MEDIA_TYPE,
    XHTML_MEDIA_TYPE,
    Container,
    ManifestItem,
    Package,
    navigation_entry_count,
    parse_xml,
    read_container,
    read_package,
)
from galley.epub.inventory import (
    archive_facts,
    container_facts,
    manifest_facts,
    package_facts,
    spine_facts,
)
from galley.epub.references import reference_facts
from galley.report.quantities import quantity


@dataclass(frozen=True)
class PackageReading:
    """One read of a package: its facts, and the documents the reading parsed."""

    facts: dict[str, object]
    documents: tuple[tuple[str, Element], ...]
    spine_documents: tuple[tuple[str, Element], ...]
    chapters: frozenset[str]
    resources: tuple[tuple[str, str], ...]
    cover_path: str | None
    malformed_documents: int


@dataclass
class _Scan:
    """Facts and problems accumulated while reading one package, in stable order."""

    problems: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    documents: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    resources: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    parsed: list[tuple[str, Element]] = field(default_factory=list[tuple[str, Element]])

    def problem(self, kind: str, detail: str, location: str) -> None:
        self.problems.append({"detail": detail, "kind": kind, "location": location})

    def already_reported(self, kind: str, location: str) -> bool:
        return any(
            problem["kind"] == kind and problem["location"] == location for problem in self.problems
        )


def read_artifact(
    *, path: str, byte_size: int, digest: str, archive: EpubArchive
) -> PackageReading:
    """Assemble every fact a read-only package audit can establish."""

    scan = _Scan()
    container = read_container(archive)
    _container_problems(scan, container)
    package = _selected_package(archive, container)
    _package_problems(scan, package)
    _archive_problems(scan, archive)
    _read_members(scan, archive, package)
    navigation = _navigation_facts(scan, archive, package)
    references = reference_facts(archive, package, scan.parsed)
    _reference_problems(scan, references)
    facts: dict[str, object] = {
        "archive": archive_facts(archive),
        "byte_size": quantity(byte_size, "bytes"),
        "container": container_facts(container),
        "content_documents": scan.documents,
        "manifest": manifest_facts(archive, package),
        "navigation": navigation,
        "package": package_facts(package),
        "path": path,
        "problems": sorted(
            scan.problems,
            key=lambda problem: (problem["kind"], problem["location"], problem["detail"]),
        ),
        "references": references,
        "resources": scan.resources,
        "sha256": digest,
        "spine": spine_facts(package),
    }
    return PackageReading(
        facts=facts,
        documents=tuple(scan.parsed),
        spine_documents=_spine_documents(package, scan.parsed),
        chapters=_chapters(package),
        resources=tuple(
            (str(resource["path"]), str(resource["declared_media_type"]))
            for resource in scan.resources
        ),
        cover_path=_cover_path(package),
        malformed_documents=sum(
            1 for document in scan.documents if document.get("malformed_xml") is True
        ),
    )


def _selected_package(archive: EpubArchive, container: Container) -> Package:
    if container.package_path is None:
        return Package(present=False, malformed=False)
    return read_package(archive, container.package_path)


def _container_problems(scan: _Scan, container: Container) -> None:
    if not container.present:
        scan.problem(
            "missing-container", "the archive declares no container document", CONTAINER_PATH
        )
    elif container.malformed:
        scan.problem("malformed-xml", "the container document is not well-formed", CONTAINER_PATH)


def _package_problems(scan: _Scan, package: Package) -> None:
    if package.path is None:
        return
    if not package.present:
        scan.problem(
            "missing-package-document",
            "the declared package document is absent from the archive",
            package.path,
        )
        return
    if package.malformed:
        scan.problem("malformed-xml", "the package document is not well-formed", package.path)
        return
    for duplicate in package.duplicate_ids:
        scan.problem(
            "duplicate-manifest-id",
            f"the manifest declares id {duplicate} more than once",
            package.path,
        )


def _archive_problems(scan: _Scan, archive: EpubArchive) -> None:
    for name in archive.duplicate_members:
        scan.problem("duplicate-archive-member", "the archive declares this member twice", name)
    for name in archive.unsafe_members:
        scan.problem("unsafe-archive-path", "this member name escapes the archive root", name)
    for name in archive.unreadable_members:
        scan.problem("unreadable-archive-member", "this member could not be read", name)


def _read_members(scan: _Scan, archive: EpubArchive, package: Package) -> None:
    seen: set[str] = set()
    for item in package.items:
        if item.path is None or item.path in seen:
            continue
        seen.add(item.path)
        data = archive.read(item.path)
        if data is None:
            continue
        facts: dict[str, object] = {
            "byte_size": quantity(len(data), "bytes"),
            "declared_media_type": item.media_type,
            "path": item.path,
            "sha256": sha256(data).hexdigest(),
        }
        if item.media_type != XHTML_MEDIA_TYPE:
            scan.resources.append(facts)
            continue
        root = parse_xml(data)
        facts["malformed_xml"] = root is None
        scan.documents.append(facts)
        if root is None:
            scan.problem("malformed-xml", "this content document is not well-formed", item.path)
        else:
            scan.parsed.append((item.path, root))
    scan.documents.sort(key=lambda document: str(document["path"]))
    scan.resources.sort(key=lambda resource: str(resource["path"]))


def _navigation_item(package: Package) -> tuple[ManifestItem | None, str | None]:
    for item in package.items:
        if "nav" in item.properties and item.media_type == XHTML_MEDIA_TYPE:
            return item, "epub3-nav"
    for item in package.items:
        if item.item_id == package.toc_idref or item.media_type == NCX_MEDIA_TYPE:
            return item, "ncx"
    return None, None


def _navigation_facts(scan: _Scan, archive: EpubArchive, package: Package) -> dict[str, object]:
    item, kind = _navigation_item(package)
    data = None if item is None or item.path is None else archive.read(item.path)
    root = None if data is None else parse_xml(data)
    path = None if item is None else item.path
    if root is None:
        _missing_navigation_problem(scan, package, path, malformed=data is not None)
        return {
            "entry_count": quantity(0, "entries"),
            "kind": None if data is None else kind,
            "malformed_xml": data is not None,
            "path": path,
            "present": data is not None,
        }
    if path is not None and all(path != parsed for parsed, _ in scan.parsed):
        scan.parsed.append((path, root))
    return {
        "entry_count": quantity(navigation_entry_count(root, kind or ""), "entries"),
        "kind": kind,
        "malformed_xml": False,
        "path": path,
        "present": True,
    }


def _missing_navigation_problem(
    scan: _Scan, package: Package, path: str | None, *, malformed: bool
) -> None:
    if not package.present or package.malformed:
        return
    location = path or package.path or CONTAINER_PATH
    if not malformed:
        scan.problem("missing-navigation", "no readable navigation document was found", location)
    elif not scan.already_reported("malformed-xml", location):
        scan.problem("malformed-xml", "the navigation document is not well-formed", location)


def _reference_problems(scan: _Scan, references: dict[str, object]) -> None:
    for entry in cast(list[dict[str, object]], references["broken"]):
        scan.problem(
            "broken-reference", f"{entry['kind']} reference is unresolved", str(entry["from"])
        )


def _chapters(package: Package) -> frozenset[str]:
    """Name the spine documents a Device Profile would read as chapters."""

    paths: dict[str, str | None] = {}
    for item in package.items:
        _ = paths.setdefault(item.item_id, item.path)
    return frozenset(
        path for spine_item in package.spine if (path := paths.get(spine_item.idref)) is not None
    )


def _spine_documents(
    package: Package, documents: list[tuple[str, Element]]
) -> tuple[tuple[str, Element], ...]:
    """Order reader content by the spine, excluding the navigation-only manifest item."""

    parsed = dict(documents)
    items = {item.item_id: item for item in package.items}
    return tuple(
        (path, root)
        for spine_item in package.spine
        if (item := items.get(spine_item.idref)) is not None
        and "nav" not in item.properties
        and (path := item.path) is not None
        and (root := parsed.get(path)) is not None
    )


def _cover_path(package: Package) -> str | None:
    """Resolve the manifest item the package names as its cover image."""

    for item in package.items:
        if item.item_id == package.cover_id:
            return item.path
    return None

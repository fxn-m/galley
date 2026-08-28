"""Shape a read EPUB package into canonical inventory facts."""

from galley.epub.archive import EpubArchive
from galley.epub.package import EPUB_MIMETYPE, MIMETYPE_PATH, Container, Package
from galley.report.quantities import quantity


def archive_facts(archive: EpubArchive) -> dict[str, object]:
    declared = archive.read_text(MIMETYPE_PATH)
    return {
        "duplicate_members": archive.duplicate_members,
        "member_count": quantity(archive.member_count, "members"),
        "mimetype": {
            "declared": None if declared is None else declared.strip(),
            "matches_epub": declared is not None and declared.strip() == EPUB_MIMETYPE,
            "present": declared is not None,
        },
        "unreadable_members": archive.unreadable_members,
        "unsafe_members": archive.unsafe_members,
    }


def container_facts(container: Container) -> dict[str, object]:
    return {
        "malformed_xml": container.malformed,
        "package_path": container.package_path,
        "present": container.present,
        "rootfiles": list(container.rootfiles),
    }


def package_facts(package: Package) -> dict[str, object]:
    return {
        "malformed_xml": package.malformed,
        "path": package.path,
        "present": package.present,
        "cover_id": package.cover_id,
        "title": package.title,
        "unique_identifier": package.unique_identifier,
        "version": package.version,
    }


def manifest_facts(archive: EpubArchive, package: Package) -> dict[str, object]:
    items = [
        {
            "declared_media_type": item.media_type,
            "href": item.href,
            "id": item.item_id,
            "path": item.path,
            "present": item.path is not None and archive.contains(item.path),
            "properties": list(item.properties),
        }
        for item in package.items
    ]
    return {
        "duplicate_ids": list(package.duplicate_ids),
        "item_count": quantity(len(items), "items"),
        "items": items,
    }


def spine_facts(package: Package) -> dict[str, object]:
    paths: dict[str, str | None] = {}
    for item in package.items:
        _ = paths.setdefault(item.item_id, item.path)
    items = [
        {
            "idref": spine_item.idref,
            "linear": spine_item.linear,
            "path": paths.get(spine_item.idref),
            "resolved": spine_item.idref in paths,
        }
        for spine_item in package.spine
    ]
    return {
        "item_count": quantity(len(items), "items"),
        "items": items,
        "toc": package.toc_idref,
    }

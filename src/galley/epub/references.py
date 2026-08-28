"""Resolve an EPUB package's reference graph read-only."""

from collections.abc import Sequence
from xml.etree.ElementTree import Element

from galley.epub.archive import EpubArchive
from galley.epub.package import CONTAINER_PATH, Package, document_references
from galley.report.quantities import quantity


def reference_facts(
    archive: EpubArchive,
    package: Package,
    documents: Sequence[tuple[str, Element]],
) -> dict[str, object]:
    """Resolve manifest, spine, and document references against archive members."""

    package_path = package.path or CONTAINER_PATH
    broken: list[dict[str, object]] = [
        {"from": package_path, "kind": "manifest", "target": target}
        for target in package.references
        if not archive.contains(target)
    ]
    manifest_ids = {item.item_id for item in package.items}
    broken.extend(
        {"from": package_path, "kind": "spine", "target": spine_item.idref}
        for spine_item in package.spine
        if spine_item.idref not in manifest_ids
    )
    counts = {"in-book": 0, "external": 0, "same-document": 0, "unsafe": 0}
    for base, root in documents:
        for kind, target in document_references(root, base):
            counts[kind] += 1
            if kind == "in-book" and target is not None and not archive.contains(target):
                broken.append({"from": base, "kind": "content-document", "target": target})
    return {
        "broken": broken,
        "broken_count": quantity(len(broken), "references"),
        "document_count": quantity(counts["in-book"], "references"),
        "external_count": quantity(counts["external"], "references"),
        "same_document_count": quantity(counts["same-document"], "references"),
    }

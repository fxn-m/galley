"""One independent snapshot of an EPUB's declared documents, reading roles and media.

No Galley package reader is used: these observations check the bytes the installed command
published. Each journey owns its snapshot; nothing is shared between tests or invocations.
"""

import posixpath
import zipfile
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

OPF = "{http://www.idpf.org/2007/opf}"
XHTML = "{http://www.w3.org/1999/xhtml}"
DC = "{http://purl.org/dc/elements/1.1/}"
EPUB = "{http://www.idpf.org/2007/ops}"
CONTAINER = "META-INF/container.xml"
CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"
Role = Literal["body", "cover", "spine"]


class PreparedEpub:
    """Read an artifact once, resolving every member relative to the declared OPF location."""

    def __init__(self, artifact: Path) -> None:
        with zipfile.ZipFile(artifact) as archive:
            self._members = {name: archive.read(name) for name in archive.namelist()}
        container = ElementTree.fromstring(self._members[CONTAINER])
        rootfile = container.find(f".//{CONTAINER_NS}rootfile")
        assert rootfile is not None
        self._package_path = rootfile.attrib["full-path"]
        self._package = ElementTree.fromstring(self._members[self._package_path])
        self._items = {item.attrib["id"]: item for item in self._package.iter(f"{OPF}item")}
        self._documents = {
            item.attrib["href"]: ElementTree.fromstring(self.member(item.attrib["href"]))
            for item in self._items.values()
            if item.get("media-type") == "application/xhtml+xml"
        }
        self._navigation = next(
            (
                item.attrib["href"]
                for item in self._items.values()
                if "nav" in item.get("properties", "").split()
            ),
            None,
        )
        self._covers = {
            _target(self._package_path, reference.attrib["href"])
            for reference in self._package.iter(f"{OPF}reference")
            if "cover" in reference.get("type", "").split()
        }
        for href, document in self._documents.items():
            body = _body(document)
            if any(
                "cover" in element.get(f"{EPUB}type", "").split()
                for element in (document, body, *body)
            ):
                self._covers.add(_target(self._package_path, href))
        if self._navigation is not None:
            for navigation in self._documents[self._navigation].iter(f"{XHTML}nav"):
                if "landmarks" not in navigation.get(f"{EPUB}type", "").split():
                    continue
                for anchor in navigation.iter(f"{XHTML}a"):
                    if "cover" in anchor.get(f"{EPUB}type", "").split():
                        self._covers.add(
                            _target(
                                _target(self._package_path, self._navigation), anchor.attrib["href"]
                            )
                        )

    def names(self) -> list[str]:
        """List ZIP members in archive order, including undeclared ones."""
        return list(self._members)

    def package(self) -> ElementTree.Element:
        """Expose the OPF for tests whose claim is package structure."""
        return self._package

    def member(self, href: str) -> bytes:
        """Read an OPF-relative member exactly; suffix matches are ambiguous."""
        return self._members[_target(self._package_path, href)]

    def metadata(self, name: str) -> list[str]:
        return [element.text or "" for element in self._package.iter(f"{DC}{name}")]

    def epub_version(self) -> str:
        return self._package.attrib["version"]

    def spine_documents(self) -> list[str]:
        """Retain every spine entry in order, including cover and navigation documents."""
        return [
            self._items[item.attrib["idref"]].attrib["href"]
            for item in self._package.iter(f"{OPF}itemref")
        ]

    def cover_documents(self) -> list[str]:
        """Name declared cover documents, even when their spine entry is non-linear."""
        return [
            href
            for href in self.spine_documents()
            if _target(self._package_path, href) in self._covers
        ]

    def body_documents(self) -> list[str]:
        """Name the work's spine documents, excluding cover and navigation roles."""
        covers = self.cover_documents()
        return [
            href
            for href in self.spine_documents()
            if href not in covers and href != self._navigation
        ]

    def navigation_entries(self) -> list[str]:
        return [text for _, text in self.navigation_anchors()]

    def navigation_anchors(self) -> list[tuple[str, str]]:
        """Read only the table of contents, not landmark or page-list links."""
        assert self._navigation is not None
        toc = next(
            element
            for element in self._documents[self._navigation].iter(f"{XHTML}nav")
            if "toc" in element.get(f"{EPUB}type", "").split()
        )
        return [
            (anchor.get("href", ""), "".join(anchor.itertext()).strip())
            for anchor in toc.iter(f"{XHTML}a")
        ]

    def content_anchors(self) -> list[tuple[str, str, str]]:
        return [
            (href, anchor.get("href", ""), "".join(anchor.itertext()).strip())
            for href, root in self._reading().items()
            for anchor in root.iter(f"{XHTML}a")
        ]

    def anchor_identifiers(self) -> list[tuple[str, str]]:
        return [
            (anchor.get("id", ""), anchor.get("href", ""))
            for root in self._reading().values()
            for anchor in root.iter(f"{XHTML}a")
        ]

    def media_resources(self) -> dict[str, bytes]:
        """Map declared image hrefs to their exact bytes, excluding undeclared ZIP members."""
        return {
            item.attrib["href"]: self.member(item.attrib["href"])
            for item in self._items.values()
            if item.get("media-type", "").startswith("image/")
        }

    def cover_resource(self) -> str | None:
        """Name the manifest image declared as the cover, independently of document roles."""
        return next(
            (
                item.attrib["href"]
                for item in self._items.values()
                if "cover-image" in item.get("properties", "").split()
            ),
            None,
        )

    def resource_for(self, document: str, reference: str) -> str | None:
        """Resolve a document's media reference to its declared manifest href, if present."""
        target = _target(_target(self._package_path, document), reference)
        return next(
            (
                href
                for href in self.media_resources()
                if _target(self._package_path, href) == target
            ),
            None,
        )

    def image_sources(self, *, role: Role = "body") -> list[tuple[str, str, str]]:
        """Read images and alt text from body, cover, or all spine documents."""
        return [
            (href, image.get("src", ""), image.get("alt", ""))
            for href, root in self._reading(role).items()
            for image in root.iter(f"{XHTML}img")
        ]

    def content_text(self) -> str:
        return " ".join(self.document_texts().values())

    def document_texts(self) -> dict[str, str]:
        """Read body text in reading order; document head titles are not reader content."""
        return {
            href: " ".join("".join(_body(root).itertext()).split())
            for href, root in self._reading().items()
        }

    def document_identifiers(self) -> dict[str, list[str]]:
        return {
            href: [
                identifier
                for element in root.iter()
                if (identifier := element.get("id")) is not None
            ]
            for href, root in self._reading().items()
        }

    def headings(self) -> list[tuple[str, str, list[str]]]:
        return [
            (href, "".join(heading.itertext()).strip(), heading.get("class", "").split())
            for href, root in self._reading().items()
            for heading in root.iter(f"{XHTML}h1")
        ]

    def element_texts(self, tag: str) -> list[str]:
        return [
            " ".join("".join(element.itertext()).split())
            for root in self._reading().values()
            for element in root.iter(f"{XHTML}{tag}")
        ]

    def _reading(self, role: Role = "body") -> dict[str, ElementTree.Element]:
        documents = {
            "body": self.body_documents,
            "cover": self.cover_documents,
            "spine": self.spine_documents,
        }[role]()
        return {href: self._documents[href] for href in documents}


def _body(root: ElementTree.Element) -> ElementTree.Element:
    body = root.find(f"{XHTML}body")
    assert body is not None
    return body


def _target(base: str, reference: str) -> str:
    split = urlsplit(reference)
    assert not split.scheme and not split.netloc, f"not an in-book reference: {reference}"
    path = unquote(split.path)
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), path)) if path else base

"""Measure Recorded Links, Link Kinds, and anchors in artifact content documents."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import unquote
from xml.etree.ElementTree import Element

from galley.document.link_kinds import CountingRule, LinkKind, Marker, is_external, link_kind
from galley.epub.archive import join_archive_path

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
EPUB_TYPE = f"{{{EPUB_NS}}}type"

READING_BLOCKS = frozenset(
    {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "blockquote",
        "pre",
        "dt",
        "dd",
        "figcaption",
        "td",
        "th",
    }
)
IMPLICIT_CONTAINERS = frozenset({"section", "div", "body"})
SKIPPED = frozenset({"head", "script", "style", "template"})
NOTEREF_TOKENS = frozenset({"noteref", "doc-noteref"})
BACKLINK_TOKENS = frozenset({"backlink", "doc-backlink"})


@dataclass(frozen=True)
class Link:
    """One measured `a href` and what the Device Profile would do with it."""

    document: str
    href: str
    text: str
    href_bytes: int
    kind: LinkKind
    recorded: bool
    marked: Marker
    resolves: bool
    target_document: str | None
    """The content document this in-book href resolves into, or nothing where it resolves nowhere.

    One file per note is a claim about where references land, not only about whether they land: a
    book whose references all resolve inside one document is the same-file notes section the
    profile rejects.
    """


@dataclass(frozen=True)
class Block:
    """One innermost reading block and the Recorded Links it carries."""

    document: str
    recorded: int
    non_footnote_recorded: int


@dataclass
class Measurement:
    """Everything one pass over the artifact's content documents established."""

    links: list[Link] = field(default_factory=list[Link])
    blocks: list[Block] = field(default_factory=list[Block])
    anchors: dict[str, int] = field(default_factory=dict[str, int])
    complete: bool = True

    @property
    def recorded(self) -> list[Link]:
        return [link for link in self.links if link.recorded]

    @property
    def max_recorded_per_block(self) -> int:
        return max((block.recorded for block in self.blocks), default=0)

    @property
    def max_non_footnote_recorded_per_block(self) -> int:
        return max((block.non_footnote_recorded for block in self.blocks), default=0)

    @property
    def max_href_bytes(self) -> int:
        return max((link.href_bytes for link in self.recorded), default=0)

    @property
    def max_anchors(self) -> int:
        return max(self.anchors.values(), default=0)


def measure_documents(
    documents: Sequence[tuple[str, Element]],
    *,
    identifiers: Mapping[str, frozenset[str]],
    members: frozenset[str],
    rule: CountingRule,
    chapters: frozenset[str],
    complete: bool,
) -> Measurement:
    """Measure every content document's links, blocks, and anchors in stable order."""

    measurement = Measurement(complete=complete)
    for path, root in documents:
        if path in chapters:
            measurement.anchors[path] = sum(1 for element in root.iter() if element.get("id"))
        for block in _blocks(root):
            recorded = 0
            non_footnote = 0
            for element in block:
                link = _link(element, path, identifiers, members, rule)
                measurement.links.append(link)
                if link.recorded:
                    recorded += 1
                    if link.kind not in ("footnote-reference", "footnote-back-link"):
                        non_footnote += 1
            measurement.blocks.append(
                Block(document=path, recorded=recorded, non_footnote_recorded=non_footnote)
            )
    return measurement


def _blocks(root: Element) -> list[list[Element]]:
    blocks: list[list[Element]] = []
    _walk(root, blocks, None)
    return blocks


def _walk(element: Element, blocks: list[list[Element]], current: list[Element] | None) -> None:
    for child in element:
        tag = _tag(child)
        if tag in SKIPPED:
            continue
        if tag in READING_BLOCKS:
            nested: list[Element] = []
            blocks.append(nested)
            _walk(child, blocks, nested)
            current = None
            continue
        if tag in IMPLICIT_CONTAINERS:
            _walk(child, blocks, None)
            current = None
            continue
        if current is None:
            current = []
            blocks.append(current)
        if tag == "a" and child.get("href") is not None:
            current.append(child)
        _walk(child, blocks, current)


def _link(
    element: Element,
    document: str,
    identifiers: Mapping[str, frozenset[str]],
    members: frozenset[str],
    rule: CountingRule,
) -> Link:
    href = element.get("href") or ""
    text = " ".join("".join(element.itertext()).split())
    external = is_external(href, rule)
    target = None if external else _target(href, document, identifiers, members)
    tokens = _tokens(element)
    marked: Marker = (
        "noteref" if tokens & NOTEREF_TOKENS else ("backlink" if tokens & BACKLINK_TOKENS else "")
    )
    return Link(
        document=document,
        href=href,
        text=text,
        href_bytes=len(href.encode("utf-8")),
        kind=link_kind(marked=marked, external=external, resolves=target is not None),
        recorded=not external and (bool(text) or not rule.requires_visible_text),
        marked=marked,
        resolves=target is not None,
        target_document=target,
    )


def _target(
    href: str,
    document: str,
    identifiers: Mapping[str, frozenset[str]],
    members: frozenset[str],
) -> str | None:
    """Name the content document one in-book href reaches, or nothing where it reaches none."""

    path_part, _, fragment = href.strip().partition("#")
    if not path_part:
        resolved = document
    else:
        joined = join_archive_path(document, unquote(path_part))
        if joined is None or joined not in members:
            return None
        resolved = joined
    if not fragment:
        return resolved
    known = identifiers.get(resolved)
    return resolved if known is not None and unquote(fragment) in known else None


def _tokens(element: Element) -> frozenset[str]:
    values = f"{element.get(EPUB_TYPE) or ''} {element.get('role') or ''}"
    return frozenset(values.lower().split())


def _tag(element: Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def document_identifiers(root: Element) -> frozenset[str]:
    """Return every fragment identifier one content document offers as a link target."""

    return frozenset(
        identifier for element in root.iter() if (identifier := element.get("id")) is not None
    )

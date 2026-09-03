"""Name the remote image references one Canonical Document carries, and point them at local bytes.

Selection and rewriting are the same walk seen twice, so they live together: what is chosen here
is exactly what is replaced there, and a reference cannot be localised without having been named
in the record first.

`Image` nodes and one named metadata field are rewritten: a locator the document's `cover-image`
metadata names is retrieved and replaced on the same terms as any `src`. It is one field with a
decision behind it, not metadata in general — a locator in some other hand-authored field stays
the agent's responsibility.
"""

from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import urlsplit

from galley.images.inline import is_inline
from galley.images.cover import COVER
from galley.images.preparation import IMAGE
from galley.images.resolution import LOCAL_SCHEMES
from galley.json_reading import mapping, sequence, text
from galley.tools.fetching import fetchable

UnlocalisableReason = Literal["unsupported-locator"]
META_STRING = "MetaString"
META_INLINES = "MetaInlines"
# The identifier the cover's own reference takes, so the record distinguishes it from the images
# without renumbering them. It is the metadata key, because that is what a reader would look for.
COVER_REFERENCE = COVER


@dataclass(frozen=True)
class Reference:
    """One remote locator this document references, and how many of its images use it."""

    identifier: str
    locator: str
    occurrences: int


@dataclass(frozen=True)
class Unlocalisable:
    """One reference `localise` cannot turn into local bytes, and why it cannot."""

    locator: str
    reason: UnlocalisableReason

    @property
    def detail(self) -> str:
        """State the refusal in the words a reader needs to act on it, locator included.

        The locator is in the fact as its own field, and it is in the sentence too, because the
        sentence is what a reader sees without `--json` and a refusal that does not say which
        reference stopped it leaves them nowhere.
        """

        return f"{self.locator} names neither a local file nor an http or https locator"


def remote_references(document: dict[str, object]) -> list[Reference] | Unlocalisable:
    """List every distinct remote locator this document's images name, in reading order.

    Distinct, because a document that shows one picture twice is one retrieval; in reading order,
    because that is the order a reader would check the record against the document. A local
    reference is passed over — `prepare` already resolves those against the source's directory —
    and so is an inline one, whose bytes travelled inside the document and need retrieving from
    nowhere. Anything that is neither is refused, because a Repair Set carrying one would be
    refused by the very command this exists to feed.
    """

    ast = cast(dict[str, object], document["pandoc"])
    counts: dict[str, int] = {}
    for locator in _sources(ast):
        if _remote(locator):
            counts[locator] = counts.get(locator, 0) + 1
        elif not _local(locator):
            return Unlocalisable(locator, "unsupported-locator")
    images = [
        Reference(identifier=f"image-{number}", locator=locator, occurrences=occurrences)
        for number, (locator, occurrences) in enumerate(counts.items(), start=1)
    ]
    cover = _cover_locator(ast)
    if cover is None or not _remote(cover):
        return images
    # A cover that is also shown in the body is one retrieval, and the rewrite reaches both from
    # the one locator it was written under. Naming it twice would fetch the same bytes twice and
    # make the record say a document pulled more than it did.
    if cover in counts:
        return images
    return [Reference(identifier=COVER_REFERENCE, locator=cover, occurrences=1), *images]


def localised_document(document: dict[str, object], paths: dict[str, str]) -> dict[str, object]:
    """Return the document with each named locator replaced by the file its bytes were written to.

    Everything else is the object that came in: same title, same author, same warnings, same
    non-image nodes, same Pandoc API version. The `cover-image` metadata value moves too, and
    repair validation still accepts the result — it runs no node-level diff, and the Preservation
    Baseline renders `blocks` alone, so neither the digest nor anything checked has moved.
    """

    ast = cast(dict[str, object], document["pandoc"])
    rewritten = cast(dict[str, object], _rewritten(ast, paths))
    return {**document, "pandoc": {**rewritten, "meta": _covered(ast, paths)}}


def _sources(value: object) -> list[str]:
    """Every `Image` `src` in the tree, in reading order, however deeply each one sits.

    An image's own description is not walked, for the reason image preparation does not walk it
    either: Pandoc copies a figure's caption into the description, so it is a second copy of text
    already reachable, and it can hold no image of its own. Selecting from somewhere `prepare`
    does not resolve would put a difference in the Repair Set that changes no book.
    """

    if isinstance(value, list):
        return [src for item in cast(list[object], value) for src in _sources(item)]
    if not isinstance(value, dict):
        return []
    node = cast(dict[str, object], value)
    if text(node.get("t")) == IMAGE:
        return [_target(node)]
    return [src for item in node.values() for src in _sources(item)]


def _rewritten(value: object, paths: dict[str, str]) -> object:
    """Rebuild the tree, replacing the `src` of each `Image` whose locator was retrieved."""

    if isinstance(value, list):
        return [_rewritten(item, paths) for item in cast(list[object], value)]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    if text(node.get("t")) != IMAGE:
        return {key: _rewritten(item, paths) for key, item in node.items()}
    local = paths.get(_target(node))
    if local is None:
        return node
    content = sequence(node.get("c"))
    target = sequence(_at(content, 2))
    return {**node, "c": [_at(content, 0), _at(content, 1), [local, _at(target, 1) or ""]]}


def _target(node: dict[str, object]) -> str:
    """Read one `Image` node's `src`, which Pandoc carries as the first half of its target."""

    return text(_at(sequence(_at(sequence(node.get("c")), 2)), 0)) or ""


def _cover_locator(ast: dict[str, object]) -> str | None:
    """Read the locator the document's `cover-image` metadata names, where it names one."""

    stated = mapping(ast.get("meta")).get(COVER)
    if stated is None:
        return None
    node = mapping(stated)
    if text(node.get("t")) == META_STRING:
        return text(node.get("c")) or ""
    return "".join(text(mapping(item).get("c")) or "" for item in sequence(node.get("c")))


def _remote(locator: str) -> bool:
    return fetchable(urlsplit(locator).scheme)


def _local(locator: str) -> bool:
    """Say whether `prepare` can already resolve this locator without retrieving anything.

    An inline reference qualifies for the same reason a relative path does: preparation reads its
    bytes with no network, so localisation has nothing to add and must not refuse over it.
    """

    if is_inline(locator):
        return True
    split = urlsplit(locator)
    return split.scheme.lower() in LOCAL_SCHEMES and not split.netloc


def _at(content: object, index: int) -> object:
    values = sequence(content)
    return values[index] if index < len(values) else None


def _covered(ast: dict[str, object], paths: dict[str, str]) -> dict[str, object]:
    """Point the `cover-image` metadata at the file its bytes were written to, where it names one.

    The carrier is kept: a value Pandoc read as `MetaString` is written back as one and a
    `MetaInlines` as one, so the only thing that moved is the locator itself.
    """

    meta = mapping(ast.get("meta"))
    locator = _cover_locator(ast)
    local = None if locator is None else paths.get(locator)
    if local is None:
        return meta
    stated = mapping(meta.get(COVER))
    if text(stated.get("t")) == META_STRING:
        return {**meta, COVER: {"t": META_STRING, "c": local}}
    return {**meta, COVER: {"t": META_INLINES, "c": [{"t": "Str", "c": local}]}}

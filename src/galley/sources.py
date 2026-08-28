"""Classify what a user handed `inspect`, before any workflow reads it.

Which kinds Galley accepts is release-scope data, not Device Profile data, so a second profile
never changes what can be read. Everything this module decides comes from that data.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

from galley.json_reading import mapping, sequence, text
from galley.release_data import SOURCE_KINDS, release_document

MARKDOWN = "markdown"
ARTICLE_URL = "article-url"
UNSUPPORTED_SCHEME = "unsupported-url-scheme"
UNKNOWN_LOCAL = "unknown-local-kind"
# A one-character "scheme" is a Windows drive letter, not a locator scheme.
SCHEME_MINIMUM = 2


@dataclass(frozen=True)
class SourceKind:
    """One kind of thing a user can name, and what Galley does with it."""

    id: str
    statement: str
    supported: bool
    reason: str = ""
    suffixes: frozenset[str] = frozenset()
    schemes: frozenset[str] = frozenset()


def classify(source: str) -> SourceKind:
    """Name the source kind one locator or path is, without reading it."""

    scheme = _scheme(source)
    if scheme:
        return _by_scheme(scheme)
    return local_kind(Path(source))


def local_kind(path: Path) -> SourceKind:
    """Name the source kind one local file is, from its suffix and the release data alone.

    An Inbox walk asks this rather than `classify`, because a filename is not a locator: a file
    genuinely called `mailto:notes.md` would otherwise be read as an unsupported URL scheme.
    """

    suffix = path.suffix.lower()
    for kind in _kinds():
        if suffix and suffix in kind.suffixes:
            return kind
    return _kind(UNKNOWN_LOCAL)


def local_path(source: str) -> Path | None:
    """Return the local file a locator names, or None where it names a remote one.

    Every local file a user names is protected from this command's own outputs, whatever kind it
    turned out to be: naming a file Galley refuses is not permission to overwrite it.
    """

    return None if _scheme(source) else Path(source)


def accepted_routes() -> list[str]:
    """State every route Galley does accept, for a refusal that leaves the user somewhere."""

    return [kind.statement for kind in _kinds() if kind.supported]


def supported_kind_ids() -> list[str]:
    """Name every source kind Galley accepts, for release data that must agree with them."""

    return sorted(kind.id for kind in _kinds() if kind.supported)


def _by_scheme(scheme: str) -> SourceKind:
    for kind in _kinds():
        if scheme in kind.schemes:
            return kind
    return _kind(UNSUPPORTED_SCHEME)


def _scheme(source: str) -> str:
    scheme = urlsplit(source.strip()).scheme.lower()
    return scheme if len(scheme) >= SCHEME_MINIMUM else ""


def _kind(identifier: str) -> SourceKind:
    for kind in _kinds():
        if kind.id == identifier:
            return kind
    return SourceKind(id=identifier, statement=identifier, supported=False)


@cache
def _kinds() -> tuple[SourceKind, ...]:
    document = release_document(SOURCE_KINDS)
    return tuple(
        SourceKind(
            id=text(entry.get("id")) or "",
            statement=" ".join((text(entry.get("statement")) or "").split()),
            supported=supported,
            reason=" ".join((text(entry.get("reason")) or "").split()),
            suffixes=_names(entry, "suffixes"),
            schemes=_names(entry, "schemes"),
        )
        for supported, group in ((True, "supported"), (False, "refused"))
        for value in sequence(document.get(group))
        if (entry := mapping(value))
    )


def _names(entry: dict[str, object], key: str) -> frozenset[str]:
    return frozenset(value.lower() for item in sequence(entry.get(key)) if (value := text(item)))

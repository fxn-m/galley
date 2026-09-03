"""Resolve local, inline or article image bytes under the source's retrieval policy."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, unquote, urlsplit

from galley.images.inline import inline_bytes, inline_label, is_inline
from galley.locations import display_path
from galley.tools.fetching import fetch_resource, fetchable

LOCAL_SCHEMES = frozenset({"", "file"})


@dataclass(frozen=True)
class ResourceOrigin:
    """Where one Canonical Document's image references resolve from.

    A Markdown source resolves relative references against its own directory and retrieves
    nothing; an Article-Like Page has no directory and its references were already resolved to
    absolute locations by extraction, so it retrieves them from the page it came from. Keeping
    both in one value is what lets every step after resolution be the same step.
    """

    directory: Path | None = None
    retrieves: bool = False


@dataclass(frozen=True)
class Resolved:
    """The bytes one reference names, and the name they are reported under."""

    data: bytes
    display: str


def resolved_bytes(origin: ResourceOrigin, src: str) -> Resolved | str:
    """Produce the bytes one reference names, or the reason this source cannot produce them.

    An inline reference is answered before either origin, because it belongs to neither: its
    bytes travelled inside the document, so the same answer is right whichever route the document
    arrived by, and no socket and no file is involved.

    A retrieving origin resolves what it can retrieve and nothing else. Extraction has already
    resolved every reference against the page's own address, so anything left that is not an
    http or https locator is not part of the page — and a page must never be able to name a path
    on the machine preparing it and have those bytes read into a book. A data URI names no path,
    so admitting it takes nothing away from that.
    """

    if is_inline(src):
        inline = inline_bytes(src)
        return inline if isinstance(inline, str) else Resolved(inline, inline_label(src))
    split = urlsplit(src)
    if origin.retrieves:
        if not fetchable(split.scheme):
            return "unsupported-location"
        fetched = fetch_resource(src)
        if fetched.data is None:
            return fetched.reason or "unfetchable-resource"
        return Resolved(fetched.data, src)
    location = _location(origin.directory, split)
    if location is None:
        return "unsupported-location"
    try:
        return Resolved(location.read_bytes(), display_path(location))
    except FileNotFoundError:
        return "missing-resource"
    except OSError:
        return "unreadable-resource"


def _location(directory: Path | None, split: SplitResult) -> Path | None:
    """Resolve one reference against the source document's own directory, or refuse to guess.

    A source that is not a local file has no directory to resolve against, so a relative
    reference is unresolvable rather than resolvable somewhere arbitrary.
    """

    if split.scheme.lower() not in LOCAL_SCHEMES or split.netloc:
        return None
    path = unquote(split.path)
    if not path:
        return None
    if Path(path).is_absolute():
        return Path(path)
    return None if directory is None else directory / path

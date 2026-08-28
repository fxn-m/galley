"""Retrieve one referenced resource over HTTP, bounded, with every way it can fail named.

Defuddle owns retrieving the page. This module retrieves only what a document already references
— the images its work is partly made of — and it is deliberately the narrowest thing that can do
that: one GET, a timeout, and a byte ceiling. Nothing here decides whether a resource is wanted;
it answers what the bytes are, or why there are none.

Two documents reference their images at different levels of trust, so there are two entry points
over one set of bounds. An Article-Like Page is a URL the user navigated to and its images are
part of the work they asked for, so `fetch_resource` retrieves them under ordinary resource
bounds. A Markdown file's image URLs are whatever arrived inside a document, so `fetch_reference`
adds two protections: the host is resolved and judged before a socket is opened for it, refused
where any address is private, loopback or link-local; and the opener is built without redirect
following, so a 3xx becomes an error and no second request is ever made. The address check is the
one that happens before the socket opens, and the request is still made by name — so this is a
boundary against a careless or hostile document rather than against an attacker who already
controls DNS.
"""

from dataclasses import dataclass
from typing import Literal, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from galley.network import local_address, no_redirect_opener, resolved_addresses

TIMEOUT_SECONDS = 30
# A page resource far past this is not an illustration Galley is going to fit on a 480×800 panel,
# and reading it whole would let one page decide how much memory a preparation run uses.
MAXIMUM_BYTES = 32 * 1024 * 1024
USER_AGENT = "galley"
SCHEMES = frozenset({"http", "https"})
DEFAULT_PORTS = {"http": 80, "https": 443}
REDIRECTS = range(300, 400)

FetchReason = Literal["unfetchable-resource", "oversize-resource"]
ReferenceReason = Literal[
    "unsupported-locator",
    "unresolvable-host",
    "blocked-host",
    "redirected",
    "http-error",
    "oversize",
]


@dataclass(frozen=True)
class Fetched:
    """One retrieval attempt: the bytes it produced, or the reason it produced none."""

    data: bytes | None
    detail: str = ""
    reason: FetchReason | None = None


@dataclass(frozen=True)
class Addresses:
    """Which resolved addresses a guarded retrieval may open a socket to.

    `local_permitted` exists for one reason and has one kind of caller: a behavioural test needs
    a real retrieval, and loopback is the only server there is offline. No command line,
    environment variable or configuration key produces a value with it set — the CLI passes
    `PUBLIC_ONLY`, and widening it is an edit to a test, inside the test's own process.
    """

    local_permitted: bool = False


PUBLIC_ONLY = Addresses()
LOCAL_PERMITTED = Addresses(local_permitted=True)


@dataclass(frozen=True)
class Retrieved:
    """One guarded retrieval: the bytes, what the host resolved to, and how the transport ended."""

    data: bytes | None
    addresses: tuple[str, ...] = ()
    status: int | None = None
    detail: str = ""
    reason: ReferenceReason | None = None


def fetch_resource(url: str) -> Fetched:
    """Retrieve one referenced resource over http or https, refusing to read past the ceiling.

    The scheme is checked here as well as by the caller, because this is the function that opens
    the locator: `urlopen` would otherwise honour `file:` and turn a page's reference into a read
    of the preparing machine's own disk.
    """

    if not fetchable(urlsplit(url).scheme):
        return Fetched(None, f"{url} is not an http or https locator", "unfetchable-resource")
    try:
        with urlopen(_request(url), timeout=TIMEOUT_SECONDS) as response:
            data = cast(bytes, response.read(MAXIMUM_BYTES + 1))
    except HTTPError as error:
        return Fetched(None, f"{url} answered {error.code}", "unfetchable-resource")
    except (URLError, OSError, ValueError) as error:
        return Fetched(None, f"{url} could not be retrieved: {error}", "unfetchable-resource")
    if len(data) > MAXIMUM_BYTES:
        return Fetched(None, f"{url} is larger than {MAXIMUM_BYTES} bytes", "oversize-resource")
    return Fetched(data)


def fetch_reference(url: str, *, permitted: Addresses = PUBLIC_ONLY) -> Retrieved:
    """Retrieve one lower-trust reference, judging its host before a socket is opened for it.

    The order is why this exists beside the function above. The scheme is read, the host is
    resolved, every address it answered with is judged, and only then is a request made — through
    an opener with redirect following removed, so a host that passed cannot hand the request on
    to one that would not have.
    """

    split = urlsplit(url)
    if not fetchable(split.scheme) or not split.hostname:
        return Retrieved(
            None,
            reason="unsupported-locator",
            detail=f"{url} is not an http or https locator naming a host",
        )
    judged = _judged_host(
        split.hostname, split.port or DEFAULT_PORTS[split.scheme.lower()], permitted
    )
    if isinstance(judged, Retrieved):
        return judged
    return _retrieved(url, judged)


def _judged_host(hostname: str, port: int, permitted: Addresses) -> Retrieved | tuple[str, ...]:
    """Resolve one host and refuse it, or hand back the addresses that allowed it through."""

    try:
        resolved = resolved_addresses(hostname, port)
    except OSError as error:
        return Retrieved(
            None, reason="unresolvable-host", detail=f"{hostname} did not resolve: {error}"
        )
    if not resolved:
        return Retrieved(
            None, reason="unresolvable-host", detail=f"{hostname} resolved to no address at all"
        )
    local = [] if permitted.local_permitted else [a for a in resolved if local_address(a)]
    if local:
        return Retrieved(
            None,
            addresses=resolved,
            reason="blocked-host",
            detail=f"{hostname} resolves onto a local network: {', '.join(local)}",
        )
    return resolved


def _retrieved(url: str, addresses: tuple[str, ...]) -> Retrieved:
    """Perform the one bounded, redirect-free GET a permitted reference has earned."""

    try:
        with no_redirect_opener().open(_request(url), timeout=TIMEOUT_SECONDS) as response:
            status = cast(int, response.status)
            data = cast(bytes, response.read(MAXIMUM_BYTES + 1))
    except HTTPError as error:
        return Retrieved(
            None,
            addresses=addresses,
            status=error.code,
            reason="redirected" if error.code in REDIRECTS else "http-error",
            detail=f"{url} answered {error.code}",
        )
    except (URLError, OSError, ValueError) as error:
        return Retrieved(
            None,
            addresses=addresses,
            reason="http-error",
            detail=f"{url} could not be retrieved: {error}",
        )
    if len(data) > MAXIMUM_BYTES:
        return Retrieved(
            None,
            addresses=addresses,
            status=status,
            reason="oversize",
            detail=f"{url} is larger than {MAXIMUM_BYTES} bytes",
        )
    return Retrieved(data, addresses=addresses, status=status)


def _request(url: str) -> Request:
    """Build the one GET both entry points make, under Galley's own name."""

    return Request(url, headers={"User-Agent": USER_AGENT})


def fetchable(scheme: str) -> bool:
    """Say whether a reference names a scheme this module retrieves."""

    return scheme.lower() in SCHEMES

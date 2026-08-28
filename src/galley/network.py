"""Settle the two network questions Galley's separate HTTP clients both have to answer.

Galley opens sockets for two unrelated jobs and keeps a bounded client for each, because each
needs the opposite of the other's address rule: Delivery writes to a CrossPoint and allows only
loopback, private and link-local addresses, while localisation reads an image off the public web
and refuses exactly those. What the two share is smaller than a client and
older than either — how a host is resolved before a socket is opened, whether an address it
answered with is on a local network, and an opener that treats a redirect as an error instead of
following it. Only those primitives live here; each policy stays with the package that holds it.

Resolution happens before the request and the request is still made by name, so a host that
answers differently a moment later is not caught. Both callers state that limit where they apply
the rule: this is a boundary against a hostile or careless configuration or document, not against
an attacker who already controls the network's DNS.
"""

import socket
from email.message import Message
from ipaddress import ip_address
from typing import IO
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener


def resolved_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Every address one hostname would be reached at, literals included, in stable order.

    Raises `OSError` where the name does not resolve, and returns an empty tuple where it
    resolves to nothing at all. Both are the caller's to name, because what an unresolvable host
    means differs entirely between a device that is asleep and a document naming a host that
    never existed.
    """

    found = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return tuple(sorted({str(entry[4][0]) for entry in found}))


def local_address(address: str) -> bool:
    """Say whether one resolved address is on a local network rather than the public internet.

    A scoped IPv6 literal carries the interface after a percent sign, which is part of how it is
    reached rather than part of the address; it is dropped before the address is judged. Anything
    that does not parse as an address at all is not treated as local, so a caller that allows only
    local addresses refuses it and a caller that refuses local addresses must check it separately.
    """

    try:
        parsed = ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return parsed.is_loopback or parsed.is_private or parsed.is_link_local


def no_redirect_opener() -> OpenerDirector:
    """Build an opener with redirect following removed rather than trusted."""

    return build_opener(_NoRedirects)


class _NoRedirects(HTTPRedirectHandler):
    """Turn every redirect into an error, so one allowed host cannot hand the request onward."""

    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> Request | None:
        """Refuse to build a follow-up request, which makes urllib raise the 3xx as an error."""

        return None

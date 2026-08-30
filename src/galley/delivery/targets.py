"""Decide whether a configured CrossPoint host is a target Galley is allowed to send bytes to.

CrossPoint's HTTP surface is unauthenticated and unencrypted, so a configurable host must not
quietly turn Galley into a public-network document sender. The rule is a property of
the addresses a target resolves to rather than of the name: every one of them must be loopback,
private or link-local, and a name that resolves to a mixture refuses. `.local` satisfies this by
construction, because mDNS answers with link-local or private addresses.

Resolution and the local-address test are `galley.network`'s, which localisation also uses with
the verdict the other way up. Resolution happens here, before any request is made, and the
addresses it produced are both retained as evidence and used directly by the CrossPoint client.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from galley.delivery.refusals import DeliveryRefusal
from galley.network import local_address, resolved_addresses

TARGET_STAGE = "delivery-target"
DEFAULT_PORT = 80


@dataclass(frozen=True)
class DeliveryTarget:
    """One validated CrossPoint target: where to connect, and what it resolved to."""

    host: str
    hostname: str
    port: int
    addresses: tuple[str, ...]
    timeout_seconds: float

    def facts(self) -> dict[str, object]:
        """State the target and the exact addresses that were allowed before anything was sent.

        These are the half of the device facts that exist before the device has said anything,
        so they are recorded under the same name — a reader asking what Galley was talking to
        gets one answer whether or not it answered.
        """

        return {
            "host": self.host,
            "port": self.port,
            "addresses": list(self.addresses),
            "timeout_seconds": self.timeout_seconds,
            "model": None,
            "firmware": None,
            "mode": None,
            "status": None,
        }


def trusted_target(host: str, timeout_seconds: float) -> DeliveryTarget | DeliveryRefusal:
    """Parse one `HOST[:PORT]`, resolve it, and allow it only if every address is local."""

    parsed = _parsed(host)
    if isinstance(parsed, DeliveryRefusal):
        return parsed
    hostname, port = parsed
    addresses = _resolved(hostname, port)
    if isinstance(addresses, DeliveryRefusal):
        return addresses
    public = [found for found in addresses if not local_address(found)]
    if public:
        return DeliveryRefusal(
            boundary="untrusted-delivery-target",
            stage=TARGET_STAGE,
            summary=(
                f"{host} resolves outside the local network, which CrossPoint Delivery "
                f"never writes to: {', '.join(public)}"
            ),
            fact={"host": host, "addresses": list(addresses), "public_addresses": public},
        )
    return DeliveryTarget(host, hostname, port, addresses, timeout_seconds)


def _parsed(host: str) -> tuple[str, int] | DeliveryRefusal:
    """Read `HOST[:PORT]` as a bare authority, refusing anything carrying more than that."""

    invalid = DeliveryRefusal(
        boundary="invalid-delivery-host",
        stage=TARGET_STAGE,
        summary=f"not a hostname or address with an optional port: {host!r}",
        fact={"host": host},
    )
    if not host or any(character.isspace() for character in host):
        return invalid
    try:
        split = urlsplit(f"http://{host}")
        port = split.port
    except ValueError:
        return invalid
    if split.hostname is None or split.username or split.password:
        return invalid
    if split.path or split.query or split.fragment:
        return invalid
    return split.hostname, port or DEFAULT_PORT


def _resolved(hostname: str, port: int) -> tuple[str, ...] | DeliveryRefusal:
    """Resolve one hostname to every address it would be reached at, literals included."""

    try:
        addresses = resolved_addresses(hostname, port)
    except OSError as error:
        return DeliveryRefusal(
            boundary="unresolvable-delivery-target",
            stage=TARGET_STAGE,
            summary=f"{hostname} did not resolve: {error}",
            fact={"hostname": hostname, "detail": str(error)},
        )
    if not addresses:
        return DeliveryRefusal(
            boundary="unresolvable-delivery-target",
            stage=TARGET_STAGE,
            summary=f"{hostname} resolved to no address at all",
            fact={"hostname": hostname, "detail": "no addresses"},
        )
    return addresses

"""Speak CrossPoint's own HTTP surface directly, and name every way it can fail to answer.

CrossPoint exposes an unauthenticated `GET /api/status`, `GET /api/files` and multipart
`POST /upload` on the device itself. Galley uses those rather than the Optimize action a user has
to tick by hand. This is the narrowest client that can do it: http only,
one finite timeout per request, a ceiling on how much of a response is read, and redirects
switched off so an allowed target cannot hand document bytes to somewhere else.

`tools/fetching.py` is not reused. Its page-resource retrieval follows redirects, judges no
address and only ever performs a GET — three properties Delivery needs the opposite of. What the
two clients do share is the handful of primitives in `galley.network`.
"""

import json
import socket
from dataclasses import dataclass
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import OpenerDirector, Request

from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget
from galley.json_reading import integer, mapping, sequence, text
from galley.network import no_redirect_opener

STATUS_STAGE = "device-status"
LISTING_STAGE = "destination-listing"
# A CrossPoint status or listing is a short JSON document. Reading past this would let a device
# on the far end of the socket decide how much memory a Delivery run uses.
RESPONSE_LIMIT = 1_000_000
STATUS_PATH = "/api/status"
FILES_PATH = "/api/files"


@dataclass(frozen=True)
class DeviceStatus:
    """What one CrossPoint device said it is, with its whole answer retained as evidence."""

    model: str
    firmware: str
    mode: str | None
    status: dict[str, object]

    def facts(self) -> dict[str, object]:
        """State the identified fields and the complete status response behind them."""

        return {
            "model": self.model,
            "firmware": self.firmware,
            "mode": self.mode,
            "status": self.status,
        }


@dataclass(frozen=True)
class RemoteEntry:
    """One file CrossPoint listed at the destination, as name and byte size alone."""

    name: str
    byte_size: int | None

    def facts(self) -> dict[str, object]:
        """State the two properties a Delivery decision is ever allowed to rest on."""

        return {"name": self.name, "byte_size": self.byte_size}


@dataclass(frozen=True)
class Listing:
    """One destination listing, reported as the entry Delivery asked about and nothing else."""

    entries: tuple[RemoteEntry, ...]

    def matching(self, filename: str) -> RemoteEntry | None:
        """Find the listed file with this exact name, which is the only one Delivery acts on."""

        return next((entry for entry in self.entries if entry.name == filename), None)

    def facts(self, filename: str) -> dict[str, object]:
        """Record how much was listed and the one entry that matters, never the whole listing."""

        found = self.matching(filename)
        return {
            "entry_count": len(self.entries),
            "matching": None if found is None else found.facts(),
        }


def device_status(target: DeliveryTarget) -> DeviceStatus | DeliveryRefusal:
    """Ask one CrossPoint device what it is, refusing anything that is not a usable answer."""

    payload = _request_json(target, STATUS_PATH, STATUS_STAGE, "read device status")
    if isinstance(payload, DeliveryRefusal):
        return payload
    status = mapping(payload)
    model = text(status.get("device"))
    firmware = text(status.get("version"))
    mode = status.get("mode")
    if not model or not firmware or not isinstance(mode, str | None):
        return DeliveryRefusal(
            boundary="unusable-device-status",
            stage=STATUS_STAGE,
            summary=f"{target.host} did not report a device type and firmware version",
            fact={"host": target.host, "status": status},
        )
    return DeviceStatus(model, firmware, mode or None, status)


def destination_listing(target: DeliveryTarget, destination: str) -> Listing | DeliveryRefusal:
    """Read what the configured destination currently holds, without writing anything.

    **An empty listing does not mean the folder is there.** Measured against a real X4 at firmware
    1.4.1 on 2026-08-20: CrossPoint answers an empty list for a folder that does not exist, exactly
    as it does for one that exists and holds nothing. So a Delivery Plan over a missing destination
    reports `upload-new` — right about the action, and unable to say the folder is absent — and the
    upload that follows is refused by the device with HTTP 400. That refusal is honest and
    retryable and leaves the Ready Artifact untouched, so nothing here works around it; what this
    note prevents is a reader taking a clean plan as proof the destination is ready.
    """

    query = urlencode({"path": destination})
    payload = _request_json(target, f"{FILES_PATH}?{query}", LISTING_STAGE, f"list {destination}")
    if isinstance(payload, DeliveryRefusal):
        return payload
    listed = sequence(payload)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in listed):
        return DeliveryRefusal(
            boundary="unusable-destination-listing",
            stage=LISTING_STAGE,
            summary=f"{target.host} did not return a file listing for {destination}",
            fact={"destination": destination, "host": target.host},
        )
    return Listing(tuple(entry for entry in map(_entry, listed) if entry is not None))


def _entry(value: object) -> RemoteEntry | None:
    """Read one listed file, ignoring directories and anything without a usable name."""

    item = mapping(value)
    name = text(item.get("name"))
    if not name or item.get("isDirectory") is True:
        return None
    return RemoteEntry(name, integer(item.get("size")))


def _request_json(
    target: DeliveryTarget, path: str, stage: str, label: str
) -> object | DeliveryRefusal:
    """Perform one bounded, redirect-free GET and read its body as JSON, or say why not."""

    request = Request(f"{target.base_url}{path}", method="GET")
    try:
        with opener().open(request, timeout=target.timeout_seconds) as response:
            body = cast(bytes, response.read(RESPONSE_LIMIT + 1))
    except HTTPError as error:
        return DeliveryRefusal(
            boundary="device-unavailable",
            stage=stage,
            summary=f"could not {label}: {target.host} answered {error.code}",
            fact={"host": target.host, "status": error.code},
        )
    except (URLError, OSError, ValueError) as error:
        return DeliveryRefusal(
            boundary="device-unavailable",
            stage=stage,
            summary=f"could not {label}: {network_cause(error)}",
            fact={"host": target.host, "detail": str(error)},
        )
    if len(body) > RESPONSE_LIMIT:
        return DeliveryRefusal(
            boundary="oversize-device-response",
            stage=stage,
            summary=f"could not {label}: the response exceeded {RESPONSE_LIMIT} bytes",
            fact={"host": target.host, "limit": RESPONSE_LIMIT},
        )
    try:
        return cast(object, json.loads(body))
    except UnicodeDecodeError, ValueError:
        return DeliveryRefusal(
            boundary="unusable-device-response",
            stage=stage,
            summary=f"could not {label}: the response was not JSON",
            fact={"host": target.host},
        )


def network_cause(error: BaseException) -> str:
    """Say what actually went wrong on the wire, in words a reader can act on.

    `<urlopen error [Errno 8] nodename nor servname provided>` tells a user nothing about what
    to do next; "the host name did not resolve" tells them the device is not on this network.
    """

    reason = cast(object, error.reason) if isinstance(error, URLError) else error
    if isinstance(reason, socket.gaierror):
        return "the host name did not resolve"
    if isinstance(reason, TimeoutError):
        return "no response before the timeout"
    if isinstance(reason, ConnectionRefusedError):
        return "the connection was refused"
    return str(error)


def opener() -> OpenerDirector:
    """Build the one opener Delivery uses, with redirect following removed rather than trusted."""

    return no_redirect_opener()

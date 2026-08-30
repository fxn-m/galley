"""Own CrossPoint status, listing and upload behind one deep client interface.

Callers use Delivery concepts and never construct HTTP exchanges. The production Python adapter
and controlled test adapters share one internal transport seam; redirect refusal, bounded reads,
JSON interpretation and multipart streaming stay local to this module.
"""

import json
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from typing import Generic, TypeVar, cast
from urllib.error import URLError
from urllib.parse import urlencode

from galley.delivery.crosspoint_transport import (
    PythonHttpTransport,
    Transport,
    TransportFailure,
    TransportRequest,
    TransportResponse,
)
from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget
from galley.json_reading import integer, mapping, sequence, text

STATUS_STAGE = "device-status"
LISTING_STAGE = "destination-listing"
UPLOAD_STAGE = "upload"
STATUS_PATH = "/api/status"
FILES_PATH = "/api/files"
UPLOAD_PATH = "/upload"
RESPONSE_LIMIT = 1_000_000
FIELD_NAME = "file"
CONTENT_TYPE = "application/epub+zip"
CHUNK = 1 << 16

ResultValue = TypeVar("ResultValue")


@dataclass(frozen=True)
class Exchange:
    """One ordered CrossPoint exchange fact retained inside the client result."""

    stage: str
    status: int | None = None
    request_began: bool = False
    detail: str = ""


@dataclass(frozen=True)
class ClientResult(Generic[ResultValue]):
    """One semantic answer and the exchanges that established it."""

    value: ResultValue | DeliveryRefusal
    exchanges: tuple[Exchange, ...] = ()


@dataclass(frozen=True)
class Transfer:
    """What CrossPoint answered to one upload, without claiming Delivery."""

    status: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class DeviceStatus:
    """What one CrossPoint device said it is, with its whole answer retained."""

    model: str
    firmware: str
    mode: str | None
    status: dict[str, object]

    def facts(self) -> dict[str, object]:
        return {
            "model": self.model,
            "firmware": self.firmware,
            "mode": self.mode,
            "status": self.status,
        }


@dataclass(frozen=True)
class RemoteEntry:
    """One listed file, reduced to the facts Delivery can act on."""

    name: str
    byte_size: int | None

    def facts(self) -> dict[str, object]:
        return {"name": self.name, "byte_size": self.byte_size}


@dataclass(frozen=True)
class Listing:
    """One destination listing returned in Delivery concepts."""

    entries: tuple[RemoteEntry, ...]

    def matching(self, filename: str) -> RemoteEntry | None:
        return next((entry for entry in self.entries if entry.name == filename), None)

    def facts(self, filename: str) -> dict[str, object]:
        found = self.matching(filename)
        return {
            "entry_count": len(self.entries),
            "matching": None if found is None else found.facts(),
        }


class _MultipartBody:
    """A repeatable, length-declaring multipart body streamed from disk."""

    def __init__(self, artifact: Path, boundary: str) -> None:
        self.artifact = artifact
        self.prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{FIELD_NAME}"; '
            f'filename="{artifact.name}"\r\n'
            f"Content-Type: {CONTENT_TYPE}\r\n\r\n"
        ).encode()
        self.suffix = f"\r\n--{boundary}--\r\n".encode()
        self.content_length = len(self.prefix) + artifact.stat().st_size + len(self.suffix)

    def __iter__(self) -> Iterator[bytes]:
        yield self.prefix
        with self.artifact.open("rb") as book:
            while chunk := book.read(CHUNK):
                yield chunk
        yield self.suffix


class CrossPointClient:
    """Read status, list a destination and upload one artifact to a trusted target."""

    def __init__(self, target: DeliveryTarget, transport: Transport | None = None) -> None:
        self._target = target
        self._transport = transport if transport is not None else PythonHttpTransport()

    def status(self) -> ClientResult[DeviceStatus]:
        payload, exchange = self._json(STATUS_PATH, STATUS_STAGE, "read device status")
        if isinstance(payload, DeliveryRefusal):
            return ClientResult(payload, (exchange,))
        status = mapping(payload)
        model = text(status.get("device"))
        firmware = text(status.get("version"))
        mode = status.get("mode")
        if not model or not firmware or not isinstance(mode, str | None):
            refusal = DeliveryRefusal(
                "unusable-device-status",
                STATUS_STAGE,
                f"{self._target.host} did not report a device type and firmware version",
                {"host": self._target.host, "status": status},
            )
            return ClientResult(refusal, (exchange,))
        return ClientResult(DeviceStatus(model, firmware, mode or None, status), (exchange,))

    def listing(self, destination: str) -> ClientResult[Listing]:
        """List one folder without inferring that an empty result proves the folder exists."""

        query = urlencode({"path": destination})
        payload, exchange = self._json(
            f"{FILES_PATH}?{query}", LISTING_STAGE, f"list {destination}"
        )
        if isinstance(payload, DeliveryRefusal):
            return ClientResult(payload, (exchange,))
        listed = sequence(payload)
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in listed):
            refusal = DeliveryRefusal(
                "unusable-destination-listing",
                LISTING_STAGE,
                f"{self._target.host} did not return a file listing for {destination}",
                {"destination": destination, "host": self._target.host},
            )
            return ClientResult(refusal, (exchange,))
        entries = tuple(entry for entry in map(_entry, listed) if entry is not None)
        return ClientResult(Listing(entries), (exchange,))

    def upload(self, destination: str, artifact: Path) -> ClientResult[Transfer]:
        boundary = f"galley-{token_hex(16)}"
        body = _MultipartBody(artifact, boundary)
        request = TransportRequest(
            "POST",
            f"{UPLOAD_PATH}?{urlencode({'path': destination})}",
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(body.content_length),
            },
            body,
        )
        response, exchange = self._send(UPLOAD_STAGE, request)
        if isinstance(response, TransportFailure):
            transfer = Transfer(None, network_cause(response.error))
        else:
            transfer = Transfer(response.status, response.detail)
        return ClientResult(transfer, (exchange,))

    def _json(
        self, path: str, stage: str, label: str
    ) -> tuple[object | DeliveryRefusal, Exchange]:
        response, exchange = self._send(stage, TransportRequest("GET", path))
        if isinstance(response, TransportFailure):
            cause = network_cause(response.error)
            return self._unavailable(stage, label, cause, str(response.error)), exchange
        if not 200 <= response.status < 300:
            detail = f"{self._target.host} answered {response.status}"
            return self._unavailable(stage, label, detail, status=response.status), exchange
        if len(response.body) > RESPONSE_LIMIT:
            refusal = DeliveryRefusal(
                "oversize-device-response",
                stage,
                f"could not {label}: the response exceeded {RESPONSE_LIMIT} bytes",
                {"host": self._target.host, "limit": RESPONSE_LIMIT},
            )
            return refusal, exchange
        try:
            return cast(object, json.loads(response.body)), exchange
        except UnicodeDecodeError, ValueError:
            refusal = DeliveryRefusal(
                "unusable-device-response",
                stage,
                f"could not {label}: the response was not JSON",
                {"host": self._target.host},
            )
            return refusal, exchange

    def _send(
        self, stage: str, request: TransportRequest
    ) -> tuple[TransportResponse | TransportFailure, Exchange]:
        response = self._transport.exchange(self._target, request)
        if isinstance(response, TransportFailure):
            detail = network_cause(response.error)
            return response, Exchange(stage, request_began=response.request_began, detail=detail)
        return response, Exchange(stage, response.status, True, response.detail)

    def _unavailable(
        self, stage: str, label: str, summary: str, detail: str = "", status: int | None = None
    ) -> DeliveryRefusal:
        fact: dict[str, object] = {"host": self._target.host}
        if status is not None:
            fact["status"] = status
        else:
            fact["detail"] = detail
        return DeliveryRefusal("device-unavailable", stage, f"could not {label}: {summary}", fact)


def _entry(value: object) -> RemoteEntry | None:
    item = mapping(value)
    name = text(item.get("name"))
    if not name or item.get("isDirectory") is True:
        return None
    return RemoteEntry(name, integer(item.get("size")))


def network_cause(error: BaseException) -> str:
    """Turn raw network exceptions into the existing actionable summaries."""

    reason = cast(object, error.reason) if isinstance(error, URLError) else error
    if isinstance(reason, socket.gaierror):
        return "the host name did not resolve"
    if isinstance(reason, TimeoutError):
        return "no response before the timeout"
    if isinstance(reason, ConnectionRefusedError):
        return "the connection was refused"
    return str(error)

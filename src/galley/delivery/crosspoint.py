"""Own CrossPoint status, listing and upload behind one deep client interface.

Callers use Delivery concepts and never construct HTTP exchanges. The production Python adapter
and controlled test adapters share one internal transport seam; redirect refusal, bounded reads,
JSON interpretation and multipart streaming stay local to this module.
"""

import json
import socket
from collections.abc import Iterator
from pathlib import Path
from secrets import token_hex
from time import monotonic
from typing import cast
from urllib.error import URLError
from urllib.parse import urlencode

from galley.delivery.crosspoint_transport import (
    PythonHttpTransport,
    Transport,
    TransportFailure,
    TransportRequest,
    TransportResponse,
)
from galley.delivery.crosspoint_results import (
    ClientResult,
    DeviceStatus,
    Exchange,
    Listing,
    RemoteEntry,
    Transfer,
)
from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget
from galley.json_reading import integer, mapping, sequence, text

STATUS_STAGE = "device-status"
LISTING_STAGE = "destination-listing"
PREFLIGHT_STAGE = "preflight-listing"
POSTFLIGHT_STAGE = "postflight-confirmation"
UPLOAD_STAGE = "upload"
STATUS_PATH = "/api/status"
FILES_PATH = "/api/files"
UPLOAD_PATH = "/upload"
RESPONSE_LIMIT = 1_000_000
FIELD_NAME = "file"
CONTENT_TYPE = "application/epub+zip"
CHUNK = 1 << 16
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
        self._upload_attempted = False
        self._postflight_deadline: float | None = None

    def status(self) -> ClientResult[DeviceStatus]:
        payload, exchanges = self._json(STATUS_PATH, STATUS_STAGE, "read device status")
        if isinstance(payload, DeliveryRefusal):
            return ClientResult(payload, exchanges)
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
            return ClientResult(refusal, exchanges)
        return ClientResult(DeviceStatus(model, firmware, mode or None, status), exchanges)

    def listing(self, destination: str) -> ClientResult[Listing]:
        """List one folder without inferring that an empty result proves the folder exists."""

        stage = POSTFLIGHT_STAGE if self._upload_attempted else PREFLIGHT_STAGE
        if self._upload_attempted and self._postflight_deadline is None:
            self._postflight_deadline = self._deadline()
        deadline = self._postflight_deadline or self._deadline()
        attempts = 1 if self._upload_attempted else 2
        query = urlencode({"path": destination})
        payload, exchanges = self._json(
            f"{FILES_PATH}?{query}",
            stage,
            f"list {destination}",
            refusal_stage=LISTING_STAGE,
            attempts=attempts,
            deadline=deadline,
        )
        if isinstance(payload, DeliveryRefusal):
            return ClientResult(payload, exchanges)
        listed = sequence(payload)
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in listed):
            refusal = DeliveryRefusal(
                "unusable-destination-listing",
                LISTING_STAGE,
                f"{self._target.host} did not return a file listing for {destination}",
                {"destination": destination, "host": self._target.host},
            )
            return ClientResult(refusal, exchanges)
        entries = tuple(entry for entry in map(_entry, listed) if entry is not None)
        return ClientResult(Listing(entries), exchanges)

    def upload(self, destination: str, artifact: Path) -> ClientResult[Transfer]:
        self._upload_attempted = True
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
        response, exchanges = self._send(
            UPLOAD_STAGE,
            request,
            attempts=min(2, len(self._target.addresses)),
            deadline=self._deadline(),
            safe=False,
        )
        if isinstance(response, TransportFailure):
            transfer = Transfer(None, network_cause(response.error))
        else:
            transfer = Transfer(response.status, response.detail)
        return ClientResult(transfer, exchanges)

    def _json(
        self,
        path: str,
        stage: str,
        label: str,
        *,
        refusal_stage: str | None = None,
        attempts: int = 2,
        deadline: float | None = None,
    ) -> tuple[object | DeliveryRefusal, tuple[Exchange, ...]]:
        boundary_stage = refusal_stage or stage
        response, exchanges = self._send(
            stage,
            TransportRequest("GET", path),
            attempts=attempts,
            deadline=deadline or self._deadline(),
            safe=True,
        )
        if isinstance(response, TransportFailure):
            cause = network_cause(response.error)
            return self._unavailable(boundary_stage, label, cause, str(response.error)), exchanges
        if not 200 <= response.status < 300:
            detail = f"{self._target.host} answered {response.status}"
            return self._unavailable(
                boundary_stage, label, detail, status=response.status
            ), exchanges
        if len(response.body) > RESPONSE_LIMIT:
            refusal = DeliveryRefusal(
                "oversize-device-response",
                boundary_stage,
                f"could not {label}: the response exceeded {RESPONSE_LIMIT} bytes",
                {"host": self._target.host, "limit": RESPONSE_LIMIT},
            )
            return refusal, exchanges
        try:
            return cast(object, json.loads(response.body)), exchanges
        except UnicodeDecodeError, ValueError:
            refusal = DeliveryRefusal(
                "unusable-device-response",
                boundary_stage,
                f"could not {label}: the response was not JSON",
                {"host": self._target.host},
            )
            return refusal, exchanges

    def _send(
        self,
        stage: str,
        request: TransportRequest,
        *,
        attempts: int,
        deadline: float,
        safe: bool,
    ) -> tuple[TransportResponse | TransportFailure, tuple[Exchange, ...]]:
        recorded: list[Exchange] = []
        response: TransportResponse | TransportFailure = TransportFailure(
            TimeoutError("operation timeout budget exhausted"), request_began=False
        )
        for index in range(attempts):
            address = self._target.addresses[index % len(self._target.addresses)]
            remaining = deadline - monotonic()
            response = (
                self._transport.exchange(self._target, address, request, remaining)
                if remaining > 0
                else TransportFailure(
                    TimeoutError("operation timeout budget exhausted"), request_began=False
                )
            )
            recorded.append(self._exchange(stage, address, response))
            if not isinstance(response, TransportFailure):
                break
            if not safe and (response.request_began or index + 1 >= len(self._target.addresses)):
                break
        return response, tuple(recorded)

    def _exchange(
        self,
        stage: str,
        address: str,
        response: TransportResponse | TransportFailure,
    ) -> Exchange:
        if isinstance(response, TransportFailure):
            return Exchange(
                stage,
                address,
                self._transport.name,
                request_began=response.request_began,
                outcome="failed" if response.request_began else "not-started",
                detail=network_cause(response.error),
            )
        return Exchange(
            stage,
            address,
            self._transport.name,
            response.status,
            True,
            "response",
            response.detail,
        )

    def _deadline(self) -> float:
        return monotonic() + self._target.timeout_seconds

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

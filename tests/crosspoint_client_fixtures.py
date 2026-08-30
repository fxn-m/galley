"""Controlled adapters shared by the deep CrossPoint client tests."""

from types import TracebackType
from urllib.request import Request

from galley.delivery.crosspoint import TransportFailure, TransportRequest, TransportResponse
from galley.delivery.targets import DeliveryTarget


class ControlledTransport:
    def __init__(
        self, *responses: TransportResponse | TransportFailure, name: str = "controlled"
    ) -> None:
        self.name = name
        self.responses = list(responses)
        self.requests: list[TransportRequest] = []
        self.addresses: list[str] = []
        self.timeouts: list[float] = []

    def exchange(
        self,
        target: DeliveryTarget,
        address: str,
        request: TransportRequest,
        timeout_seconds: float,
    ) -> TransportResponse | TransportFailure:
        _ = target
        self.addresses.append(address)
        self.timeouts.append(timeout_seconds)
        self.requests.append(request)
        return self.responses.pop(0)


class CapturedResponse:
    status = 200

    def read(self, limit: int) -> bytes:
        _ = limit
        return b"{}"

    def __enter__(self) -> "CapturedResponse":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = (exception_type, exception, traceback)


class CapturingOpener:
    def __init__(self) -> None:
        self.request: Request | None = None

    def open(self, request: Request, *, timeout: float) -> CapturedResponse:
        _ = timeout
        self.request = request
        return CapturedResponse()

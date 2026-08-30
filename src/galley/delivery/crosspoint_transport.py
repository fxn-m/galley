"""Internal transport seam and normal Python HTTP adapter for the CrossPoint client."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import OpenerDirector, Request

from galley.delivery.targets import DeliveryTarget
from galley.network import no_redirect_opener


@dataclass(frozen=True)
class TransportRequest:
    """One HTTP-shaped exchange passed only across the internal transport seam."""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict[str, str])
    body: Iterable[bytes] | None = None
    response_limit: int = 1_000_000


@dataclass(frozen=True)
class TransportResponse:
    """A response that reached an HTTP status."""

    status: int
    body: bytes = b""
    detail: str = ""


@dataclass(frozen=True)
class TransportFailure:
    """A transport failure, including whether a request may have begun."""

    error: BaseException
    request_began: bool = True


class Transport(Protocol):
    """Internal seam implemented by production and controlled adapters."""

    name: str

    def exchange(
        self, target: DeliveryTarget, address: str, request: TransportRequest
    ) -> TransportResponse | TransportFailure: ...


class PythonHttpTransport:
    """The normal bounded, redirect-free urllib adapter."""

    name = "python-http"

    def __init__(self, opener: OpenerDirector | None = None) -> None:
        self._opener = opener if opener is not None else no_redirect_opener(direct=True)

    def exchange(
        self, target: DeliveryTarget, address: str, exchange: TransportRequest
    ) -> TransportResponse | TransportFailure:
        request = Request(
            f"http://{_authority(address, target.port)}{exchange.path}",
            data=exchange.body,
            method=exchange.method,
            headers={"Host": target.host, **exchange.headers},
        )
        try:
            with self._opener.open(request, timeout=target.timeout_seconds) as response:
                body = cast(bytes, response.read(exchange.response_limit + 1))
                return TransportResponse(int(response.status), body)
        except HTTPError as error:
            return TransportResponse(int(error.code), detail=f"the device answered {error.code}")
        except (URLError, OSError, ValueError) as error:
            return TransportFailure(error)


def _authority(address: str, port: int) -> str:
    """Render a validated IPv4 or IPv6 address as an HTTP connection authority."""

    escaped = address.replace("%", "%25")
    bracketed = f"[{escaped}]" if ":" in escaped else escaped
    return f"{bracketed}:{port}"

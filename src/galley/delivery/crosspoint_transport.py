"""Internal transport seam and normal Python HTTP adapter for the CrossPoint client."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
import socket
import subprocess
from tempfile import TemporaryDirectory
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
    artifact: Path | None = None


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
        self,
        target: DeliveryTarget,
        address: str,
        request: TransportRequest,
        timeout_seconds: float,
    ) -> TransportResponse | TransportFailure: ...


class PythonHttpTransport:
    """The normal bounded, redirect-free urllib adapter."""

    name = "python-http"

    def __init__(self, opener: OpenerDirector | None = None) -> None:
        self._opener = opener if opener is not None else no_redirect_opener(direct=True)

    def exchange(
        self,
        target: DeliveryTarget,
        address: str,
        request: TransportRequest,
        timeout_seconds: float,
    ) -> TransportResponse | TransportFailure:
        prepared = Request(
            f"http://{_authority(address, target.port)}{request.path}",
            data=request.body,
            method=request.method,
            headers={"Host": target.host, **request.headers},
        )
        try:
            with self._opener.open(prepared, timeout=timeout_seconds) as response:
                body = cast(bytes, response.read(request.response_limit + 1))
                return TransportResponse(int(response.status), body)
        except HTTPError as error:
            return TransportResponse(int(error.code), detail=f"the device answered {error.code}")
        except (URLError, OSError, ValueError) as error:
            return TransportFailure(error, request_began=errno_code(error) != 65)


class SystemCurlTransport:
    """The absolute macOS curl adapter used only after one eligible Python failure."""

    name = "system-curl"
    executable = Path("/usr/bin/curl")

    @classmethod
    def available(cls) -> bool:
        return cls.executable.is_file()

    def exchange(
        self,
        target: DeliveryTarget,
        address: str,
        request: TransportRequest,
        timeout_seconds: float,
    ) -> TransportResponse | TransportFailure:
        if not self.available():
            return TransportFailure(FileNotFoundError(str(self.executable)), request_began=False)
        with TemporaryDirectory(prefix="galley-crosspoint-") as temporary:
            directory = Path(temporary)
            output = directory / "response"
            errors = directory / "errors"
            command = self._command(target, address, request, timeout_seconds, output)
            try:
                with errors.open("wb") as error_stream:
                    completed = subprocess.run(
                        command,
                        check=False,
                        stdout=subprocess.PIPE,
                        stderr=error_stream,
                        timeout=max(timeout_seconds, 0.001),
                    )
            except (OSError, subprocess.TimeoutExpired) as error:
                return TransportFailure(error, request_began=request.method == "POST")
            body = output.read_bytes() if output.is_file() else b""
            status = _status(completed.stdout)
            detail = errors.read_text(encoding="utf-8", errors="replace")[:1_000]
            if completed.returncode == 63:
                body = body + b"\0" * (request.response_limit + 1 - len(body))
                return TransportResponse(status or 200, body, detail)
            if completed.returncode == 0 or len(body) > request.response_limit:
                return TransportResponse(status, body, detail)
            return TransportFailure(RuntimeError(detail or f"curl exited {completed.returncode}"))

    def _command(
        self,
        target: DeliveryTarget,
        address: str,
        request: TransportRequest,
        timeout_seconds: float,
        output: Path,
    ) -> list[str]:
        timeout = f"{max(timeout_seconds, 0.001):.3f}"
        command = [
            str(self.executable),
            "--silent",
            "--show-error",
            "--noproxy",
            "*",
            "--max-time",
            timeout,
            "--connect-timeout",
            timeout,
            "--max-filesize",
            str(request.response_limit + 1),
            "--output",
            str(output),
            "--write-out",
            "%{http_code}",
            "--resolve",
            _resolve(target, address),
            "--request",
            request.method,
        ]
        if request.artifact is not None:
            command.extend(["--form", _form(request.artifact)])
        return [*command, f"http://{_logical_authority(target)}{request.path}"]


def _authority(address: str, port: int) -> str:
    """Render a validated IPv4 or IPv6 address as an HTTP connection authority."""

    escaped = address.replace("%", "%25")
    bracketed = f"[{escaped}]" if ":" in escaped else escaped
    return f"{bracketed}:{port}"


def _logical_authority(target: DeliveryTarget) -> str:
    host = target.hostname.replace("%", "%25")
    bracketed = f"[{host}]" if ":" in host else host
    return f"{bracketed}:{target.port}"


def _resolve(target: DeliveryTarget, address: str) -> str:
    resolved = f"[{address}]" if ":" in address else address
    return f"{target.hostname}:{target.port}:{resolved}"


def _form(artifact: Path) -> str:
    path = _quoted(str(artifact))
    filename = _quoted(artifact.name)
    return f'file=@"{path}";type=application/epub+zip;filename="{filename}"'


def _quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _status(value: bytes) -> int:
    try:
        return int(value[-3:])
    except ValueError:
        return 0


def errno_code(error: BaseException) -> int | None:
    reason = cast(object, error.reason) if isinstance(error, URLError) else error
    return cast(int | None, getattr(reason, "errno", None))


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

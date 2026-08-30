"""Exercise the deep CrossPoint client interface against a pinned fake device."""

from pathlib import Path
from types import TracebackType
from typing import cast
from urllib.request import OpenerDirector, Request

import pytest
import socket

from galley.delivery.crosspoint import (
    CrossPointClient,
    DeviceStatus,
    Listing,
    PythonHttpTransport,
    SystemCurlTransport,
    Transfer,
    TransportFailure,
    TransportRequest,
    TransportResponse,
)
from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget, trusted_target
from tests.crosspoint_server import Device, crosspoint


class ControlledTransport:
    """Return pinned responses while retaining what the client asked the adapter to send."""

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
    """Behave like one successful urllib response without opening a socket."""

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
    """Retain the exact urllib request the production adapter would send."""

    def __init__(self) -> None:
        self.request: Request | None = None

    def open(self, request: Request, *, timeout: float) -> CapturedResponse:
        _ = timeout
        self.request = request
        return CapturedResponse()


def test_client_exposes_only_the_three_crosspoint_domain_operations(tmp_path: Path) -> None:
    """One client reads status, lists a destination and uploads raw artifact bytes."""

    artifact = tmp_path / "A Readable Book.epub"
    payload = b"raw epub bytes"
    _ = artifact.write_bytes(payload)
    with crosspoint() as (host, device):
        target = trusted_target(host, 3.0)
        assert isinstance(target, DeliveryTarget)
        client = CrossPointClient(target)

        status = client.status()
        listing = client.listing("/")
        transfer = client.upload("/", artifact)

    assert isinstance(status.value, DeviceStatus)
    assert status.value.model == "X4"
    assert isinstance(listing.value, Listing)
    assert listing.value.entries == ()
    assert isinstance(transfer.value, Transfer)
    assert transfer.value.status == 200
    assert not isinstance(transfer.value, DeliveryRefusal)
    assert device.uploads == [(artifact.name, len(payload))]
    assert [
        exchange.stage for result in (status, listing, transfer) for exchange in result.exchanges
    ] == [
        "device-status",
        "preflight-listing",
        "upload",
    ]


def test_client_owns_http_json_and_multipart_over_one_injected_transport(tmp_path: Path) -> None:
    """A controlled adapter varies transport without leaking HTTP work into callers."""

    artifact = tmp_path / "A Readable Book.epub"
    _ = artifact.write_bytes(b"raw epub bytes")
    transport = ControlledTransport(
        TransportResponse(200, b'{"device":"X4","version":"1.4.1"}'),
        TransportResponse(200, b'[{"name":"there.epub","size":7,"isDirectory":false}]'),
        TransportResponse(200, b'{"ok":true}'),
    )
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20",), 3.0)
    client = CrossPointClient(target, transport)

    assert isinstance(client.status().value, DeviceStatus)
    assert isinstance(client.listing("/Books & Notes").value, Listing)
    assert client.upload("/Books & Notes", artifact).value == Transfer(200)
    assert [(request.method, request.path) for request in transport.requests] == [
        ("GET", "/api/status"),
        ("GET", "/api/files?path=%2FBooks+%26+Notes"),
        ("POST", "/upload?path=%2FBooks+%26+Notes"),
    ]
    upload = transport.requests[-1]
    assert upload.body is not None
    multipart = b"".join(upload.body)
    assert b'filename="A Readable Book.epub"' in multipart
    assert b"raw epub bytes" in multipart


@pytest.mark.parametrize(
    ("address", "authority"),
    [("192.168.1.20", "192.168.1.20:8080"), ("fe80::20%en0", "[fe80::20%25en0]:8080")],
)
def test_python_adapter_connects_to_ipv4_or_ipv6_but_keeps_logical_authority(
    address: str, authority: str
) -> None:
    """Connection routing and HTTP authority are separate, including a scoped IPv6 address."""

    opener = CapturingOpener()
    transport = PythonHttpTransport(cast(OpenerDirector, cast(object, opener)))
    target = DeliveryTarget("x4.local:8080", "x4.local", 8080, (address,), 3.0)

    response = transport.exchange(target, address, TransportRequest("GET", "/api/status"), 3.0)

    assert response == TransportResponse(200, b"{}")
    assert opener.request is not None
    assert opener.request.full_url == f"http://{authority}/api/status"
    assert opener.request.get_header("Host") == "x4.local:8080"


def test_safe_read_recovers_once_on_the_next_validated_address() -> None:
    """A transient read failure is visible and followed by one bounded address attempt."""

    transport = ControlledTransport(
        TransportFailure(ConnectionRefusedError("first address")),
        TransportResponse(200, b'{"device":"X4","version":"1.4.1"}'),
    )
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20", "192.168.1.21"), 3.0)

    result = CrossPointClient(target, transport).status()

    assert isinstance(result.value, DeviceStatus)
    assert transport.addresses == ["192.168.1.20", "192.168.1.21"]
    assert [exchange.outcome for exchange in result.exchanges] == ["failed", "response"]
    assert len(transport.timeouts) == 2
    assert 0 < transport.timeouts[1] <= transport.timeouts[0] <= 3.0


def test_safe_read_stops_after_one_recovery_attempt() -> None:
    """Two failures exhaust the read operation without indefinite waiting."""

    transport = ControlledTransport(
        TransportFailure(TimeoutError("first")),
        TransportFailure(TimeoutError("second")),
        TransportResponse(200, b'{"device":"X4","version":"1.4.1"}'),
    )
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20",), 3.0)

    result = CrossPointClient(target, transport).status()

    assert isinstance(result.value, DeliveryRefusal)
    assert len(result.exchanges) == 2
    assert len(transport.responses) == 1


def test_upload_changes_address_only_after_a_proven_not_started_failure(tmp_path: Path) -> None:
    """A second write is safe only when the first adapter proves no request began."""

    artifact = tmp_path / "Book.epub"
    _ = artifact.write_bytes(b"book")
    transport = ControlledTransport(
        TransportFailure(ConnectionRefusedError("pre-connect"), request_began=False),
        TransportResponse(200),
    )
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20", "192.168.1.21"), 3.0)

    result = CrossPointClient(target, transport).upload("/", artifact)

    assert result.value == Transfer(200)
    assert transport.addresses == ["192.168.1.20", "192.168.1.21"]
    assert [exchange.outcome for exchange in result.exchanges] == ["not-started", "response"]


def test_upload_never_retries_after_a_request_may_have_begun(tmp_path: Path) -> None:
    """An uncertain write stops even when another validated address exists."""

    artifact = tmp_path / "Book.epub"
    _ = artifact.write_bytes(b"book")
    transport = ControlledTransport(
        TransportFailure(TimeoutError("uncertain"), request_began=True), TransportResponse(200)
    )
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20", "192.168.1.21"), 3.0)

    result = CrossPointClient(target, transport).upload("/", artifact)

    assert isinstance(result.value, Transfer)
    assert result.value.status is None
    assert transport.addresses == ["192.168.1.20"]
    assert len(transport.responses) == 1


def test_macos_errno65_before_connection_uses_the_controlled_curl_adapter() -> None:
    """The single eligible Python failure falls back on the same address and deadline."""

    primary = ControlledTransport(
        TransportFailure(OSError(65, "No route to host"), request_began=False),
        name="python-http",
    )
    fallback = ControlledTransport(
        TransportResponse(200, b'{"device":"X4","version":"1.4.1"}'),
        name="system-curl",
    )
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20",), 3.0)

    result = CrossPointClient(target, primary, fallback, "darwin").status()

    assert isinstance(result.value, DeviceStatus)
    assert [exchange.transport for exchange in result.exchanges] == [
        "python-http",
        "system-curl",
    ]
    assert primary.addresses == fallback.addresses == ["192.168.1.20"]
    assert 0 < fallback.timeouts[0] <= primary.timeouts[0]


@pytest.mark.parametrize(
    ("error", "request_began", "platform_name"),
    [
        (OSError(65, "No route to host"), False, "linux"),
        (ConnectionRefusedError("refused"), False, "darwin"),
        (OSError(65, "No route to host"), True, "darwin"),
        (TimeoutError("timeout"), False, "darwin"),
        (socket.gaierror("did not resolve"), True, "darwin"),
    ],
)
def test_ineligible_python_failures_never_activate_curl(
    tmp_path: Path, error: OSError, request_began: bool, platform_name: str
) -> None:
    """Platform, errno and pre-connection proof are all required for fallback."""

    artifact = tmp_path / "Book.epub"
    _ = artifact.write_bytes(b"book")
    primary = ControlledTransport(
        TransportFailure(error, request_began=request_began), name="python-http"
    )
    fallback = ControlledTransport(TransportResponse(200), name="system-curl")
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20",), 3.0)

    result = CrossPointClient(target, primary, fallback, platform_name).upload("/", artifact)

    assert isinstance(result.value, Transfer)
    assert fallback.requests == []
    assert [exchange.transport for exchange in result.exchanges] == ["python-http"]


def test_http_response_and_missing_absolute_curl_do_not_activate_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A device response is final, and an absent fixed binary is not a fallback candidate."""

    artifact = tmp_path / "Book.epub"
    _ = artifact.write_bytes(b"book")
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20",), 3.0)
    fallback = ControlledTransport(TransportResponse(200), name="system-curl")
    responded = CrossPointClient(
        target,
        ControlledTransport(TransportResponse(503), name="python-http"),
        fallback,
        "darwin",
    ).upload("/", artifact)
    assert responded.value == Transfer(503)
    assert fallback.requests == []

    monkeypatch.setattr(SystemCurlTransport, "executable", tmp_path / "missing-curl")
    primary = ControlledTransport(
        TransportFailure(OSError(65, "No route to host"), request_began=False),
        name="python-http",
    )
    missing = CrossPointClient(target, primary, platform_name="darwin").upload("/", artifact)
    assert isinstance(missing.value, Transfer)
    assert [exchange.transport for exchange in missing.exchanges] == ["python-http"]


@pytest.mark.skipif(
    not SystemCurlTransport.available(), reason="the macOS absolute system curl is unavailable"
)
def test_real_system_curl_preserves_crosspoint_operations_and_logical_host(tmp_path: Path) -> None:
    """The real adapter reads, lists and streams multipart bytes through a pinned address."""

    artifact = tmp_path / "Café’s Readable Book.epub"
    payload = b"raw epub bytes"
    _ = artifact.write_bytes(payload)
    with crosspoint() as (host, device):
        port = int(host.rsplit(":", 1)[1])
        target = DeliveryTarget("x4.invalid", "x4.invalid", port, ("127.0.0.1",), 3.0)
        client = CrossPointClient(target, SystemCurlTransport(), platform_name="adapter-test")
        status = client.status()
        listing = client.listing("/")
        upload = client.upload("/", artifact)
        confirmed = client.listing("/")

    assert isinstance(status.value, DeviceStatus)
    assert isinstance(listing.value, Listing)
    assert upload.value == Transfer(200)
    assert isinstance(confirmed.value, Listing)
    assert confirmed.value.matching(artifact.name) is not None
    assert device.uploads == [(artifact.name, len(payload))]
    assert all(
        exchange.transport == "system-curl"
        for result in (status, listing, upload, confirmed)
        for exchange in result.exchanges
    )


@pytest.mark.skipif(
    not SystemCurlTransport.available(), reason="the macOS absolute system curl is unavailable"
)
def test_real_system_curl_refuses_redirects_and_caps_responses() -> None:
    """Curl neither follows a redirect nor admits a response beyond the client ceiling."""

    with crosspoint(Device(redirect_paths=("/api/status",))) as (host, _device):
        target = trusted_target(host, 3.0)
        assert isinstance(target, DeliveryTarget)
        redirected = CrossPointClient(target, SystemCurlTransport()).status()
    assert isinstance(redirected.value, DeliveryRefusal)
    assert redirected.value.fact["status"] == 302

    oversized_status = {
        "device": "X4",
        "version": "1.4.1",
        "padding": "x" * 1_000_000,
    }
    with crosspoint(Device(status=oversized_status)) as (host, _device):
        target = trusted_target(host, 3.0)
        assert isinstance(target, DeliveryTarget)
        oversized = CrossPointClient(target, SystemCurlTransport()).status()
    assert isinstance(oversized.value, DeliveryRefusal)
    assert oversized.value.boundary == "oversize-device-response"

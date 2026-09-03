"""Prove the narrow macOS fallback decision and the real absolute curl adapter."""

import socket
from pathlib import Path

import pytest

from galley.delivery.crosspoint import (
    CrossPointClient,
    DeviceStatus,
    Listing,
    SystemCurlTransport,
    Transfer,
    TransportFailure,
    TransportResponse,
)
from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget, trusted_target
from tests.delivery.crosspoint_client_fixtures import ControlledTransport
from tests.support.crosspoint_server import Device, crosspoint


def test_macos_errno65_before_connection_uses_the_controlled_curl_adapter() -> None:
    primary = ControlledTransport(
        TransportFailure(OSError(65, "No route to host"), request_began=False),
        name="python-http",
        supports_fallback=True,
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
    artifact = tmp_path / "Book.epub"
    _ = artifact.write_bytes(b"book")
    primary = ControlledTransport(
        TransportFailure(error, request_began=request_began),
        name="python-http",
        supports_fallback=True,
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
    artifact = tmp_path / "Book.epub"
    _ = artifact.write_bytes(b"book")
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20",), 3.0)
    fallback = ControlledTransport(TransportResponse(200), name="system-curl")
    responded = CrossPointClient(
        target,
        ControlledTransport(TransportResponse(503), name="python-http", supports_fallback=True),
        fallback,
        "darwin",
    ).upload("/", artifact)
    assert responded.value == Transfer(503)
    assert fallback.requests == []

    monkeypatch.setattr(SystemCurlTransport, "executable", tmp_path / "missing-curl")
    primary = ControlledTransport(
        TransportFailure(OSError(65, "No route to host"), request_began=False),
        name="python-http",
        supports_fallback=True,
    )
    missing = CrossPointClient(target, primary, platform_name="darwin").upload("/", artifact)
    assert isinstance(missing.value, Transfer)
    assert [exchange.transport for exchange in missing.exchanges] == ["python-http"]


@pytest.mark.skipif(
    not SystemCurlTransport.available(), reason="the macOS absolute system curl is unavailable"
)
def test_real_system_curl_preserves_crosspoint_operations_and_logical_host(tmp_path: Path) -> None:
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

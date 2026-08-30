"""Exercise the deep CrossPoint client interface against a pinned fake device."""

from pathlib import Path
from typing import cast
from urllib.request import OpenerDirector

import pytest

from galley.delivery.crosspoint import (
    CrossPointClient,
    DeviceStatus,
    Listing,
    PythonHttpTransport,
    Transfer,
    TransportFailure,
    TransportResponse,
)
from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget, trusted_target
from tests.crosspoint_client_fixtures import CapturingOpener, ControlledTransport
from tests.crosspoint_server import crosspoint


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

    response = CrossPointClient(target, transport).status()

    assert isinstance(response.value, DeviceStatus)
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


def test_upload_serialises_a_hostile_filename_without_injecting_multipart_headers(
    tmp_path: Path,
) -> None:
    """Explicit paths remain safe even though Ready naming normally removes these characters."""

    artifact = tmp_path / 'Proof"\r\nX-Galley-Injected: yes\\book.epub'
    _ = artifact.write_bytes(b"book")
    transport = ControlledTransport(TransportResponse(200))
    target = DeliveryTarget("x4.local", "x4.local", 80, ("192.168.1.20",), 3.0)

    result = CrossPointClient(target, transport).upload("/", artifact)

    assert result.value == Transfer(200)
    body = transport.requests[0].body
    assert body is not None
    header = b"".join(body).partition(b"\r\n\r\n")[0]
    assert b"\r\nX-Galley-Injected:" not in header
    assert b'filename="Proof%22%0D%0AX-Galley-Injected: yes%5Cbook.epub"' in header

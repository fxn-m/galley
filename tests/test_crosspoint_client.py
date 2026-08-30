"""Exercise the deep CrossPoint client interface against a pinned fake device."""

from pathlib import Path

from galley.delivery.crosspoint import (
    CrossPointClient,
    DeviceStatus,
    Listing,
    Transfer,
    TransportRequest,
    TransportResponse,
)
from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget, trusted_target
from tests.crosspoint_server import crosspoint


class ControlledTransport:
    """Return pinned responses while retaining what the client asked the adapter to send."""

    name = "controlled"

    def __init__(self, *responses: TransportResponse) -> None:
        self.responses = list(responses)
        self.requests: list[TransportRequest] = []

    def exchange(self, target: DeliveryTarget, request: TransportRequest) -> TransportResponse:
        _ = target
        self.requests.append(request)
        return self.responses.pop(0)


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
    assert [exchange.stage for result in (status, listing, transfer) for exchange in result.exchanges] == [
        "device-status",
        "destination-listing",
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

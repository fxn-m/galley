"""Prove bounded recovery through the installed CLI and a pinned fake CrossPoint."""

import os
import subprocess
from pathlib import Path

from tests.crosspoint_server import Device, crosspoint
from tests.delivery_fixtures import REFUSED, published
from tests.public_cli import cli_command, run_command
from tests.workspace_fixtures import command_document, entries, field

COMPLETED = 0
ENTRY_POINT = cli_command()


def _plan(
    artifact: Path, environment: dict[str, str], host: str
) -> subprocess.CompletedProcess[str]:
    return run_command(
        ENTRY_POINT,
        "deliver",
        str(artifact),
        "--plan",
        "--json",
        "--host",
        host,
        environment=environment,
    )


def test_exhausted_read_recovery_refuses_after_two_visible_attempts(tmp_path: Path) -> None:
    """A fake device that drops both allowed listings cannot extend the operation indefinitely."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(listing_disconnects=2)) as (host, device):
        result = _plan(artifact, environment, host)
        assert device.listing_requests == 2
        assert device.upload_requests == 0

    assert result.returncode == REFUSED
    document = command_document(result)
    assert field(document, "refusal")["boundary"] == "device-unavailable"
    assert [(item["stage"], item["outcome"]) for item in entries(document, "exchanges")] == [
        ("device-status", "response"),
        ("preflight-listing", "failed"),
        ("preflight-listing", "failed"),
    ]


def test_recovery_moves_deterministically_to_the_second_validated_address(
    tmp_path: Path,
) -> None:
    """The first refused loopback address remains evidence before the fake device answers."""

    _workspace, artifact, environment = published(tmp_path)
    hooks = tmp_path / "resolver-hook"
    hooks.mkdir()
    _ = (hooks / "sitecustomize.py").write_text(
        """import socket

_original = socket.getaddrinfo

def _two(host, port, *args, **kwargs):
    if host != "x4-two.test":
        return _original(host, port, *args, **kwargs)
    return [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port)),
        (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("::1", port, 0, 0)),
    ]

socket.getaddrinfo = _two
""",
        encoding="utf-8",
    )
    with crosspoint(address="::1") as (host, device):
        port = host.rsplit(":", 1)[1]
        result = _plan(
            artifact,
            {
                **environment,
                "PYTHONPATH": os.pathsep.join([str(hooks), os.environ.get("PYTHONPATH", "")]),
            },
            f"x4-two.test:{port}",
        )
        assert device.listing_requests == 1

    assert result.returncode == COMPLETED, result.stderr
    document = command_document(result)
    assert field(document, "device")["addresses"] == ["127.0.0.1", "::1"]
    assert [
        (item["stage"], item["address"], item["outcome"]) for item in entries(document, "exchanges")
    ] == [
        ("device-status", "127.0.0.1", "failed"),
        ("device-status", "::1", "response"),
        ("preflight-listing", "127.0.0.1", "failed"),
        ("preflight-listing", "::1", "response"),
    ]

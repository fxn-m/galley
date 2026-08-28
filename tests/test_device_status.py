"""Probe a pinned CrossPoint device through the installed public CLI."""

from pathlib import Path

from tests.crosspoint_server import Device, crosspoint
from tests.public_cli import run_public_cli
from tests.workspace_fixtures import (
    command_document,
    field,
    tree,
    valid_workspace,
    workspace_environment,
    write_configuration,
)

COMPLETED = 0
INVOCATION_ERROR = 2
REFUSED = 3


def status(environment: dict[str, str], *arguments: str) -> list[dict[str, object]]:
    """Run `device status` through both entry points and read the document each emitted."""

    results = run_public_cli("device", "status", "--json", *arguments, environment=environment)
    return [command_document(result) for result in results]


def workspace_for(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace)
    return workspace, workspace_environment(workspace, tmp_path / "home")


def test_a_pinned_device_reports_its_model_firmware_and_mode(tmp_path: Path) -> None:
    """The whole status response is retained beside the fields Galley identifies."""

    _, environment = workspace_for(tmp_path)
    with crosspoint() as (host, _device):
        documents = status(environment, "--host", host)
    for document in documents:
        assert document["outcome"] == "completed"
        device = field(document, "device")
        assert device["model"] == "X4"
        assert device["firmware"] == "1.4.1"
        assert device["mode"] == "File Transfer"
        assert field(device, "status")["storage"] == {"free": 1234567}
        assert field(document, "host") == {"value": host, "source": "option"}
        assert device["addresses"] == ["127.0.0.1"]


def test_the_human_rendering_states_the_same_device(tmp_path: Path) -> None:
    """Concise output is a second rendering of the document, never a second account."""

    _, environment = workspace_for(tmp_path)
    with crosspoint() as (host, _device):
        results = run_public_cli("device", "status", "--host", host, environment=environment)
    for result in results:
        assert result.returncode == COMPLETED
        assert "device status: completed" in result.stdout
        assert "Device: X4 firmware 1.4.1 (File Transfer)" in result.stdout
        assert f"Target: {host} -> 127.0.0.1" in result.stdout


def test_the_configured_host_is_used_when_no_option_overrides_it(tmp_path: Path) -> None:
    """Workspace Configuration owns the device connection; the option is per-invocation."""

    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    with crosspoint() as (host, _device):
        _ = write_configuration(
            workspace,
            'version = 1\n\n[[inbox]]\nname = "galley"\npath = "inbox"\nrecursive = false\n\n'
            f'[x4-crosspoint]\nhost = "{host}"\n',
        )
        (workspace / "inbox").mkdir(parents=True, exist_ok=True)
        documents = status(environment)
    for document in documents:
        assert field(document, "host") == {"value": host, "source": "configured"}
        assert field(document, "configuration")["version"] == 1


def test_a_device_that_is_not_an_x4_refuses_but_keeps_what_it_said(tmp_path: Path) -> None:
    """Wrong-model refusal is a Delivery fact and never discards the status evidence."""

    _, environment = workspace_for(tmp_path)
    device = Device(status={"device": "Kobo", "version": "9.9", "mode": "USB"})
    with crosspoint(device) as (host, _device):
        results = run_public_cli(
            "device", "status", "--json", "--host", host, environment=environment
        )
    for result in results:
        assert result.returncode == REFUSED
        document = command_document(result)
        assert field(document, "refusal")["boundary"] == "unexpected-device-model"
        assert field(document, "device")["model"] == "Kobo"
        assert field(document, "device")["firmware"] == "9.9"


def test_a_status_without_a_model_or_firmware_is_unusable(tmp_path: Path) -> None:
    """A device that answers without identifying itself has not been identified."""

    _, environment = workspace_for(tmp_path)
    with crosspoint(Device(status={"mode": "File Transfer"})) as (host, _device):
        documents = status(environment, "--host", host)
    for document in documents:
        assert field(document, "refusal")["boundary"] == "unusable-device-status"


def test_a_public_target_refuses_before_any_request(tmp_path: Path) -> None:
    """CrossPoint's surface is unauthenticated, so Galley never writes off the local network."""

    _, environment = workspace_for(tmp_path)
    for public in ("8.8.8.8", "[2001:4860:4860::8888]:80"):
        for document in status(environment, "--host", public):
            refusal = field(document, "refusal")
            assert refusal["boundary"] == "untrusted-delivery-target"
            assert field(refusal, "fact")["public_addresses"]
            assert document["device"] is None


def test_a_private_or_link_local_literal_is_an_allowed_target(tmp_path: Path) -> None:
    """The allowed classes are loopback, private and link-local, checked before connecting."""

    _, environment = workspace_for(tmp_path)
    for local in ("192.168.7.7:8080", "169.254.3.4:8080", "127.0.0.1:9"):
        for document in status(environment, "--host", local, "--timeout", "0.2"):
            assert field(document, "refusal")["boundary"] == "device-unavailable"
            assert field(document, "device")["addresses"]
            assert field(document, "device")["model"] is None


def test_a_malformed_host_refuses_before_resolution(tmp_path: Path) -> None:
    """A host is an authority and nothing else: no scheme, no path, no credentials."""

    _, environment = workspace_for(tmp_path)
    for malformed in ("http://127.0.0.1", "127.0.0.1/books", "user@127.0.0.1"):
        for document in status(environment, "--host", malformed):
            assert field(document, "refusal")["boundary"] == "invalid-delivery-host"


def test_a_redirect_is_never_followed(tmp_path: Path) -> None:
    """Redirects are disabled so an allowed target cannot hand the exchange to another host."""

    _, environment = workspace_for(tmp_path)
    with crosspoint(Device(redirect_paths=("/api/status",))) as (host, _device):
        documents = status(environment, "--host", host)
    for document in documents:
        refusal = field(document, "refusal")
        assert refusal["boundary"] == "device-unavailable"
        assert field(refusal, "fact")["status"] == 302


def test_a_slow_device_stops_at_the_configured_timeout(tmp_path: Path) -> None:
    """Timeouts are configurable per invocation and never infinite."""

    _, environment = workspace_for(tmp_path)
    with crosspoint(Device(status_delay_seconds=2.0)) as (host, _device):
        documents = status(environment, "--host", host, "--timeout", "0.25")
    for document in documents:
        refusal = field(document, "refusal")
        assert refusal["boundary"] == "device-unavailable"
        assert "timeout" in str(refusal["summary"])
        assert field(document, "device")["timeout_seconds"] == 0.25


def test_a_non_positive_timeout_is_an_invocation_error(tmp_path: Path) -> None:
    """A timeout that could never expire is rejected before a workflow exists."""

    _, environment = workspace_for(tmp_path)
    for stated in ("0", "-1"):
        for result in run_public_cli(
            "device",
            "status",
            "--host",
            "127.0.0.1:9",
            "--timeout",
            stated,
            environment=environment,
        ):
            assert result.returncode == INVOCATION_ERROR


def test_probing_writes_nothing_into_the_workspace(tmp_path: Path) -> None:
    """A probe is neither a plan nor an attempt, so it leaves no record of its own."""

    workspace, environment = workspace_for(tmp_path)
    before = tree(workspace)
    with crosspoint() as (host, device):
        _ = status(environment, "--host", host)
        assert device.listing_requests == 0
        assert device.upload_requests == 0
    assert tree(workspace) == before

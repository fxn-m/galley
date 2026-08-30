"""Produce read-only Delivery Plans against a pinned loopback CrossPoint."""

import json
import os
from pathlib import Path

from tests.crosspoint_server import Device, crosspoint
from tests.delivery_fixtures import REFUSED, deliver, plan, published, records
from tests.public_cli import run_public_cli
from tests.public_cli import public_cli_commands, run_command
from tests.workspace_fixtures import command_document, entries, field

COMPLETED = 0


def test_a_new_book_plans_one_upload(tmp_path: Path) -> None:
    """A destination without the artifact plans a new upload and sends no document bytes."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, device):
        results = plan(artifact, environment, host)
        assert device.upload_requests == 0
        assert device.listing_requests == len(results)
    for result in results:
        assert result.returncode == COMPLETED
        document = command_document(result)
        assert document["outcome"] == "planned"
        assert document["mode"] == "plan"
        assert field(document, "action")["planned"] == "upload-new"
        assert field(document, "action")["upload_began"] is False
        assert field(document, "destination")["remote_path"] == f"/{artifact.name}"
        assert field(field(document, "destination"), "preflight")["matching"] is None
        assert field(document, "galley")["document_schema"] == "galley/delivery-record/2"
        exchanges = entries(document, "exchanges")
        assert [exchange["stage"] for exchange in exchanges] == [
            "device-status",
            "preflight-listing",
        ]
        for exchange in exchanges:
            assert exchange == {
                "stage": exchange["stage"],
                "address": "127.0.0.1",
                "transport": "python-http",
                "request_began": True,
                "status": 200,
                "outcome": "response",
                "detail": "",
            }
    assert len(records(workspace)) == len(results)


def test_authorised_logical_host_is_never_resolved_again(tmp_path: Path) -> None:
    """Each installed CLI resolves once, then connects every exchange to the approved address."""

    _workspace, artifact, environment = published(tmp_path)
    hooks = tmp_path / "resolver-hook"
    hooks.mkdir()
    _ = (hooks / "sitecustomize.py").write_text(
        """import os
import socket
from pathlib import Path

_original = socket.getaddrinfo

def _once(host, port, *args, **kwargs):
    if host != "x4-once.test":
        return _original(host, port, *args, **kwargs)
    marker = Path(os.environ["GALLEY_TEST_RESOLUTION_MARKER"])
    if marker.exists():
        raise socket.gaierror("logical host was resolved twice")
    marker.touch()
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port))]

socket.getaddrinfo = _once
""",
        encoding="utf-8",
    )
    with crosspoint() as (host, _device):
        port = host.rsplit(":", 1)[1]
        for index, command in enumerate(public_cli_commands()):
            marker = tmp_path / f"resolved-{index}"
            result = run_command(
                command,
                "deliver",
                str(artifact),
                "--plan",
                "--json",
                "--host",
                f"x4-once.test:{port}",
                environment={
                    **environment,
                    "GALLEY_TEST_RESOLUTION_MARKER": str(marker),
                    "PYTHONPATH": os.pathsep.join(
                        [str(hooks), os.environ.get("PYTHONPATH", "")]
                    ),
                },
            )
            assert result.returncode == COMPLETED, result.stderr
            assert marker.is_file()


def test_the_plan_references_the_artifact_and_its_preparation_evidence(tmp_path: Path) -> None:
    """A record references preparation evidence by path and hash, copying none of it."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        results = plan(artifact, environment, host)
    document = command_document(results[0])
    facts = field(document, "artifact")
    assert facts["path"] == str(artifact)
    assert facts["byte_size"] == artifact.stat().st_size
    report = Path(str(facts["report_path"]))
    assert report.is_file()
    assert report.parent == workspace / "ready" / "evidence" / report.parent.name
    assert field(facts, "profile")["id"] == "x4-crosspoint"
    assert field(document, "device")["model"] == "X4"


def test_the_record_is_persisted_before_it_is_rendered(tmp_path: Path) -> None:
    """Whatever a reader sees on stdout is already on disk under the record's own id."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        results = plan(artifact, environment, host)
    document = command_document(results[0])
    stored = workspace / "delivery" / f"{document['record_id']}.json"
    assert stored.is_file()
    assert json.loads(stored.read_text(encoding="utf-8")) == document


def test_an_identical_book_already_there_plans_no_upload(tmp_path: Path) -> None:
    """Same filename and same byte size is the artifact already being present."""

    _workspace, artifact, environment = published(tmp_path)
    device = Device(files={artifact.name: artifact.stat().st_size})
    with crosspoint(device) as (host, pinned):
        results = plan(artifact, environment, host)
        assert pinned.upload_requests == 0
    for result in results:
        document = command_document(result)
        assert document["outcome"] == "planned"
        assert field(document, "action")["planned"] == "already-delivered"


def test_a_different_book_of_the_same_name_refuses_the_plan(tmp_path: Path) -> None:
    """Two different books cannot both be one filename, and Galley does not choose."""

    _workspace, artifact, environment = published(tmp_path)
    device = Device(files={artifact.name: artifact.stat().st_size + 17})
    with crosspoint(device) as (host, pinned):
        results = plan(artifact, environment, host)
        assert pinned.upload_requests == 0
    for result in results:
        assert result.returncode == REFUSED
        document = command_document(result)
        assert document["outcome"] == "refused"
        refusal = field(document, "refusal")
        assert refusal["boundary"] == "destination-collision"
        assert field(refusal, "fact")["local_byte_size"] == artifact.stat().st_size


def test_explicit_overwrite_plans_a_replacement(tmp_path: Path) -> None:
    """Overwrite is the user's permission to replace exactly that colliding filename."""

    _workspace, artifact, environment = published(tmp_path)
    device = Device(files={artifact.name: artifact.stat().st_size + 17})
    with crosspoint(device) as (host, pinned):
        results = plan(artifact, environment, host, "--overwrite")
        assert pinned.upload_requests == 0
    for result in results:
        assert result.returncode == COMPLETED
        document = command_document(result)
        assert document["overwrite_requested"] is True
        assert field(document, "action")["planned"] == "overwrite"


def test_the_configured_destination_reaches_the_listing(tmp_path: Path) -> None:
    """The destination is sent as written, and the remote path is built from it."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        results = plan(artifact, environment, host, "--destination", "/Books")
    for result in results:
        document = command_document(result)
        destination = field(document, "destination")
        assert destination["path"] == "/Books"
        assert destination["remote_path"] == f"/Books/{artifact.name}"
        assert field(document, "connection")["destination"] == {
            "value": "/Books",
            "source": "option",
        }


def test_an_unnormalised_destination_refuses(tmp_path: Path) -> None:
    """A destination that would have to be rewritten is refused rather than rewritten."""

    _workspace, artifact, environment = published(tmp_path)
    for stated in ("Books", "/Books/", "/Books/../Secrets"):
        for result in deliver(artifact, environment, "--plan", "--destination", stated):
            assert result.returncode == REFUSED
            refusal = field(command_document(result), "refusal")
            assert refusal["boundary"] == "invalid-delivery-destination"


def test_the_human_rendering_states_the_same_plan(tmp_path: Path) -> None:
    """Concise output is rendered from the persisted record and adds nothing to it."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        results = run_public_cli(
            "deliver", str(artifact), "--plan", "--host", host, environment=environment
        )
    for result in results:
        assert result.returncode == COMPLETED
        assert "deliver: planned" in result.stdout
        assert f"Artifact: {artifact}" in result.stdout
        assert "Device: X4 firmware 1.4.1" in result.stdout
        assert "Action: upload-new (no upload)" in result.stdout

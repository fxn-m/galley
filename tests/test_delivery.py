"""Deliver one Ready Artifact to a pinned loopback CrossPoint and confirm it arrived."""

import json
import os
import subprocess
from pathlib import Path

from tests.crosspoint_server import Device, crosspoint
from tests.delivery_fixtures import UNCONFIRMED, deliver, published, records
from tests.public_cli import public_cli_commands, run_command, run_public_cli
from tests.workspace_fixtures import command_document, field, tree

COMPLETED = 0


def test_a_new_book_is_uploaded_once_and_confirmed(tmp_path: Path) -> None:
    """Delivery is one multipart upload followed by the listing that proves it landed."""

    workspace, artifact, environment = published(tmp_path)
    size = artifact.stat().st_size
    with crosspoint() as (host, device):
        results = run_public_cli(
            "deliver", str(artifact), "--json", "--host", host, environment=environment
        )
        assert device.uploads[0] == (artifact.name, size)
        assert device.files[artifact.name] == size
    first = command_document(results[0])
    assert results[0].returncode == COMPLETED
    assert first["outcome"] == "delivered"
    assert first["mode"] == "deliver"
    action = field(first, "action")
    assert action["planned"] == "upload-new"
    assert action["upload_began"] is True
    assert action["transport_status"] == 200
    assert field(action, "confirmation") == {"name": artifact.name, "byte_size": size}
    assert field(field(first, "destination"), "postflight")["matching"] is not None
    assert len(records(workspace)) == len(results)


def test_the_upload_is_multipart_and_asks_for_no_optimization(tmp_path: Path) -> None:
    """Galley uploads the raw artifact; CrossPoint's Optimize action is never invoked."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, device):
        _ = run_public_cli(
            "deliver", str(artifact), "--json", "--host", host, environment=environment
        )
        # The second entry point finds the book already there and sends nothing; one upload is the
        # whole of what Delivery writes.
        assert device.upload_requests == 1
        for content_type in device.upload_content_types:
            assert content_type.startswith("multipart/form-data; boundary=galley-")
        for query in device.upload_queries:
            assert query == "path=%2F"
            assert "optimi" not in query.lower()


def test_the_exact_readable_ready_name_reaches_crosspoint(tmp_path: Path) -> None:
    """Both entry points serialize and confirm the published Unicode filename unchanged."""

    readable = "Café’s, 2026 (第2版) [A&B] - draft_v1.2.md"
    _workspace, artifact, environment = published(tmp_path, readable)
    size = artifact.stat().st_size
    assert artifact.name == f"{Path(readable).stem}.epub"
    for command in public_cli_commands():
        with crosspoint() as (host, device):
            result = run_command(
                command,
                "deliver",
                str(artifact),
                "--json",
                "--host",
                host,
                environment=environment,
            )
            assert result.returncode == COMPLETED
            assert device.uploads == [(artifact.name, size)]
            assert device.files == {artifact.name: size}


def test_the_record_references_everything_the_delivery_rested_on(tmp_path: Path) -> None:
    """One record carries artifact, Report, profile, host, destination, device and times."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        results = deliver(artifact, environment, "--host", host)
    document = command_document(results[0])
    facts = field(document, "artifact")
    assert Path(str(facts["report_path"])).is_file()
    assert len(str(facts["report_sha256"])) == 64
    assert field(facts, "profile")["id"] == "x4-crosspoint"
    assert field(document, "connection")["host"] == {"value": host, "source": "option"}
    assert field(document, "destination")["path"] == "/"
    assert field(document, "device")["firmware"] == "1.4.1"
    galley = field(document, "galley")
    assert galley["started_at"] and galley["finished_at"]
    stored = workspace / "delivery" / f"{document['record_id']}.json"
    assert json.loads(stored.read_text(encoding="utf-8")) == document


def test_the_artifact_and_its_evidence_are_untouched_by_delivery(tmp_path: Path) -> None:
    """Delivery reads the Ready Artifact and never removes, rewrites or invalidates it."""

    workspace, artifact, environment = published(tmp_path)
    before = tree(workspace / "ready")
    with crosspoint() as (host, _device):
        results = deliver(artifact, environment, "--host", host)
    assert [command_document(result)["outcome"] for result in results] == [
        "delivered",
        "already-delivered",
    ]
    assert tree(workspace / "ready") == before


def test_http_success_without_confirmation_is_not_delivery(tmp_path: Path) -> None:
    """The device's own answer is never evidence a book arrived; the listing is."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(visibility_delay=99)) as (host, device):
        results = deliver(artifact, environment, "--host", host)
        assert device.upload_requests == len(results)
    for result in results:
        assert result.returncode == UNCONFIRMED
        document = command_document(result)
        assert document["outcome"] == "unconfirmed"
        assert field(document, "action")["transport_status"] == 200
        assert field(document, "refusal")["boundary"] == "unconfirmed-delivery"
    assert tree(workspace / "ready")


def test_a_definite_pre_write_failure_sends_no_upload(tmp_path: Path) -> None:
    """Everything that can refuse before the write does, and no upload request is made."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(status={"device": "Kobo", "version": "1.0"})) as (host, device):
        results = deliver(artifact, environment, "--host", host)
        assert device.upload_requests == 0
    for result in results:
        document = command_document(result)
        assert document["outcome"] == "refused"
        assert field(document, "action")["upload_began"] is False
    assert {str(record["outcome"]) for record in records(workspace)} == {"refused"}


def test_the_human_rendering_derives_from_the_same_record(tmp_path: Path) -> None:
    """Concise output and JSON are two renderings of one validated Delivery Record."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        result = subprocess.run(
            [*public_cli_commands()[0], "deliver", str(artifact), "--host", host],
            check=False,
            capture_output=True,
            text=True,
            input="",
            env={**os.environ, **environment},
        )
    assert result.returncode == COMPLETED
    stored = records(workspace)[0]
    assert "deliver: delivered" in result.stdout
    assert f"Record: {stored['record_id']} (deliver)" in result.stdout
    assert f"Artifact: {artifact}" in result.stdout
    assert "Action: upload-new (upload began; HTTP 200)" in result.stdout
    assert f"After: 1 entries; {artifact.name} at {artifact.stat().st_size} bytes" in result.stdout


def test_delivery_never_prompts_in_the_terminal(tmp_path: Path) -> None:
    """Invoking the command is the authorization to write; there is nothing to answer."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        result = subprocess.run(
            [*public_cli_commands()[0], "deliver", str(artifact), "--json", "--host", host],
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env={**os.environ, **environment},
        )
    assert result.returncode == COMPLETED
    assert command_document(result)["outcome"] == "delivered"

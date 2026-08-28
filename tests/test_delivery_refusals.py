"""Refuse everything that is not a verified Ready Artifact bound for a trusted X4."""

import shutil
from pathlib import Path

from tests.crosspoint_server import Device, crosspoint
from tests.delivery_fixtures import REFUSED, deliver, plan, published, records
from tests.workspace_fixtures import command_document, field, tree


def boundaries(workspace: Path) -> set[str]:
    """Read the boundary every invocation refused at, from its own persisted record."""

    stated = {str(field(record, "refusal")["boundary"]) for record in records(workspace)}
    assert {record["outcome"] for record in records(workspace)} == {"refused"}
    return stated


def test_a_book_outside_ready_refuses_before_any_request(tmp_path: Path) -> None:
    """Delivery accepts a Ready Artifact of the resolved Workspace and nothing else."""

    workspace, artifact, environment = published(tmp_path)
    elsewhere = tmp_path / "elsewhere.epub"
    _ = shutil.copy(artifact, elsewhere)
    with crosspoint() as (host, device):
        results = plan(elsewhere, environment, host)
        assert device.listing_requests == 0
    for result in results:
        assert result.returncode == REFUSED
    assert boundaries(workspace) == {"artifact-outside-ready"}


def test_a_symlink_out_of_ready_cannot_smuggle_a_book_in(tmp_path: Path) -> None:
    """The path is resolved first, so "directly inside ready" also means "cannot escape it"."""

    workspace, artifact, environment = published(tmp_path)
    outside = tmp_path / "outside.epub"
    _ = shutil.copy(artifact, outside)
    link = workspace / "ready" / "smuggled.epub"
    link.symlink_to(outside)
    with crosspoint() as (host, _device):
        results = plan(link, environment, host)
    for result in results:
        assert result.returncode == REFUSED
    assert boundaries(workspace) == {"artifact-outside-ready"}


def test_a_missing_or_non_epub_path_refuses(tmp_path: Path) -> None:
    """Exactly one regular EPUB is deliverable; a directory or a stray file is not."""

    workspace, _artifact, environment = published(tmp_path)
    stray = workspace / "ready" / "notes.txt"
    _ = stray.write_text("not a book", encoding="utf-8")
    for chosen in (workspace / "ready" / "absent.epub", stray, workspace / "ready"):
        for result in deliver(chosen, environment, "--plan", "--host", "127.0.0.1:9"):
            assert result.returncode == REFUSED
            refusal = field(command_document(result), "refusal")
            assert refusal["boundary"] == "unusable-ready-artifact"


def test_a_book_with_no_preparation_evidence_refuses(tmp_path: Path) -> None:
    """A book that no immutable Report published is not a Ready Artifact of this Workspace."""

    workspace, artifact, environment = published(tmp_path)
    unpublished = workspace / "ready" / "unpublished.epub"
    _ = shutil.copy(artifact, unpublished)
    with crosspoint() as (host, device):
        results = plan(unpublished, environment, host)
        assert device.listing_requests == 0
    for result in results:
        assert result.returncode == REFUSED
    assert boundaries(workspace) == {"missing-preparation-evidence"}


def test_changed_artifact_bytes_refuse_before_the_device_is_touched(tmp_path: Path) -> None:
    """A book that is no longer what its Report recorded is not the book that was approved."""

    workspace, artifact, environment = published(tmp_path)
    with artifact.open("ab") as book:
        _ = book.write(b"tampered")
    with crosspoint() as (host, device):
        results = plan(artifact, environment, host)
        assert device.listing_requests == 0
    for result in results:
        assert result.returncode == REFUSED
        fact = field(field(command_document(result), "refusal"), "fact")
        assert fact["observed_sha256"] != fact["recorded_sha256"]
    assert boundaries(workspace) == {"artifact-mismatched"}


def test_an_unreachable_device_never_invalidates_the_ready_artifact(tmp_path: Path) -> None:
    """Device availability has no authority over what preparation already established."""

    workspace, artifact, environment = published(tmp_path)
    before = tree(workspace / "ready")
    results = plan(artifact, environment, "127.0.0.1:9", "--timeout", "0.25")
    for result in results:
        assert result.returncode == REFUSED
    assert boundaries(workspace) == {"device-unavailable"}
    assert tree(workspace / "ready") == before


def test_a_wrong_model_device_never_invalidates_the_ready_artifact(tmp_path: Path) -> None:
    """An X4 is required for Delivery alone; the book stays exactly as it was published."""

    workspace, artifact, environment = published(tmp_path)
    before = tree(workspace / "ready")
    with crosspoint(Device(status={"device": "X3", "version": "1.0.0"})) as (host, device):
        results = plan(artifact, environment, host)
        assert device.listing_requests == 0
    for result in results:
        assert result.returncode == REFUSED
        assert field(command_document(result), "device")["model"] == "X3"
    assert boundaries(workspace) == {"unexpected-device-model"}
    assert tree(workspace / "ready") == before


def test_an_unreadable_listing_refuses_rather_than_guessing(tmp_path: Path) -> None:
    """A destination Galley cannot read is a destination Galley cannot plan against."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(malformed_paths=("/api/files",))) as (host, _device):
        results = plan(artifact, environment, host)
    for result in results:
        assert result.returncode == REFUSED
    assert boundaries(workspace) == {"unusable-device-response"}


def test_a_redirected_listing_is_never_followed(tmp_path: Path) -> None:
    """Redirects are off for every request, not only the first one of an invocation."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(redirect_paths=("/api/files",))) as (host, _device):
        results = plan(artifact, environment, host)
    for result in results:
        assert result.returncode == REFUSED
    assert boundaries(workspace) == {"device-unavailable"}


def test_a_public_target_refuses_with_a_record_and_no_traffic(tmp_path: Path) -> None:
    """Even a refused plan leaves an immutable record saying what was asked and refused."""

    workspace, artifact, environment = published(tmp_path)
    results = plan(artifact, environment, "8.8.8.8")
    for result in results:
        assert result.returncode == REFUSED
    assert boundaries(workspace) == {"untrusted-delivery-target"}
    assert len(records(workspace)) == len(results)


def test_a_workspace_that_cannot_hold_a_record_refuses_before_the_device(tmp_path: Path) -> None:
    """A plan or attempt that could not be recorded refuses while refusing is still true."""

    workspace, artifact, environment = published(tmp_path)
    occupied = workspace / "delivery"
    _ = occupied.write_text("not a directory", encoding="utf-8")
    with crosspoint() as (host, device):
        results = plan(artifact, environment, host)
        assert device.listing_requests == 0
    for result in results:
        assert result.returncode == REFUSED
        document = command_document(result)
        assert field(document, "refusal")["boundary"] == "delivery-record-unwritable"
        assert document["device"] is None
    assert records(workspace) == []

"""Make repeated, colliding and uncertain Deliveries trustworthy through the installed CLI."""

from pathlib import Path

from tests.support.crosspoint_server import Device, crosspoint
from tests.support.delivery_fixtures import REFUSED, plan, published, records
from tests.support.public_cli import cli_command, run_command
from tests.support.workspace_fixtures import command_document, entries, field, tree

COMPLETED = 0
UNCONFIRMED = 5
ENTRY_POINT = cli_command()


def once(artifact: Path, environment: dict[str, str], *arguments: str) -> dict[str, object]:
    """Deliver through one entry point, so a test can count attempts exactly."""

    result = run_command(
        ENTRY_POINT,
        "deliver",
        str(artifact),
        "--json",
        *arguments,
        environment=environment,
    )
    return {**command_document(result), "exit_code": result.returncode}


def test_an_identical_book_reports_already_delivered_and_sends_nothing(tmp_path: Path) -> None:
    """Finding the exact artifact already present is the same successful fact as sending it."""

    _workspace, artifact, environment = published(tmp_path)
    size = artifact.stat().st_size
    with crosspoint(Device(files={artifact.name: size})) as (host, device):
        document = once(artifact, environment, "--host", host)
        assert device.upload_requests == 0
    assert document["exit_code"] == COMPLETED
    assert document["outcome"] == "already-delivered"
    assert field(document, "action")["planned"] == "already-delivered"
    assert field(document, "action")["upload_began"] is False


def test_a_same_name_different_size_collision_refuses_without_overwrite(tmp_path: Path) -> None:
    """Two different books cannot both be one filename, and Delivery does not choose."""

    _workspace, artifact, environment = published(tmp_path)
    device = Device(files={artifact.name: artifact.stat().st_size + 5})
    with crosspoint(device) as (host, pinned):
        document = once(artifact, environment, "--host", host)
        assert pinned.upload_requests == 0
    assert document["exit_code"] == REFUSED
    assert field(document, "refusal")["boundary"] == "destination-collision"


def test_overwrite_replaces_only_the_colliding_name(tmp_path: Path) -> None:
    """Overwrite is permission for one filename, never for the rest of the destination."""

    _workspace, artifact, environment = published(tmp_path)
    size = artifact.stat().st_size
    device = Device(files={artifact.name: size + 5, "keepsake.epub": 4242})
    with crosspoint(device) as (host, pinned):
        document = once(artifact, environment, "--host", host, "--overwrite")
        assert pinned.upload_requests == 1
        assert pinned.files == {artifact.name: size, "keepsake.epub": 4242}
    assert document["exit_code"] == COMPLETED
    assert document["outcome"] == "delivered"
    assert field(document, "action")["planned"] == "overwrite"
    assert field(field(document, "action"), "confirmation")["byte_size"] == size


def test_a_timeout_after_the_upload_began_is_unconfirmed(tmp_path: Path) -> None:
    """A device that stops answering mid-exchange has not said whether it kept the bytes."""

    workspace, artifact, environment = published(tmp_path)
    device = Device(upload_delay_seconds=2.0, visibility_delay=99)
    with crosspoint(device) as (host, pinned):
        before = tree(workspace / "ready")
        document = once(artifact, environment, "--host", host, "--timeout", "0.4")
        assert pinned.upload_requests == 1
    assert document["exit_code"] == UNCONFIRMED
    assert document["outcome"] == "unconfirmed"
    assert field(document, "action")["upload_began"] is True
    assert field(document, "action")["transport_status"] is None
    assert field(document, "action")["confirmation"] is None
    exchanges = entries(document, "exchanges")
    assert [(exchange["stage"], exchange["outcome"]) for exchange in exchanges] == [
        ("device-status", "response"),
        ("preflight-listing", "response"),
        ("upload", "failed"),
        ("postflight-confirmation", "response"),
        ("postflight-confirmation", "response"),
    ]
    assert exchanges[2]["request_began"] is True
    assert tree(workspace / "ready") == before


def test_a_malformed_post_write_listing_is_unconfirmed(tmp_path: Path) -> None:
    """A confirmation that cannot be read is not a confirmation, and never a failure either."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(listing_malformed_after_upload=True)) as (host, pinned):
        document = once(artifact, environment, "--host", host)
        assert pinned.upload_requests == 1
    assert document["exit_code"] == UNCONFIRMED
    refusal = field(document, "refusal")
    assert refusal["boundary"] == "unconfirmed-delivery"
    assert field(document, "destination")["postflight"] is None


def test_postflight_confirmation_recovers_once_before_becoming_unconfirmed(
    tmp_path: Path,
) -> None:
    """One temporarily invisible upload is confirmed by one bounded second listing."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(visibility_delay=1)) as (host, pinned):
        document = once(artifact, environment, "--host", host)
        assert pinned.upload_requests == 1
        assert pinned.listing_requests == 3
    assert document["exit_code"] == COMPLETED
    assert document["outcome"] == "delivered"
    exchanges = entries(document, "exchanges")
    assert [exchange["stage"] for exchange in exchanges] == [
        "device-status",
        "preflight-listing",
        "upload",
        "postflight-confirmation",
        "postflight-confirmation",
    ]


def test_a_redirected_upload_is_unconfirmed_rather_than_followed(tmp_path: Path) -> None:
    """Redirects stay off for the writing request too, and the outcome stays honest."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(redirect_paths=("/upload",))) as (host, pinned):
        document = once(artifact, environment, "--host", host)
        assert pinned.uploads == []
    assert document["exit_code"] == UNCONFIRMED
    assert field(document, "action")["transport_status"] == 302


def test_an_unconfirmed_delivery_never_guesses_and_stays_retryable(tmp_path: Path) -> None:
    """Delayed visibility resolves itself on retry, which is why nothing is inferred."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(visibility_delay=2)) as (host, pinned):
        first = once(artifact, environment, "--host", host)
        assert first["exit_code"] == UNCONFIRMED
        assert "could not be confirmed" in str(field(first, "refusal")["summary"])
        second = once(artifact, environment, "--host", host)
        assert pinned.upload_requests == 1
    assert second["exit_code"] == COMPLETED
    assert second["outcome"] == "already-delivered"
    assert tree(workspace / "ready")


def test_a_retry_after_an_unconfirmed_upload_begins_with_normal_planning(tmp_path: Path) -> None:
    """Retry re-reads the destination rather than remembering, so a landed upload is success."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint(Device(listing_malformed_after_upload=True)) as (host, pinned):
        first = once(artifact, environment, "--host", host)
        assert first["exit_code"] == UNCONFIRMED
        pinned.listing_malformed_after_upload = False
        planned = command_document(
            run_command(
                ENTRY_POINT,
                "deliver",
                str(artifact),
                "--plan",
                "--json",
                "--host",
                host,
                environment=environment,
            )
        )
        second = once(artifact, environment, "--host", host)
        assert pinned.upload_requests == 1
    assert field(planned, "action")["planned"] == "already-delivered"
    assert second["outcome"] == "already-delivered"


def test_every_plan_and_attempt_writes_its_own_immutable_record(tmp_path: Path) -> None:
    """Records accumulate: nothing replaces, rewrites or removes an earlier one."""

    workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        _ = plan(artifact, environment, host)
        _ = plan(artifact, environment, host)
        earlier = tree(workspace / "delivery")
        _ = once(artifact, environment, "--host", host)
        _ = once(artifact, environment, "--host", host)
    stored = records(workspace)
    assert len(stored) == 4
    assert len({str(record["record_id"]) for record in stored}) == 4
    assert earlier.items() <= tree(workspace / "delivery").items()
    outcomes = [str(record["outcome"]) for record in stored]
    assert outcomes.count("planned") == 2
    assert "delivered" in outcomes and "already-delivered" in outcomes
    for record in stored:
        action = field(record, "action")
        assert "planned" in action and "upload_began" in action
        assert field(record, "destination")["preflight"] is not None


def test_retries_and_outages_never_touch_preparation_evidence(tmp_path: Path) -> None:
    """Delivery outcomes have no authority over Compatibility or Reading Quality evidence."""

    workspace, artifact, environment = published(tmp_path)
    before = tree(workspace / "ready")
    bundles = sorted((workspace / "ready" / "evidence").glob("*/report.json"))
    reports = [path.read_bytes() for path in bundles]
    _ = once(artifact, environment, "--host", "127.0.0.1:9", "--timeout", "0.25")
    with crosspoint(Device(files={artifact.name: 7})) as (host, _device):
        _ = once(artifact, environment, "--host", host)
        _ = once(artifact, environment, "--host", host, "--overwrite")
    with crosspoint(Device(visibility_delay=99)) as (host, _device):
        _ = once(artifact, environment, "--host", host)
    assert tree(workspace / "ready") == before
    assert [path.read_bytes() for path in bundles] == reports

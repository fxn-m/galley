"""Exercise the installed Agent Skill's separately authorised one-source X4 continuation."""

import re
from pathlib import Path

import pytest

from tests.skills.skill_fixtures import isolated_home
from tests.support.crosspoint_server import Device, crosspoint
from tests.support.delivery_fixtures import published
from tests.support.public_cli import run_cli
from tests.support.workspace_fixtures import command_document, field

SKILL = Path("src/galley/skills/galley")
RESOURCE = Path("resources/x4-delivery.md")
COMPLETED = 0
REFUSED = 3
UNCONFIRMED = 5


def _commands(text: str) -> list[list[str]]:
    blocks = re.findall(r"```text\n(.*?)```", text, flags=re.DOTALL)
    return [block.replace("\\\n", " ").split() for block in blocks if block.startswith("galley ")]


@pytest.fixture(scope="module")
def installed_guidance(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("x4-one-source-handoff")
    target = root / "skills-0"
    result = run_cli(
        "skill",
        "install",
        "--target",
        str(target),
        "--json",
        environment=isolated_home(root / "home-0"),
    )
    assert (result.returncode, result.stderr) == (0, "")
    resource = target / "galley" / RESOURCE
    assert resource.read_bytes() == (SKILL / RESOURCE).read_bytes()
    return resource.read_text(encoding="utf-8")


def _arguments(template: list[str], artifact: Path, host: str, *, overwrite: bool) -> list[str]:
    values = {
        "READY": str(artifact),
        "HOST": host,
        "DESTINATION": "/",
    }
    arguments = [values.get(item, item) for item in template[1:]]
    if not overwrite:
        arguments = [item for item in arguments if item != "--overwrite"]
    return arguments


def test_every_documented_x4_command_runs_through_the_installed_cli(
    tmp_path: Path, installed_guidance: str
) -> None:
    """The exact plan, approved upload and separately approved overwrite templates all execute."""

    _workspace, artifact, environment = published(tmp_path)
    templates = _commands(installed_guidance)
    assert len(templates) == 3
    with crosspoint() as (host, device):
        planned = run_cli(
            *_arguments(templates[0], artifact, host, overwrite=False), environment=environment
        )
        delivered = run_cli(
            *_arguments(templates[1], artifact, host, overwrite=False), environment=environment
        )
        assert device.upload_requests == 1
    assert planned.returncode == delivered.returncode == COMPLETED
    assert field(command_document(planned), "action")["planned"] == "upload-new"
    assert command_document(delivered)["outcome"] == "delivered"

    collision = Device(files={artifact.name: artifact.stat().st_size + 1})
    with crosspoint(collision) as (host, device):
        overwritten = run_cli(
            *_arguments(templates[2], artifact, host, overwrite=True), environment=environment
        )
        assert device.upload_requests == 1
    assert overwritten.returncode == COMPLETED
    assert field(command_document(overwritten), "action")["planned"] == "overwrite"


def test_x4_guidance_scopes_approval_and_translates_every_consequential_branch(
    installed_guidance: str,
) -> None:
    """Conversation stays small while the retained commands and outcomes stay exact."""

    guidance = installed_guidance
    compact = " ".join(guidance.split())
    assert "Send it to X4?" in compact
    assert "Ready Artifact, logical host, destination and `upload-new` action" in compact
    assert "freeze the Ready Artifact, logical host and destination" in compact
    assert "already on the X4" in compact
    assert "replacement decision" in compact
    assert "separate explicit approval" in compact
    assert "changed artifact" in compact
    assert "no longer identifies as X4" in compact
    assert "Unconfirmed" in compact
    assert "wake the device" in compact
    assert "freshly validated local address" in compact
    assert "does not invalidate approval" in compact


def test_documented_x4_boundaries_stop_or_remain_unconfirmed_without_extra_uploads(
    tmp_path: Path,
) -> None:
    """Already-present, collision, changed input, wrong device and uncertainty keep their meaning."""

    _workspace, artifact, environment = published(tmp_path)
    size = artifact.stat().st_size
    with crosspoint(Device(files={artifact.name: size})) as (host, device):
        present = run_cli(
            "deliver", str(artifact), "--json", "--host", host, environment=environment
        )
        assert device.upload_requests == 0
    assert command_document(present)["outcome"] == "already-delivered"

    with crosspoint(Device(files={artifact.name: size + 1})) as (host, device):
        collision = run_cli(
            "deliver", str(artifact), "--json", "--host", host, environment=environment
        )
        assert device.upload_requests == 0
    assert collision.returncode == REFUSED
    assert field(command_document(collision), "refusal")["boundary"] == "destination-collision"

    _ = artifact.write_bytes(artifact.read_bytes() + b"changed")
    with crosspoint() as (host, device):
        changed = run_cli(
            "deliver", str(artifact), "--json", "--host", host, environment=environment
        )
        assert device.upload_requests == 0
    assert changed.returncode == REFUSED

    _workspace, artifact, environment = published(tmp_path / "fresh")
    with crosspoint(Device(status={"device": "X3", "version": "1.0"})) as (host, device):
        wrong = run_cli("deliver", str(artifact), "--json", "--host", host, environment=environment)
        assert device.upload_requests == 0
    assert wrong.returncode == REFUSED

    with crosspoint(Device(visibility_delay=99)) as (host, device):
        uncertain = run_cli(
            "deliver", str(artifact), "--json", "--host", host, environment=environment
        )
        assert device.upload_requests == 1
    assert uncertain.returncode == UNCONFIRMED
    assert command_document(uncertain)["outcome"] == "unconfirmed"

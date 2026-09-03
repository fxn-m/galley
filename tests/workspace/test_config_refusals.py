"""Refuse every invalid Workspace Configuration deterministically, through the public CLI."""

from pathlib import Path

import pytest

from tests.support.public_cli import run_cli
from tests.support.workspace_fixtures import (
    command_document,
    field,
    inbox_table,
    valid_workspace,
    workspace_environment,
    write_configuration,
)

REFUSED = 3

VALID_INBOX = inbox_table("galley", "inbox")

INVALID_CONFIGURATIONS = (
    ("version = 2\n\n" + VALID_INBOX, "unsupported-configuration-version"),
    ('version = 1\ncolour = "blue"\n\n' + VALID_INBOX, "unknown-configuration-key"),
    ("version = 1\n\n" + VALID_INBOX + "\n" + inbox_table("galley", "."), "duplicate-inbox-name"),
    ("version = 1\n", "invalid-workspace-configuration"),
    ('version = 1\n\n[[inbox]]\nname = "galley"\n', "invalid-workspace-configuration"),
    (
        'version = 1\n\n[[inbox]]\nname = ""\npath = "inbox"\nrecursive = false\n',
        "invalid-workspace-configuration",
    ),
    (
        "version = 1\n\n" + VALID_INBOX + '\n[[inbox]]\nname = "x"\npath = "y"\nrecursive = 1\n',
        "invalid-workspace-configuration",
    ),
    (
        "version = 1\n\n" + VALID_INBOX + "\n[x4-crosspoint]\nport = 80\n",
        "unknown-configuration-key",
    ),
    (
        "version = 1\n\n" + VALID_INBOX + '\n[x4-crosspoint]\nhost = ""\n',
        "invalid-workspace-configuration",
    ),
    ("version = 1\n[[inbox\n", "invalid-workspace-configuration"),
)


@pytest.mark.parametrize(("body", "boundary"), INVALID_CONFIGURATIONS)
def test_invalid_configurations_refuse_at_a_named_boundary(
    tmp_path: Path, body: str, boundary: str
) -> None:
    """Each malformed configuration refuses at its own boundary rather than being repaired."""

    workspace = tmp_path / "workspace"
    (workspace / "inbox").mkdir(parents=True)
    _ = write_configuration(workspace, body)
    environment = workspace_environment(workspace, tmp_path / "home")
    result = run_cli("config", "validate", "--json", environment=environment)
    document = command_document(result)
    refusal = field(document, "refusal")
    assert refusal["boundary"] == boundary
    assert refusal["authority"] == "config validate"
    assert document["outcome"] == "refused"
    assert result.returncode == REFUSED


def test_a_missing_inbox_directory_refuses(tmp_path: Path) -> None:
    """An external Inbox must already exist: Galley never creates or alters one."""

    workspace = tmp_path / "workspace"
    _ = write_configuration(
        workspace, "version = 1\n\n" + inbox_table("clippings", str(tmp_path / "absent"))
    )
    environment = workspace_environment(workspace, tmp_path / "home")
    result = run_cli("config", "validate", "--json", environment=environment)
    refusal = field(command_document(result), "refusal")
    assert refusal["boundary"] == "inbox-unavailable"
    assert refusal["fact"] == {
        "configured_path": str(tmp_path / "absent"),
        "name": "clippings",
        "resolved_path": str((tmp_path / "absent").resolve()),
        "state": "absent",
    }
    assert result.returncode == REFUSED


def test_an_inbox_naming_a_file_refuses_on_its_path_kind(tmp_path: Path) -> None:
    """A configured Inbox that is a regular file is the wrong kind of path for its role."""

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    occupied = workspace / "inbox"
    _ = occupied.write_text("not a directory\n", encoding="utf-8")
    _ = write_configuration(workspace, "version = 1\n\n" + inbox_table("galley", "inbox"))
    environment = workspace_environment(workspace, tmp_path / "home")
    result = run_cli("config", "validate", "--json", environment=environment)
    refusal = field(command_document(result), "refusal")
    assert refusal["boundary"] == "inbox-unavailable"
    assert field(refusal, "fact")["state"] == "not-a-directory"
    assert result.returncode == REFUSED


def test_an_unreadable_inbox_refuses(tmp_path: Path) -> None:
    """A directory Galley cannot read is reported as unreadable rather than silently empty."""

    workspace = tmp_path / "workspace"
    external = tmp_path / "locked"
    external.mkdir(parents=True)
    external.chmod(0o000)
    _ = write_configuration(workspace, "version = 1\n\n" + inbox_table("locked", str(external)))
    environment = workspace_environment(workspace, tmp_path / "home")
    try:
        result = run_cli("config", "validate", "--json", environment=environment)
        refusal = field(command_document(result), "refusal")
        assert refusal["boundary"] == "inbox-unavailable"
        assert field(refusal, "fact")["state"] == "unreadable"
        assert result.returncode == REFUSED
    finally:
        external.chmod(0o700)


def test_an_owned_location_of_the_wrong_kind_refuses(tmp_path: Path) -> None:
    """A Galley-owned location occupied by a file cannot serve its role, and says so."""

    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace, owned=False)
    _ = (workspace / "ready").write_text("occupied\n", encoding="utf-8")
    environment = workspace_environment(workspace, tmp_path / "home")
    result = run_cli("config", "validate", "--json", environment=environment)
    refusal = field(command_document(result), "refusal")
    assert refusal["boundary"] == "workspace-location-unusable"
    assert field(refusal, "fact")["role"] == "ready"
    assert result.returncode == REFUSED

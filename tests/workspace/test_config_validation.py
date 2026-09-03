"""Validate Workspace Configuration through the installed public CLI."""

from pathlib import Path

from tests.support.public_cli import run_cli
from tests.support.workspace_fixtures import (
    command_document,
    entries,
    field,
    inbox_table,
    isolated_home,
    tree,
    valid_workspace,
    workspace_environment,
    write_configuration,
)

COMPLETED = 0
REFUSED = 3


def test_default_workspace_sits_under_the_documents_directory(tmp_path: Path) -> None:
    """With no option and no `GALLEY_HOME`, the visible default under Documents is resolved."""

    home = tmp_path / "home"
    result = run_cli("config", "validate", "--json", environment=isolated_home(home))
    workspace = field(command_document(result), "workspace")
    assert workspace["source"] == "default"
    assert workspace["path"] == str((home / "Documents" / "Galley").resolve())
    assert result.returncode == REFUSED


def test_environment_and_option_take_precedence_in_that_order(tmp_path: Path) -> None:
    """The explicit option beats `GALLEY_HOME`, which beats the default."""

    home = tmp_path / "home"
    named = tmp_path / "named"
    chosen = tmp_path / "chosen"
    _ = valid_workspace(named)
    _ = valid_workspace(chosen)
    environment = workspace_environment(named, home)
    result = run_cli("config", "validate", "--json", environment=environment)
    workspace = field(command_document(result), "workspace")
    assert workspace["source"] == "environment"
    assert workspace["path"] == str(named.resolve())
    result = run_cli(
        "config", "validate", "--workspace", str(chosen), "--json", environment=environment
    )
    workspace = field(command_document(result), "workspace")
    assert workspace["source"] == "option"
    assert workspace["path"] == str(chosen.resolve())
    assert result.returncode == COMPLETED


def test_resolution_never_searches_the_current_directory(tmp_path: Path) -> None:
    """A Workspace beside the invocation is not found: only the fixed precedence is consulted."""

    home = tmp_path / "home"
    nearby = tmp_path / "nearby"
    _ = valid_workspace(nearby)
    result = run_cli("config", "validate", "--json", environment=isolated_home(home))
    refusal = field(command_document(result), "refusal")
    assert refusal["boundary"] == "workspace-configuration-missing"
    assert result.returncode == REFUSED


def test_a_valid_configuration_reports_every_resolution(tmp_path: Path) -> None:
    """Version 1 accepts ordered named Inboxes with paths, recursion and connection details."""

    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    external = tmp_path / "vault" / "Clippings"
    external.mkdir(parents=True)
    (workspace / "inbox").mkdir(parents=True)
    for name in ("work", "ready", "delivery"):
        (workspace / name).mkdir(parents=True)
    _ = write_configuration(
        workspace,
        "version = 1\n\n"
        + inbox_table("galley", "inbox")
        + "\n"
        + inbox_table("clippings", str(external), recursive=True)
        + '\n[x4-crosspoint]\nhost = "x4.local"\n',
    )
    environment = workspace_environment(workspace, home)
    result = run_cli("config", "validate", "--json", environment=environment)
    document = command_document(result)
    assert result.returncode == COMPLETED
    assert document["outcome"] == "completed"
    assert document["configuration"] == {"schema": "galley/workspace-config/1", "version": 1}
    inboxes = entries(document, "inboxes")
    assert [entry["name"] for entry in inboxes] == ["galley", "clippings"]
    assert inboxes[0]["path_resolution"] == "relative"
    assert inboxes[0]["resolved_path"] == str((workspace / "inbox").resolve())
    assert inboxes[1]["path_resolution"] == "absolute"
    assert inboxes[1]["recursive"] is True
    assert all(entry["state"] == "usable" for entry in inboxes)
    assert document["connection"] == {
        "host": {"value": "x4.local", "source": "configured"},
        "destination": {"value": "/", "source": "default"},
    }
    locations = entries(document, "locations")
    assert [entry["role"] for entry in locations] == ["work", "ready", "delivery"]
    assert all(entry["state"] == "usable" for entry in locations)


def test_a_home_relative_inbox_resolves_against_the_home_directory(tmp_path: Path) -> None:
    """A `~`-spelled Inbox path is reported as home-relative and resolved explicitly."""

    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    (home / "Reading").mkdir(parents=True)
    _ = write_configuration(workspace, "version = 1\n\n" + inbox_table("reading", "~/Reading"))
    environment = workspace_environment(workspace, home)
    result = run_cli("config", "validate", "--json", environment=environment)
    inboxes = entries(command_document(result), "inboxes")
    assert inboxes[0]["path_resolution"] == "home-relative"
    assert inboxes[0]["resolved_path"] == str((home / "Reading").resolve())
    assert result.returncode == COMPLETED


def test_absent_owned_locations_are_reported_without_refusing(tmp_path: Path) -> None:
    """The CLI never creates its own directories, so absent ones are a fact, not a fault."""

    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace, owned=False)
    environment = workspace_environment(workspace, home)
    result = run_cli("config", "validate", "--json", environment=environment)
    locations = entries(command_document(result), "locations")
    assert all(entry["state"] == "absent" for entry in locations)
    assert result.returncode == COMPLETED


def test_validation_writes_nothing_at_all(tmp_path: Path) -> None:
    """Validation performs no configuration write, Inbox inventory or source mutation."""

    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace)
    source = workspace / "inbox" / "note.md"
    _ = source.write_text("# Note\n", encoding="utf-8")
    environment = workspace_environment(workspace, home)
    before = tree(tmp_path)
    result = run_cli("config", "validate", "--json", environment=environment)
    assert result.returncode == COMPLETED
    assert tree(tmp_path) == before


def test_human_output_states_the_same_facts_as_the_document(tmp_path: Path) -> None:
    """Concise output is rendered from the document rather than assembled separately."""

    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace)
    environment = workspace_environment(workspace, home)
    result = run_cli("config", "validate", environment=environment)
    assert result.stdout.startswith("config validate: completed\n")
    assert str(workspace.resolve()) in result.stdout
    assert "Inbox galley:" in result.stdout
    assert "crosspoint.local (default)" in result.stdout
    assert result.returncode == COMPLETED


def test_an_unwritable_owned_location_is_reported_rather_than_refused(tmp_path: Path) -> None:
    """Validation was asked to report type and access; only the wrong kind of path refuses."""

    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace)
    (workspace / "ready").chmod(0o500)
    environment = workspace_environment(workspace, home)
    try:
        result = run_cli("config", "validate", "--json", environment=environment)
        locations = entries(command_document(result), "locations")
        states = {str(entry["role"]): entry["state"] for entry in locations}
        assert states["ready"] == "unwritable"
        assert result.returncode == COMPLETED
    finally:
        (workspace / "ready").chmod(0o700)

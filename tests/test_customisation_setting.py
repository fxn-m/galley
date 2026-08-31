"""Customisation is opaque user-authored text, exposed by the read-only public validator."""

import json
from pathlib import Path

import pytest

from tests.public_cli import run_public_cli
from tests.workspace_fixtures import (
    command_document,
    field,
    tree,
    valid_workspace,
    workspace_environment,
)


@pytest.mark.parametrize(
    ("section", "instructions", "source"),
    (
        ("", "", "default"),
        ('\n[customisation]\ninstructions = ""\n', "", "configured"),
        (
            '\n[customisation]\ninstructions = """\nUse geometric covers.\nKeep café titles.\n"""\n',
            "Use geometric covers.\nKeep café titles.\n",
            "configured",
        ),
    ),
)
def test_customisation_round_trips_without_changing_the_workspace(
    tmp_path: Path, section: str, instructions: str, source: str
) -> None:
    workspace = tmp_path / "workspace"
    config = valid_workspace(workspace)
    _ = config.write_text(config.read_text() + section, encoding="utf-8")
    before = config.read_bytes(), config.stat().st_mtime_ns, tree(workspace)
    environment = workspace_environment(workspace, tmp_path / "home")

    for result in run_public_cli("config", "validate", "--json", environment=environment):
        document = command_document(result)
        assert result.returncode == 0, document
        assert document["customisation"] == {"instructions": instructions, "source": source}
        assert field(document, "configuration")["version"] == 1
        assert document["cover_artwork"] == {"value": False, "source": "default"}
    assert (config.read_bytes(), config.stat().st_mtime_ns, tree(workspace)) == before


@pytest.mark.parametrize(
    ("setting", "boundary"),
    (
        ('customisation = "prose"', "invalid-workspace-configuration"),
        ("customisation = []", "invalid-workspace-configuration"),
        ("[customisation]", "invalid-workspace-configuration"),
        ("[customisation]\ninstructions = true", "invalid-workspace-configuration"),
        ("[customisation]\ninstructions = 1", "invalid-workspace-configuration"),
        ("[customisation]\ninstructions = []", "invalid-workspace-configuration"),
        ("[customisation.instructions]", "invalid-workspace-configuration"),
        (
            '[customisation]\ninstructions = "Use geometric covers."\ncommand = "send"',
            "unknown-configuration-key",
        ),
    ),
)
def test_customisation_keeps_the_configuration_schema_strict(
    tmp_path: Path, setting: str, boundary: str
) -> None:
    workspace = tmp_path / "workspace"
    config = valid_workspace(workspace)
    header, inbox = config.read_text().split("[[inbox]]", 1)
    _ = config.write_text(f"{header}{setting}\n\n[[inbox]]{inbox}", encoding="utf-8")
    environment = workspace_environment(workspace, tmp_path / "home")

    for result in run_public_cli("config", "validate", "--json", environment=environment):
        document = command_document(result)
        assert result.returncode == 3
        refusal = field(document, "refusal")
        assert refusal["boundary"] == boundary
        assert document["customisation"] is None
        if boundary == "unknown-configuration-key":
            assert field(refusal, "fact")["accepted"] == ["instructions"]


def test_instructions_are_reported_as_text_and_never_executed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    config = valid_workspace(workspace)
    marker = workspace / "should-not-exist"
    instructions = f'touch "{marker}"; $(touch "{marker}")'
    _ = config.write_text(
        config.read_text() + f"\n[customisation]\ninstructions = {json.dumps(instructions)}\n",
        encoding="utf-8",
    )
    environment = workspace_environment(workspace, tmp_path / "home")

    for result in run_public_cli("config", "validate", "--json", environment=environment):
        assert result.returncode == 0
        assert field(command_document(result), "customisation")["instructions"] == instructions
    assert not marker.exists()
    for result in run_public_cli("config", "validate", environment=environment):
        assert result.returncode == 0
        assert "Customisation (configured):" in result.stdout
        assert instructions in result.stdout
    assert not marker.exists()

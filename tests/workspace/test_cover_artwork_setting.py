"""The Cover Artwork setting is an optional Workspace Configuration boolean."""

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

COMPLETED = 0
REFUSED = 3
INBOX = inbox_table("galley", "inbox")


def _validate(tmp_path: Path, body: str) -> tuple[int, dict[str, object]]:
    workspace = tmp_path / "workspace"
    (workspace / "inbox").mkdir(parents=True)
    _ = write_configuration(workspace, body)
    environment = workspace_environment(workspace, tmp_path / "home")
    return (
        run_cli("config", "validate", "--json", environment=environment).returncode,
        command_document(run_cli("config", "validate", "--json", environment=environment)),
    )


def test_an_omitted_cover_artwork_key_is_off_by_default(tmp_path: Path) -> None:
    code, document = _validate(tmp_path, "version = 1\n\n" + INBOX)
    assert code == COMPLETED
    assert document["cover_artwork"] == {"value": False, "source": "default"}


@pytest.mark.parametrize("stated", (True, False))
def test_an_explicit_cover_artwork_boolean_is_configured(tmp_path: Path, stated: bool) -> None:
    body = f"version = 1\ncover-artwork = {str(stated).lower()}\n\n{INBOX}"
    code, document = _validate(tmp_path, body)
    assert code == COMPLETED
    assert document["cover_artwork"] == {"value": stated, "source": "configured"}


@pytest.mark.parametrize(
    "line",
    ('cover-artwork = "yes"', "cover-artwork = 1", 'cover-artwork = "true"'),
)
def test_a_non_boolean_cover_artwork_value_is_invalid(tmp_path: Path, line: str) -> None:
    code, document = _validate(tmp_path, f"version = 1\n{line}\n\n{INBOX}")
    assert code == REFUSED
    assert field(document, "refusal")["boundary"] == "invalid-workspace-configuration"


def test_an_unknown_key_is_still_refused_and_version_stays_one(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace)
    environment = workspace_environment(workspace, tmp_path / "home")
    result = run_cli("config", "validate", "--json", environment=environment)
    document = command_document(result)
    assert field(document, "configuration")["version"] == 1
    assert result.returncode == COMPLETED
    code, document = _validate(tmp_path / "unknown", 'version = 1\ncolour = "blue"\n\n' + INBOX)
    assert code == REFUSED
    assert field(document, "refusal")["boundary"] == "unknown-configuration-key"


def test_recommended_defaults_omit_the_cover_artwork_key() -> None:
    template = Path("src/galley/skills/galley-setup/resources/workspace-config.md").read_text(
        encoding="utf-8"
    )
    block = template[
        template.index("```toml") : template.index("```\n", template.index("```toml") + 1)
    ]
    assert "cover-artwork" not in block


def test_human_output_names_the_cover_artwork_setting(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace)
    environment = workspace_environment(workspace, tmp_path / "home")
    result = run_cli("config", "validate", environment=environment)
    assert "Cover artwork: off (default)" in result.stdout
    assert result.returncode == COMPLETED

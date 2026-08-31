"""Installed reading and setup guidance share a usable customisation contract."""

from pathlib import Path

from tests.public_cli import public_cli_commands, run_command
from tests.skill_fixtures import isolated_home
from tests.workspace_fixtures import command_document, field, valid_workspace


def test_installed_customisation_guide_is_reachable_and_its_example_validates(
    tmp_path: Path,
) -> None:
    for index, command in enumerate(public_cli_commands()):
        target = tmp_path / f"skills-{index}"
        environment = isolated_home(tmp_path / f"home-{index}")
        installed = run_command(
            command,
            "skill",
            "install",
            "--target",
            str(target),
            "--json",
            environment=environment,
        )
        assert (installed.returncode, installed.stderr) == (0, "")
        guide = target / "galley/resources/customisation.md"
        assert (
            guide.read_bytes()
            == Path("src/galley/skills/galley/resources/customisation.md").read_bytes()
        )

        # Both entry skills and their workflow resources must reach the same installed policy.
        for relative in (
            "galley/SKILL.md",
            "galley/resources/assisted-preparation.md",
            "galley/resources/galley-my-inbox.md",
            "galley/resources/kindle-ios-handoff.md",
            "galley-setup/SKILL.md",
            "galley-setup/resources/reconfiguration.md",
            "galley-setup/resources/workspace-config.md",
        ):
            resource = target / relative
            links = [part.split(")", 1)[0] for part in resource.read_text().split("](")[1:]]
            assert any((resource.parent / link).resolve() == guide.resolve() for link in links)

        example = guide.read_text().split("```toml\n", 1)[1].split("```", 1)[0]
        workspace = tmp_path / f"workspace-{index}"
        config = valid_workspace(workspace)
        _ = config.write_text(config.read_text() + "\n" + example, encoding="utf-8")
        before = config.read_bytes(), config.stat().st_mtime_ns
        validated = run_command(
            command,
            "config",
            "validate",
            "--workspace",
            str(workspace),
            "--json",
            environment=environment,
        )
        assert (validated.returncode, validated.stderr) == (0, "")
        assert field(command_document(validated), "customisation") == {
            "instructions": "Use restrained geometric artwork for custom covers.\n",
            "source": "configured",
        }
        assert (config.read_bytes(), config.stat().st_mtime_ns) == before

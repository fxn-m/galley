"""Keep Galley's exact technical record separate from its conversation with the reader."""

from pathlib import Path

import pytest

from tests.public_cli import public_cli_commands, run_command
from tests.skill_fixtures import isolated_home

SKILL = Path("src/galley/skills/galley")
RESOURCE = Path("resources/user-facing-communication.md")


@pytest.fixture(scope="module")
def installed_guidance(tmp_path_factory: pytest.TempPathFactory) -> tuple[tuple[str, str], ...]:
    root = tmp_path_factory.mktemp("user-facing-communication")
    installed: list[tuple[str, str]] = []
    for index, installer in enumerate(public_cli_commands("skill", "install")):
        target = root / f"installed-skills-{index}"
        result = run_command(
            installer,
            "--target",
            str(target),
            "--json",
            environment=isolated_home(root / f"home-{index}"),
        )
        assert (result.returncode, result.stderr) == (0, "")
        main = target / "galley" / "SKILL.md"
        guidance = target / "galley" / RESOURCE
        assert main.read_bytes() == (SKILL / "SKILL.md").read_bytes()
        assert guidance.read_bytes() == (SKILL / RESOURCE).read_bytes()
        installed.append((main.read_text(encoding="utf-8"), guidance.read_text(encoding="utf-8")))
    return tuple(installed)


def test_main_skill_requires_plain_communication_before_updates(
    installed_guidance: tuple[tuple[str, str], ...],
) -> None:
    for main, _guidance in installed_guidance:
        section = " ".join(
            main[main.index("## Keep the conversation plain") : main.index("## Establish")].split()
        )
        assert "user-facing communication contract" in section
        assert "before the first update" in section
        assert "ordinary language" in section
        assert "technical details available rather than foregrounded" in section


def test_guidance_translates_internal_states_and_limits_update_noise(
    installed_guidance: tuple[tuple[str, str], ...],
) -> None:
    for _main, guidance in installed_guidance:
        compact = " ".join(guidance.split())
        assert "useful updates, not a narrated pipeline" in compact.casefold()
        assert "Combine adjacent internal stages into one update" in compact
        assert "one or two sentences" in compact
        assert all(
            translation in compact
            for translation in (
                "Galley needs setting up first.",
                "The article looks straightforward.",
                "I’m downloading the article’s images.",
                "The cover is ready.",
                "It passed Galley’s checks.",
                "Kindle-ready file",
            )
        )
        assert "not conversational labels" in compact


def test_success_handoff_leads_with_file_action_and_caveats_not_audit_fields(
    installed_guidance: tuple[tuple[str, str], ...],
) -> None:
    for _main, guidance in installed_guidance:
        final = " ".join(guidance[guidance.index("## Finish with") :].split())
        assert "lead with the clickable file path" in final
        assert "next action" in final
        assert "reading caveats that matter" in final
        assert "**Technical report**" in final
        assert all(
            detail in final
            for detail in ("File size", "SHA-256", "profile identifiers", "checker counts")
        )
        assert "stay out of the primary response" in final

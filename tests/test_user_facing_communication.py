"""Keep Galley's exact technical record separate from its conversation with the reader."""

from pathlib import Path

import pytest

from tests.public_cli import run_cli
from tests.skill_fixtures import isolated_home

SKILL = Path("src/galley/skills/galley")
RESOURCE = Path("resources/user-facing-communication.md")


@pytest.fixture(scope="module")
def installed_guidance(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    root = tmp_path_factory.mktemp("user-facing-communication")
    target = root / "installed-skills-0"
    result = run_cli(
        "skill",
        "install",
        "--target",
        str(target),
        "--json",
        environment=isolated_home(root / "home-0"),
    )
    assert (result.returncode, result.stderr) == (0, "")
    main = target / "galley" / "SKILL.md"
    guidance = target / "galley" / RESOURCE
    assert main.read_bytes() == (SKILL / "SKILL.md").read_bytes()
    assert guidance.read_bytes() == (SKILL / RESOURCE).read_bytes()
    return (main.read_text(encoding="utf-8"), guidance.read_text(encoding="utf-8"))


def test_main_skill_requires_plain_communication_before_updates(
    installed_guidance: tuple[str, str],
) -> None:
    main, _guidance = installed_guidance
    section = " ".join(
        main[main.index("## Keep the conversation plain") : main.index("## Establish")].split()
    )
    assert "user-facing communication contract" in section
    assert "before the first update" in section
    assert "ordinary language" in section
    assert "technical details available rather than foregrounded" in section


def test_guidance_translates_internal_states_and_limits_update_noise(
    installed_guidance: tuple[str, str],
) -> None:
    _main, guidance = installed_guidance
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
    installed_guidance: tuple[str, str],
) -> None:
    _main, guidance = installed_guidance
    final = " ".join(guidance[guidance.index("## Finish with") :].split())
    assert "lead with “It passed Galley's checks.”" in final
    assert "exact artifact basename as clickable text" in final
    assert "Report's absolute `artifact.path` as its target" in final
    assert "raw path again" in final
    assert "next action" in final
    assert "reading caveats that matter" in final
    assert "**Technical report**" in final
    assert all(
        detail in final
        for detail in ("File size", "SHA-256", "profile identifiers", "checker counts")
    )
    assert "stay out of the primary response" in final
    assert "one-off request ends after this useful handoff" in final
    assert "Plural or clearly unfinished work" in final


def test_named_profile_is_selected_without_a_second_question(
    installed_guidance: tuple[str, str],
) -> None:
    """The request selects a named target; only an unnamed target needs concise choices."""

    main, _guidance = installed_guidance
    profile = " ".join(
        main[
            main.index("## Confirm the Device Profile") : main.index("## Assisted Preparation")
        ].split()
    )
    assert "run `galley profiles list --json`" in profile
    assert "explicitly names Kindle or X4" in profile
    assert "proceed without another question" in profile
    assert "names no target" in profile
    assert "ask the user to choose" in profile
    for forbidden_source in (
        "Workspace configuration",
        "setup answers",
        "available hardware",
        "prior runs",
        "source content",
        "list order",
    ):
        assert forbidden_source in profile

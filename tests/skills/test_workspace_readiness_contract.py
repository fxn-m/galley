"""Hold one-source conversion work behind Workspace validation."""

from pathlib import Path

MAIN_SKILL = Path("src/galley/skills/galley/SKILL.md")


def test_the_main_skill_validates_workspace_before_profile_or_source_work() -> None:
    """A one-source Ready Artifact request must discover missing setup before doing source work."""

    main = MAIN_SKILL.read_text(encoding="utf-8")
    validation = main.index("## Establish Workspace readiness before conversion work")
    confirmation = main.index("## Confirm the Device Profile before conversion work")
    assisted = main.index("## Assisted Preparation")
    gate = " ".join(main[validation:confirmation].split())

    assert validation < confirmation < assisted
    assert "begin with `galley config validate --json`" in gate
    assert all(
        activity in gate
        for activity in (
            "`profiles list`",
            "reading the source",
            "`inspect`",
            "profile-directed cover work",
            "Localisation",
            "repair",
            "`prepare`",
        )
    )
    assert "hands the user immediately to the `galley-setup` skill" in gate
    assert "only after setup's final validator returns exit `0`" in gate

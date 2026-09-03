"""Hold setup's questions and confirmation to a portable harness contract."""

from pathlib import Path

SKILL = Path("src/galley/skills/galley-setup/SKILL.md")


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_setup_uses_native_questions_without_requiring_a_particular_harness() -> None:
    """The skill should exploit a picker when present and remain usable when it is absent."""

    skill = _skill_text()
    assert "All recommended defaults" in skill
    assert "Customise" in skill
    assert "batches of at most three questions" in skill
    assert "native structured-question tool" in skill
    assert "Do not change modes merely to obtain a picker" in skill
    assert "ordinary chat" in skill
    collapsed = " ".join(skill.split())
    assert "Do you want custom covers?" in collapsed
    assert "Write `cover-artwork = true` only when the reader asked for custom covers" in collapsed
    assert "Leaving a device value or the Cover Artwork key out is meaningful" in collapsed
    assert "All recommended defaults" in skill
    reconfiguration = " ".join(
        Path("src/galley/skills/galley-setup/resources/reconfiguration.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "Turning custom covers on or off edits that key alone" in reconfiguration


def test_setup_scopes_x4_questions_without_creating_a_default_conversion_target() -> None:
    """Reader scope makes irrelevant setup questions disappear but cannot choose a later
    artifact's Device Profile."""

    skill = _skill_text()
    scope = skill[
        skill.index("## Scope setup to the user's reading targets") : skill.index(
            "## One configuration fast path"
        )
    ]

    assert all(reader in scope for reader in ("Kindle for iOS", "Xteink X4", "both"))
    assert "not written to `galley.toml`" in scope
    assert "does not establish a default Device Profile" in scope
    assert "Ask about the CrossPoint host, destination and optional probe only" in scope
    assert "Kindle-only setup" in scope
    assert "separately confirms the Device Profile for every individual conversion" in scope


def test_configuration_choices_and_mutation_authorisation_are_separate() -> None:
    """Accepting defaults must never silently authorise dependency installs or file writes."""

    skill = _skill_text()
    policy = "Configuration answers select the proposed state; they do not authorise side effects"
    assert policy in skill
    assert "Proceed / Revise / Cancel" in skill
    assert "Proceed" in skill and "external installs and writes" in skill


def test_setup_keeps_technical_inventory_out_of_the_primary_conversation() -> None:
    """Exact setup evidence remains available without making the user follow its machinery."""

    skill = _skill_text()
    plain = skill[skill.index("## Keep setup plain") : skill.index("## Start with")]
    summary = skill[skill.index("## One summary, one confirmation") : skill.index("## What setup")]

    assert "Galley needs setting up first" in plain
    assert "outcomes and choices" in plain
    assert "no separate progress announcement" in plain
    assert "setup is complete" in plain
    assert "one concise message" in summary
    assert "one line saying all required tools are ready" in summary
    assert "selected readers, without explaining internal persistence" in summary
    assert "**Technical details** only for customised" in summary

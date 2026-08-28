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


def test_configuration_choices_and_mutation_authorisation_are_separate() -> None:
    """Accepting defaults must never silently authorise dependency installs or file writes."""

    skill = _skill_text()
    policy = "Configuration answers select the proposed state; they do not authorise side effects"
    assert policy in skill
    assert "Proceed / Revise / Cancel" in skill
    assert "Proceed" in skill and "external installs and writes" in skill

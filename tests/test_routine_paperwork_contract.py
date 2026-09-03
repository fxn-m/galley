"""Routine conversion does the named product work and leaves assessment for later."""

from pathlib import Path

import pytest

from tests.public_cli import run_cli
from tests.skill_fixtures import isolated_home

SKILL = Path("src/galley/skills/galley")


@pytest.fixture(scope="module")
def installed_texts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    root = tmp_path_factory.mktemp("routine-paperwork-contract")
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
    galley = target / "galley"
    files = {
        "skill": galley / "SKILL.md",
        "inbox": galley / "resources" / "galley-my-inbox.md",
        "assessment": galley / "resources" / "assessment.md",
        "assisted": galley / "resources" / "assisted-preparation.md",
    }
    for name, path in files.items():
        assert path.read_bytes() == (SKILL / path.relative_to(galley)).read_bytes(), name
    return {name: path.read_text(encoding="utf-8") for (name, path) in files.items()}


def test_routine_paths_leave_assessment_for_a_later_eval_or_device_read(
    installed_texts: dict[str, str],
) -> None:
    texts = installed_texts
    skill = " ".join(texts["skill"].split())
    inbox = " ".join(texts["inbox"].split())
    assessment = " ".join(texts["assessment"].split())
    assisted = " ".join(texts["assisted"].split())

    assert "Leave an Agent Assessment for a later eval or device-read" in skill
    assert "only when a later eval or device-read needs one" in skill
    assert "Read compact Report facts" in skill
    assert "Predicted Verdict in an assessment" not in skill
    assert "Do not write a technical report, helper script, or extra note" in skill
    assert "Leave an Agent Assessment and Predicted Verdict for a later eval" in inbox
    assert "Do not write a technical report, helper script, or extra note" in inbox
    assert "without writing that file" in assessment
    assert "Do not write a technical report, helper script, or extra note" in assisted

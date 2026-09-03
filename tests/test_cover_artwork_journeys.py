"""One-source and Inbox journeys follow the Cover Artwork setting."""

from pathlib import Path

import pytest

from tests.public_cli import run_cli
from tests.skill_fixtures import isolated_home

SKILL = Path("src/galley/skills/galley")


@pytest.fixture(scope="module")
def installed_texts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    root = tmp_path_factory.mktemp("cover-artwork-journeys")
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
        "assisted": galley / "resources" / "assisted-preparation.md",
        "skill": galley / "SKILL.md",
        "inbox": galley / "resources" / "galley-my-inbox.md",
        "delivery": galley / "resources" / "x4-delivery.md",
    }
    for name, path in files.items():
        assert path.read_bytes() == (SKILL / path.relative_to(galley)).read_bytes(), name
    return {name: path.read_text(encoding="utf-8") for (name, path) in files.items()}


def test_one_source_preparation_reads_the_setting_from_config_validate(
    installed_texts: dict[str, str],
) -> None:
    texts = installed_texts
    assisted = " ".join(texts["assisted"].split())
    skill = " ".join(texts["skill"].split())

    assert "Read `cover_artwork` from the successful `config validate`" in assisted
    assert "Silence follows that setting" in assisted
    assert "Read `cover_artwork` from the successful `config validate`" in skill
    assert "Setting off, or omitted" in assisted
    assert "Do not start a cover agent" in assisted
    assert "Setting on, and no source `cover-image`" in assisted
    assert "source `cover-image` stands even when the setting is on" in assisted
    assert "Make a nice cover for this one" in assisted
    assert "plain cover only" in assisted
    assert "overrides the setting for this request only" in assisted


def test_inbox_preparation_never_authors_cover_artwork(
    installed_texts: dict[str, str],
) -> None:
    texts = installed_texts
    inbox = " ".join(texts["inbox"].split())
    skill = " ".join(texts["skill"].split())

    assert "Inbox preparation never authors Cover Artwork" in inbox
    assert "regardless of the Workspace setting" in inbox
    assert "Inbox preparation never authors Cover Artwork" in skill


def test_a_later_cover_change_is_a_new_artifact_with_a_new_send(
    installed_texts: dict[str, str],
) -> None:
    texts = installed_texts
    assisted = " ".join(texts["assisted"].split())
    delivery = " ".join(texts["delivery"].split())

    assert "Send it to X4?" in assisted
    assert "Artwork and send are never one question" in assisted
    assert "Artwork and send are never one question" in delivery
    assert "later cover change" in assisted
    assert "new Ready Artifact" in assisted
    assert "output-exists" in assisted
    assert "Republishing the same source and hash" in assisted
    assert "Send it to X4?" in delivery

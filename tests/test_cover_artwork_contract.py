"""Hold the installed cover-authoring guide to its creative contract."""

from pathlib import Path

import pytest

from tests.public_cli import run_cli
from tests.skill_fixtures import isolated_home

GUIDE = Path("src/galley/skills/galley/resources/cover-artwork.md")


@pytest.fixture(scope="module")
def installed_guides(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("cover-guide-contract")
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
    installed = target / "galley" / "resources" / "cover-artwork.md"
    assert installed.read_bytes() == GUIDE.read_bytes()
    return installed.read_text(encoding="utf-8")


def section(text: str, start: str, end: str) -> str:
    return " ".join(text[text.index(start) : text.index(end)].split())


def test_cover_author_researches_then_chooses_identity_direction(
    installed_guides: str,
) -> None:
    text = installed_guides
    research = section(text, "## Understand the work", "## State one governing idea")
    assert "search the web" in research
    assert all(trail in research for trail in ("URLs consulted", "concrete cue"))
    assert all(direction in research for direction in ("established visual identity", "original"))
    assert all(token in research for token in ("palette", "typography", "grid", "image treatment"))
    assert "not an ingredient list" in research
    assert "compare against recent Galley covers" in research


def test_cover_author_commits_to_one_idea_and_restrained_copy(
    installed_guides: str,
) -> None:
    text = installed_guides
    idea = section(text, "## State one governing idea", "## Establish composition before detail")
    assert "Write one sentence" in idea
    assert "one dominant form" in idea
    assert "make every other element serve it" in idea
    assert all(hard in idea for hard in ("person", "animal", "machine", "anatomical and spatial"))
    assert all(copy in idea for copy in ("exact title", "known author", "never invent"))
    assert all(extra in idea for extra in ("synopsis", "quotation", "tagline", "badge"))
    assert "title the artwork" in idea


def test_cover_author_proves_the_grid_before_drawing_detail(
    installed_guides: str,
) -> None:
    text = installed_guides
    composition = section(
        text, "## Establish composition before detail", "## Author one self-contained SVG"
    )
    assert all(
        decision in composition
        for decision in (
            "rough block composition",
            "primary alignment",
            "title area",
            "negative space",
        )
    )
    assert "thumbnail size" in composition
    assert "Cropping and overlap must already look intentional" in composition
    assert "revise the grid" in composition
    assert "not every cue you found" in composition
    assert "own block composition" in composition
    artwork = section(text, "## Author one self-contained SVG", "## Render and judge the whole")
    assert "original lettering as SVG paths" in artwork
    assert "licence permits that use" in artwork


def test_cover_author_judges_the_whole_render_not_a_motif_checklist(
    installed_guides: str,
) -> None:
    text = installed_guides
    review = section(text, "## Render and judge the whole", "## Verify on the final prepare")
    assert all(view in review for view in ("full size", "small library thumbnail", "quantised"))
    assert all(
        whole in review
        for whole in ("one hierarchy", "alignments", "cropping", "overlaps", "empty space")
    )
    assert "revise the grid or governing idea" in review
    assert "rather than adding another motif" in review
    assert "viewed a render made after the last edit" in review
    assert all(handoff in review for handoff in ("one-line idea", "research trail"))


def test_cover_author_checks_raster_facts_on_the_final_ready_prepare(
    installed_guides: str,
) -> None:
    text = installed_guides
    verify = " ".join(text[text.index("## Verify on the final prepare") :].split())
    assert "rendered SVG previews" in verify
    assert "one final `--ready` prepare" in verify
    assert "not on a throwaway preview book" in verify
    assert "--output BOOK.epub" not in text
    assert "--ready" in verify
    assert "packaged.renderer" in verify
    assert "bundled font" in verify

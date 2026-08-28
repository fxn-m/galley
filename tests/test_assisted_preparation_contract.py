"""Hold the installed Agent Skill to the Assisted Preparation contract."""

from pathlib import Path

import pytest

from tests.public_cli import public_cli_commands, run_command
from tests.skill_fixtures import isolated_home

SKILL = Path("src/galley/skills/galley")
CONTRACT = Path("resources/assisted-preparation.md")


def _installed_contract(tmp_path: Path, index: int, installer: list[str]) -> str:
    """Install the public skill and return its Assisted Preparation contract."""

    target = tmp_path / f"installed-skills-{index}"
    result = run_command(
        installer,
        "--target",
        str(target),
        "--json",
        environment=isolated_home(tmp_path / f"home-{index}"),
    )
    assert (result.returncode, result.stderr) == (0, "")
    installed = target / "galley" / CONTRACT
    assert installed.read_bytes() == (SKILL / CONTRACT).read_bytes()
    return installed.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def installed_contracts(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, ...]:
    """Install once through both public entry points for every contract assertion."""

    tmp_path = tmp_path_factory.mktemp("assisted-preparation-contract")
    return tuple(
        _installed_contract(tmp_path, index, installer)
        for index, installer in enumerate(public_cli_commands("skill", "install"))
    )


def test_assisted_preparation_inspects_before_it_classifies_or_changes_the_source(
    installed_contracts: tuple[str, ...],
) -> None:
    """Every journey begins from inspection evidence and names its initial classification before
    repair, cover work, Localisation or final preparation can change or package the source."""

    for text in installed_contracts:
        inspect = text.index("## Inspect and classify first")
        later_work = text.index("## Work after classification")
        opening = " ".join(text[inspect:later_work].split())

        assert inspect < later_work
        assert (
            "galley inspect SOURCE --profile PROFILE --evidence-dir INSPECTION.galley --json"
            in opening
        )
        assert "Routine Assisted Preparation" in opening
        assert "Repairing Assisted Preparation" in opening
        assert all(
            activity in opening
            for activity in ("repair", "Cover Artwork", "Localisation", "final preparation")
        )


def test_assisted_preparation_visibly_reclassifies_when_later_evidence_requires_repair(
    installed_contracts: tuple[str, ...],
) -> None:
    """A Routine journey does not hide a later repair discovery: its public account changes to
    Repairing and tells the user what evidence changed the classification."""

    for text in installed_contracts:
        start = text.index("## Reclassify when evidence changes")
        end = text.index("## Work after classification")
        reclassification = " ".join(text[start:end].split())

        assert "Routine Assisted Preparation" in reclassification
        assert "Repairing Assisted Preparation" in reclassification
        assert "tell the user" in reclassification
        assert "evidence" in reclassification


def test_assisted_preparation_keeps_semantic_and_editorial_repair_choices_with_the_user(
    installed_contracts: tuple[str, ...],
) -> None:
    """Autonomy stops at the agreed repair boundary: all three safe properties must hold, while
    central-content, authorship, meaning and material editorial choices return to the user."""

    for text in installed_contracts:
        start = text.index("## Decide whether to repair or ask")
        end = text.index("## Work after classification")
        boundary = " ".join(text[start:end].split())

        assert all(
            criterion in boundary
            for criterion in ("unambiguous", "reversible", "outside the original source")
        )
        assert "only when all three hold" in boundary
        assert all(
            choice in boundary
            for choice in ("Central Content", "authorship", "meaning", "material editorial")
        )
        assert "ask the user" in boundary.casefold()


def test_assisted_preparation_delegates_complete_cover_ownership_with_a_main_agent_fallback(
    installed_contracts: tuple[str, ...],
) -> None:
    """A focused cover subagent owns the creative loop without duplicate review; the main agent
    owns that whole loop only when delegation is unavailable."""

    for text in installed_contracts:
        start = text.index("## Delegate Cover Artwork when possible")
        end = text.index("## Work after classification")
        cover = " ".join(text[start:end].split())

        assert "focused cover subagent" in cover
        assert all(
            responsibility in cover
            for responsibility in (
                "interpretation",
                "identity-cue research",
                "SVG creation",
                "rendering",
                "visual judgment",
                "revision",
            )
        )
        assert "recent Galley covers" in cover
        assert "main agent" in cover
        assert all(fact in cover for fact in ("rasterised", "referenced", "packaged"))
        assert "second creative or visual review" in cover
        assert "delegation is unavailable" in cover
        assert "complete cover role" in cover


def test_assisted_preparation_batches_repairs_and_parallelises_only_independent_work(
    installed_contracts: tuple[str, ...],
) -> None:
    """The workflow makes one coherent pass from initial evidence, previews the cover before the
    build, and reads compact facts instead of meandering through repeated work."""

    for text in installed_contracts:
        start = text.index("## Work after classification")
        end = text.index("## Keep the workflow boundary")
        workflow = " ".join(text[start:end].split())
        lowered = workflow.casefold()

        assert "batch coherent repairs" in lowered
        assert "one coherent repair pass" in lowered
        assert "parallelise only independent work" in lowered
        assert "preview the svg before packaging" in lowered
        assert "compact report facts" in lowered
        assert "unambiguous" in lowered
        assert "ambiguity" in lowered
        assert "ask the user" in lowered


def test_assisted_preparation_adds_no_orchestration_or_timing_system(
    installed_contracts: tuple[str, ...],
) -> None:
    """The skill keeps the settled no-timing boundary and does not describe a hidden runtime
    subsystem for what remains an agent-guided use of Galley's existing interfaces."""

    for text in installed_contracts:
        boundary = " ".join(text[text.index("## Keep the workflow boundary") :].split())
        lowered = boundary.casefold()

        assert "existing public interfaces" in lowered
        assert all(
            excluded in lowered
            for excluded in (
                "public command",
                "daemon",
                "state machine",
                "assisted preparation record",
                "timer",
                "telemetry",
                "target",
                "score",
                "retry counter",
                "dashboard",
                "service-level objective",
            )
        )
        assert "existing cli report timing" in lowered
        assert "success measure" in lowered

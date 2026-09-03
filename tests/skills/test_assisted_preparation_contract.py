"""Hold the installed Agent Skill to the Assisted Preparation contract."""

from pathlib import Path

import pytest

from tests.skills.skill_fixtures import isolated_home
from tests.support.public_cli import cli_command, run_command

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
def installed_contracts(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Install the contract through the installed command for the documentation assertions."""

    tmp_path = tmp_path_factory.mktemp("assisted-preparation-contract")
    return _installed_contract(tmp_path, 0, cli_command("skill", "install"))


def test_assisted_preparation_uses_a_named_profile_and_asks_only_when_none_is_named(
    installed_contracts: str,
) -> None:
    """The request can name the profile; ambient state cannot, and an unnamed request must ask."""

    text = installed_contracts
    confirmation = " ".join(
        text[
            text.index("## Confirm the Device Profile first") : text.index(
                "## Inspect and classify first"
            )
        ].split()
    )
    assert "galley profiles list --json" in confirmation
    assert "An explicit Kindle or X4 request establishes that profile" in confirmation
    assert "state the concise label and continue" in confirmation
    assert "With no named target" in confirmation
    assert "wait for the user's selection" in confirmation
    assert "**Kindle for iOS** for `kindle-ios-personal-documents`" in confirmation
    assert "**Xteink X4** for `x4-crosspoint`" in confirmation
    assert "ids and observed-device provenance in commands and Reports" in confirmation
    assert all(
        source in confirmation.casefold()
        for source in (
            "workspace configuration",
            "setup answers",
            "available hardware",
            "prior runs",
            "source content",
            "list order",
        )
    )


def test_assisted_preparation_validates_workspace_before_profile_or_source_work(
    installed_contracts: str,
) -> None:
    """A direct conversion request must enter setup before it spends work on an unusable
    Workspace or on the source itself."""

    text = installed_contracts
    validation = text.index("## Validate Workspace readiness first")
    confirmation = text.index("## Confirm the Device Profile first")
    inspection = text.index("## Inspect and classify first")
    gate = " ".join(text[validation:confirmation].split())

    assert validation < confirmation < inspection
    assert "Begin every Assisted Preparation with `galley config validate --json`" in gate
    assert all(
        activity in gate
        for activity in (
            "`galley profiles list`",
            "reading the source",
            "inspection",
            "Cover Artwork",
            "Localisation",
            "repair",
            "preparation",
        )
    )
    assert "hands the request immediately to `galley-setup`" in gate
    assert "pause source work" in gate.casefold()
    assert "only after setup's final `galley config validate --json` completes" in gate


def test_assisted_preparation_inspects_before_it_classifies_or_changes_the_source(
    installed_contracts: str,
) -> None:
    """Every journey begins from inspection evidence and classifies the work internally before
    repair, cover work, Localisation or final preparation can change or package the source."""

    text = installed_contracts
    inspect = text.index("## Inspect and classify first")
    later_work = text.index("## Work after classification")
    opening = " ".join(text[inspect:later_work].split())

    assert inspect < later_work
    assert (
        "galley inspect SOURCE --profile PROFILE --evidence-dir INSPECTION.galley --json" in opening
    )
    assert "Routine Assisted Preparation" in opening
    assert "Repairing Assisted Preparation" in opening
    assert all(
        activity in opening
        for activity in ("repair", "Cover Artwork", "Localisation", "final preparation")
    )


def test_assisted_preparation_plainly_explains_a_later_repair_without_internal_labels(
    installed_contracts: str,
) -> None:
    """A later repair discovery reaches the reader as a concrete finding, not workflow jargon."""

    text = installed_contracts
    start = text.index("## Reclassify when evidence changes")
    end = text.index("## Work after classification")
    reclassification = " ".join(text[start:end].split())

    assert "Routine Assisted Preparation" in reclassification
    assert "Repairing Assisted Preparation" in reclassification
    assert "internal classification" in reclassification
    assert "specific finding" in reclassification
    assert "plain language" in reclassification
    assert "without naming the classification" in reclassification
    assert "proof machinery" in reclassification


def test_assisted_preparation_keeps_semantic_and_editorial_repair_choices_with_the_user(
    installed_contracts: str,
) -> None:
    """Autonomy stops at the agreed repair boundary: all three safe properties must hold, while
    central-content, authorship, meaning and material editorial choices return to the user."""

    text = installed_contracts
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
    installed_contracts: str,
) -> None:
    """A focused cover subagent owns the creative loop without duplicate review; the main agent
    owns that whole loop only when delegation is unavailable."""

    text = installed_contracts
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
    installed_contracts: str,
) -> None:
    """The workflow makes one coherent pass from initial evidence, previews the cover before the
    build, and reads compact facts instead of meandering through repeated work."""

    text = installed_contracts
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


def test_assisted_preparation_always_finishes_with_a_ready_artifact(
    installed_contracts: str,
) -> None:
    """A chosen source reaches the same immutable Workspace boundary for every profile; later
    delivery or personal-document submission belongs to a separate actor."""

    text = installed_contracts
    opening = " ".join(text[: text.index("## Inspect and classify first")].split())
    workflow = " ".join(
        text[
            text.index("## Work after classification") : text.index("## Keep the workflow boundary")
        ].split()
    )

    assert "production of one Ready Artifact" in opening
    assert "Submission Artifact" not in opening
    assert "final preparation with `--ready`" in workflow
    assert "Report's `artifact.path`" in workflow


def test_assisted_preparation_adds_no_orchestration_or_timing_system(
    installed_contracts: str,
) -> None:
    """The skill keeps the settled no-timing boundary and does not describe a hidden runtime
    subsystem for what remains an agent-guided use of Galley's existing interfaces."""

    text = installed_contracts
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


def test_routine_assisted_preparation_does_the_named_conversion_work(
    installed_contracts: str,
) -> None:
    """Routine conversion inspects, localises, repairs, prepares once, and continues into
    Delivery. Paperwork and a preview prepare are not part of that path."""

    text = installed_contracts
    workflow = " ".join(
        text[
            text.index("## Work after classification") : text.index("## Keep the workflow boundary")
        ].split()
    )
    assert "inspect, localise, repair when needed, prepare once" in workflow
    assert "compact Report facts rather than the whole JSON dump" in workflow
    assert "material caveats" in workflow
    assert "without rewriting title or author metadata" in workflow
    assert "later eval or device-read" in workflow
    assert "Predicted Verdict" not in workflow
    assert "Do not write a technical report, helper script, or extra note" in workflow

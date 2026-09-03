"""Hold the Agent Skill to the CLI it documents.

The skill is a product surface, so an option it names that the CLI does not have is
a defect in the product, not a typo in a document. These read the installed command's own help
rather than Galley's source, for the same reason every other behavioural test does.
"""

import json
import re
from pathlib import Path

from tests.support.public_cli import run_cli

SKILL = Path("src/galley/skills/galley")
# Every command the skill names, as the argument list its own help is read through.
COMMANDS = (
    ("inspect",),
    ("prepare",),
    ("localise",),
    ("audit",),
    ("config", "validate"),
    ("inbox", "check"),
    ("device", "status"),
    ("deliver",),
    ("skill", "install"),
)
# The one flag the skill names that belongs to no subcommand.
ROOT_FLAGS = frozenset({"--version"})


def _help(*arguments: str) -> str:
    result = run_cli(*arguments, "--help", environment={"TERM": "dumb", "COLUMNS": "400"})
    assert result.returncode == 0, result.stderr
    return result.stdout


def _documented_flags() -> set[str]:
    """Collect every long option the skill and its resources name, from their Markdown."""

    flags: set[str] = set()
    for path in sorted(SKILL.rglob("*.md")):
        flags.update(re.findall(r"`(--[a-z][a-z-]+)`", path.read_text(encoding="utf-8")))
    return flags


def test_every_option_the_skill_names_exists_on_the_installed_cli() -> None:
    available = ROOT_FLAGS.union(
        *(set(re.findall(r"--[a-z-]+", _help(*command))) for command in COMMANDS)
    )
    documented = _documented_flags()

    assert documented, "the skill documents no options at all"
    assert documented <= available, sorted(documented - available)


def test_every_command_the_skill_names_is_one_the_cli_exposes() -> None:
    listed = set(re.findall(r"^.\s(\w[\w-]*)\s{2,}\w", _help(), flags=re.MULTILINE))
    named = set(
        re.findall(
            r"galley ([a-z]+(?: [a-z]+)?)",
            (SKILL / "resources/cli-contract.md").read_text(encoding="utf-8"),
        )
    )

    assert {"inspect", "prepare", "audit", "profiles", "inbox", "device", "deliver"} <= listed
    assert named, "the contract resource names no commands at all"
    assert {name.split()[0] for name in named} <= listed
    # The orchestration turns on these three, so each must resolve as its own subcommand, not
    # merely share a first word with a group the CLI happens to expose.
    for command in ("inbox check", "device status", "deliver"):
        assert command in named
        assert _help(*command.split())


def _commands(text: str) -> list[list[str]]:
    """Read every fenced shell command in one resource, joining backslash continuations."""

    blocks = re.findall(r"```\n(.*?)```", text, flags=re.DOTALL)
    return [block.replace("\\\n", " ").split() for block in blocks if block.startswith("galley ")]


def _option(command: list[str], name: str) -> str | None:
    return command[command.index(name) + 1] if name in command else None


def test_the_worked_repairs_prepare_step_does_not_own_its_own_repair_inputs() -> None:
    """`prepare` protects every file it reads from its own outputs, so a worked example whose
    evidence directory is the directory holding the Repair Inputs refuses instead of running."""

    text = (SKILL / "resources/worked-repair.md").read_text(encoding="utf-8")
    prepare = next(command for command in _commands(text) if command[1] == "prepare")
    output = _option(prepare, "--output")
    assert output is not None
    evidence = _option(prepare, "--evidence-dir") or str(Path(output).with_suffix(".galley"))
    inputs = [
        _option(prepare, name)
        for name in ("--inspection-report", "--canonical-document", "--preservation-baseline")
    ]

    assert all(inputs), "the worked example must name all three Repair Inputs"
    for supplied in inputs:
        assert Path(evidence) not in Path(str(supplied)).parents
        assert Path(evidence) != Path(str(supplied))


def test_the_localisation_sequence_localises_before_it_prepares(tmp_path: Path) -> None:
    """The documented answer to a remote-image refusal is one `localise` then one ordinary
    `prepare` from what it wrote. The three Repair Inputs must be the files localisation actually
    produces, inside the directory it was given — and `prepare` must not own that directory, or
    the documented sequence would refuse at `output-is-input` instead of building a book."""

    text = (SKILL / "resources/localisation.md").read_text(encoding="utf-8")
    commands = _commands(text)
    localise = next(command for command in commands if command[1] == "localise")
    prepare = next(command for command in commands if command[1] == "prepare")

    assert commands.index(localise) < commands.index(prepare)
    assert _option(localise, "--profile") == _option(prepare, "--profile")
    evidence = _option(localise, "--evidence-dir")
    assert evidence is not None
    inputs = {
        "--inspection-report": "report.json",
        "--canonical-document": "canonical-document.json",
        "--preservation-baseline": "preservation-baseline.txt",
    }
    for option, name in inputs.items():
        supplied = _option(prepare, option)
        assert supplied is not None, option
        assert Path(supplied) == Path(evidence) / name

    output = _option(prepare, "--output")
    assert output is not None
    owned = _option(prepare, "--evidence-dir") or str(Path(output).with_suffix(".galley"))
    assert Path(owned) != Path(evidence)
    assert Path(owned) not in Path(evidence).parents


def _run_commands() -> list[list[str]]:
    text = (SKILL / "resources/galley-my-inbox.md").read_text(encoding="utf-8")
    return _commands(text)


def test_the_inbox_run_prepares_ready_artifacts_with_the_observed_hash() -> None:
    """Routine candidates are prepared as Ready Artifacts under the Inbox Check hash, so the
    documented `prepare` step must carry both `--ready` and `--expected-source-hash` — the two
    options that make an unattended build publish only when the source has not moved."""

    prepare = [command for command in _run_commands() if command[1] == "prepare"]
    assert prepare, "the run documents no prepare step"
    for command in prepare:
        assert "--ready" in command
        assert "--expected-source-hash" in command


def test_the_inbox_run_plans_a_delivery_before_it_performs_one() -> None:
    """The run presents finite plans and stops before upload. The first `deliver` the guide shows
    reads the device with `--plan`; a bare `deliver` only appears after it, so the documented
    sequence itself cannot upload before the plans are shown."""

    delivers = [command for command in _run_commands() if command[1] == "deliver"]
    assert delivers, "the run documents no deliver step"
    assert "--plan" in delivers[0]
    assert all("--plan" not in command for command in delivers[1:])


def test_the_detailed_run_sequence_lives_in_the_resource_not_the_skill_body() -> None:
    """Detailed guidance stays in bounded resources: the runnable step-by-step command sequence
    lives in `galley-my-inbox.md`, while `SKILL.md` orchestrates and links to it rather than
    carrying the fenced walkthrough itself. (The description and prohibition budgets that keep the
    body concise are the province of the `checkskill` gate.)"""

    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert _run_commands(), "the run resource carries no fenced command sequence"
    assert not _commands(body), "detailed command sequences belong in the bounded resource"
    for resource in (
        "resources/galley-my-inbox.md",
        "resources/device-read.md",
        "resources/assessment.md",
    ):
        assert resource in body, resource


def test_the_repair_procedure_uses_each_conventions_native_target() -> None:
    """Adding a social convention must not send every matched repair to the footnote target."""

    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    procedure = " ".join(
        body[body.index("The repair procedure") : body.index("## Where a repair stays")].split()
    )

    assert "Follow the convention's target native document structure" in procedure
    assert "aim at the Recovered Footnote Apparatus" not in procedure


def test_the_authored_record_shapes_are_the_skills_and_not_the_clis() -> None:
    """The assessment and the reading record ship beside the skill, and no command emits them.

    They are the agent's and the human's artifacts. A shape sitting in `galley/schemas/` beside
    the Report and the Delivery Record would imply a writer inside the CLI, so where the file
    lives is part of the boundary, not filing.
    """

    shapes = {
        "galley/agent-assessment/1": SKILL / "resources/agent-assessment.schema.json",
        "galley/reading-record/1": SKILL / "resources/reading-record.schema.json",
    }
    packaged = {
        path.read_text(encoding="utf-8")
        for path in sorted(Path("src/galley/schemas").glob("*.json"))
    }

    for identifier, path in shapes.items():
        assert path.is_file(), path
        assert json.loads(path.read_text(encoding="utf-8"))["$id"] == identifier
        assert not any(identifier in document for document in packaged), identifier
        assert any(
            path.name in resource.read_text(encoding="utf-8")
            for resource in sorted(SKILL.rglob("*.md"))
        ), f"{path.name} is not linked from any resource"

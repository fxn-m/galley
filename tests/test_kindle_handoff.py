"""The installed Agent Skill publishes one Kindle Ready Artifact and gives it to the user."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.markdown_fixtures import PLAIN_BOOK, write_markdown
from tests.public_cli import public_cli_commands, run_command
from tests.ready_fixtures import ready_reports
from tests.skill_fixtures import isolated_home
from tests.workspace_fixtures import workspace_environment

PROFILE = "kindle-ios-personal-documents"
PROFILE_VERSION = "0.3.0"
SKILL = Path("src/galley/skills/galley")
RESOURCE = Path("resources/kindle-ios-handoff.md")


def _commands(text: str) -> list[list[str]]:
    blocks = re.findall(r"```(?:text)?\n(.*?)```", text, flags=re.DOTALL)
    return [block.replace("\\\n", " ").split() for block in blocks if block.startswith("galley ")]


def _option(command: list[str], name: str) -> str | None:
    return command[command.index(name) + 1] if name in command else None


@pytest.fixture(scope="module")
def installed_guidance(tmp_path_factory: pytest.TempPathFactory) -> tuple[tuple[str, str], ...]:
    root = tmp_path_factory.mktemp("kindle-user-handoff")
    installed: list[tuple[str, str]] = []
    for index, installer in enumerate(public_cli_commands("skill", "install")):
        target = root / f"installed-skills-{index}"
        result = run_command(
            installer,
            "--target",
            str(target),
            "--json",
            environment=isolated_home(root / f"home-{index}"),
        )
        assert (result.returncode, result.stderr) == (0, "")
        installed_skill = target / "galley" / "SKILL.md"
        installed_handoff = target / "galley" / RESOURCE
        assert installed_skill.read_bytes() == (SKILL / "SKILL.md").read_bytes()
        assert installed_handoff.read_bytes() == (SKILL / RESOURCE).read_bytes()
        installed.append(
            (
                installed_skill.read_text(encoding="utf-8"),
                installed_handoff.read_text(encoding="utf-8"),
            )
        )
    return tuple(installed)


def _json(result: Any) -> Any:
    assert (result.returncode, result.stderr) == (0, "")
    return json.loads(result.stdout)


def test_the_installed_skill_command_publishes_the_public_kindle_ready_artifact(
    tmp_path: Path, installed_guidance: tuple[tuple[str, str], ...]
) -> None:
    preparers = public_cli_commands("prepare")
    for index, ((_, handoff), preparer) in enumerate(
        zip(installed_guidance, preparers, strict=True)
    ):
        commands = _commands(handoff)
        assert len(commands) == 1
        documented = commands[0]
        assert documented[:3] == ["galley", "prepare", "SOURCE"]
        assert _option(documented, "--profile") == PROFILE
        assert {"--ready", "--json"} <= set(documented)
        assert {"--output", "--evidence-dir", "--overwrite"}.isdisjoint(documented)

        source = write_markdown(tmp_path / f"source-{index}.md", PLAIN_BOOK)
        workspace = tmp_path / f"workspace-{index}"
        environment = workspace_environment(workspace, tmp_path / f"runtime-home-{index}")
        arguments = [
            str(source) if argument == "SOURCE" else argument for argument in documented[2:]
        ]

        report = _json(run_command(preparer, *arguments, environment=environment))
        output = Path(report["artifact"]["path"])

        assert report["outcome"] == "completed"
        assert report["profile"]["id"] == PROFILE
        assert report["profile"]["profile_version"] == PROFILE_VERSION
        assert output.parent == workspace / "ready"
        assert report["artifact"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
        assert report["artifact"]["byte_size"] == {
            "basis": "measured",
            "unit": "bytes",
            "value": output.stat().st_size,
        }
        retained = ready_reports(workspace)
        assert len(retained) == 1
        assert retained[0] == report


def test_kindle_guidance_allows_authorised_transfer_and_keeps_submission_manual(
    installed_guidance: tuple[tuple[str, str], ...],
) -> None:
    for skill, handoff in installed_guidance:
        combined = " ".join(f"{skill} {handoff}".split())

        assert "user-confirmed iCloud Drive Handoff Folder" not in combined
        assert "CONFIRMED_HANDOFF_FOLDER" not in combined
        assert "By default, hand over the file in the Workspace's `ready/` directory" in combined
        assert "current request or saved customisation specifies a transfer" in combined
        assert "final checked EPUB after requested cover work is complete" in combined
        assert "Submission to Kindle remains user-controlled" in combined
        assert "exact artifact basename" in combined
        assert "preferred Send to Kindle route" in combined
        assert "Upload or share this EPUB" in combined


def test_kindle_handoff_leads_with_the_file_and_keeps_audit_fields_in_the_report(
    installed_guidance: tuple[tuple[str, str], ...],
) -> None:
    """A successful handoff is useful to a reader without serialising the technical Report."""

    for _skill, handoff in installed_guidance:
        compact = " ".join(handoff.split())

        assert "exact artifact basename as clickable text" in compact
        assert "absolute `artifact.path` as the link target" in compact
        assert "Routine success starts with “It passed Galley's checks.”" in compact
        assert "A routine handoff has no proactive **Technical report** link" in compact
        assert all(
            field in compact
            for field in (
                "`artifact.sha256`",
                "`artifact.byte_size.value`",
                "`profile.id`",
                "`profile.profile_version`",
            )
        )
        assert "in the Report unless the person asks" in compact

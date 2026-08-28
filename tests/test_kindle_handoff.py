"""The installed Agent Skill stages one Kindle Submission Artifact and stops."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tests.markdown_fixtures import PLAIN_BOOK, write_markdown
from tests.public_cli import public_cli_commands, run_command
from tests.skill_fixtures import isolated_home

PROFILE = "kindle-ios-personal-documents"
PROFILE_VERSION = "0.3.0"
RESOURCE = Path("resources/kindle-ios-handoff.md")


def _commands(text: str) -> list[list[str]]:
    blocks = re.findall(r"```(?:text)?\n(.*?)```", text, flags=re.DOTALL)
    return [block.replace("\\\n", " ").split() for block in blocks if block.startswith("galley ")]


def _option(command: list[str], name: str) -> str | None:
    return command[command.index(name) + 1] if name in command else None


def _installed_handoff_command(tmp_path: Path, index: int, installer: list[str]) -> list[str]:
    target = tmp_path / f"installed-skills-{index}"
    result = run_command(
        installer,
        "--target",
        str(target),
        "--json",
        environment=isolated_home(tmp_path / f"home-{index}"),
    )
    assert (result.returncode, result.stderr) == (0, "")
    installed = target / "galley" / RESOURCE
    assert installed.read_bytes() == (Path("src/galley/skills/galley") / RESOURCE).read_bytes()
    commands = _commands(installed.read_text(encoding="utf-8"))
    assert len(commands) == 1
    return commands[0]


def _json(result: Any) -> Any:
    assert (result.returncode, result.stderr) == (0, "")
    return json.loads(result.stdout)


def test_the_installed_skill_command_runs_the_public_kindle_handoff(tmp_path: Path) -> None:
    installers = public_cli_commands("skill", "install")
    preparers = public_cli_commands("prepare")
    for index, (installer, preparer) in enumerate(zip(installers, preparers, strict=True)):
        documented = _installed_handoff_command(tmp_path, index, installer)
        assert documented[:3] == ["galley", "prepare", "SOURCE"]
        assert _option(documented, "--profile") == PROFILE
        assert _option(documented, "--output") == "CONFIRMED_HANDOFF_FOLDER/BOOK.epub"
        assert _option(documented, "--evidence-dir") == "GALLEY_EVIDENCE/BOOK.galley"
        assert {"--json"} <= set(documented)
        assert {"--ready", "--overwrite"}.isdisjoint(documented)

        source = write_markdown(tmp_path / f"source-{index}.md", PLAIN_BOOK)
        handoff = tmp_path / f"confirmed-handoff-{index}"
        evidence_root = tmp_path / f"galley-evidence-{index}"
        handoff.mkdir()
        evidence_root.mkdir()
        output = handoff / "book.epub"
        evidence = evidence_root / "book.galley"
        replacements = {
            "SOURCE": str(source),
            "CONFIRMED_HANDOFF_FOLDER/BOOK.epub": str(output),
            "GALLEY_EVIDENCE/BOOK.galley": str(evidence),
        }
        arguments = [replacements.get(argument, argument) for argument in documented[2:]]

        report = _json(run_command(preparer, *arguments))

        assert sorted(path.name for path in handoff.iterdir()) == ["book.epub"]
        assert handoff not in evidence.parents
        assert sorted(path.name for path in evidence.iterdir()) == [
            "canonical-document.json",
            "preservation-baseline.txt",
            "report.json",
        ]
        assert json.loads((evidence / "report.json").read_text(encoding="utf-8")) == report
        assert report["outcome"] == "completed"
        assert report["profile"]["id"] == PROFILE
        assert report["profile"]["profile_version"] == PROFILE_VERSION
        assert report["artifact"]["path"] == str(output.resolve())
        assert report["artifact"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
        assert report["artifact"]["byte_size"] == {
            "basis": "measured",
            "unit": "bytes",
            "value": output.stat().st_size,
        }


def test_the_kindle_handoff_keeps_the_existing_output_refusal(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "source.md", PLAIN_BOOK)
    for index, command in enumerate(public_cli_commands("prepare")):
        handoff = tmp_path / f"confirmed-handoff-{index}"
        handoff.mkdir()
        output = handoff / "book.epub"
        existing = b"an existing submission artifact\n"
        _ = output.write_bytes(existing)
        evidence = tmp_path / f"external-evidence-{index}" / "book.galley"

        result = run_command(
            command,
            str(source),
            "--profile",
            PROFILE,
            "--output",
            str(output),
            "--evidence-dir",
            str(evidence),
            "--json",
        )

        assert (result.returncode, result.stderr) == (3, "")
        report = json.loads(result.stdout)
        assert report["refusal"]["boundary"] == "output-exists"
        assert report["refusal"]["artifact_written"] is False
        assert output.read_bytes() == existing
        assert not evidence.exists()
        assert sorted(path.name for path in handoff.iterdir()) == ["book.epub"]

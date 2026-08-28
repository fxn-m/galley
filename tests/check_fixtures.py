"""Shared helpers for the Inbox Check tests that own a Workspace with published evidence."""

import subprocess
from pathlib import Path

from tests.public_cli import public_cli_commands, run_command, run_public_cli
from tests.ready_fixtures import PROFILE, facts, report
from tests.workspace_fixtures import (
    command_document,
    entries,
    inbox_table,
    workspace_environment,
    write_configuration,
)

DERIVED = ("coverage", "candidates", "evidence_problems")
OTHER_BODY = "# Other\n\nA different body, still long enough to make an honest little book.\n"


def checked_workspace(root: Path, *tables: str) -> tuple[Path, dict[str, str]]:
    """Configure one Workspace whose Inboxes are the external directories sources sit in."""

    workspace = root / "workspace"
    configured = tables or (inbox_table("inbox", str(root / "inbox")),)
    _ = write_configuration(workspace, "version = 1\n\n" + "\n".join(configured))
    return workspace, workspace_environment(workspace, root / "home")


def publish(
    source: Path, environment: dict[str, str], *extra: str
) -> subprocess.CompletedProcess[str]:
    """Publish one Ready Artifact through a single entry point, as a reader would."""

    return run_command(
        public_cli_commands("prepare", str(source))[0],
        "--profile",
        PROFILE,
        "--ready",
        "--json",
        *extra,
        environment=environment,
    )


def checked(environment: dict[str, str]) -> dict[str, object]:
    """Check the Inboxes through both entry points, proving they derived the same facts."""

    documents = [
        command_document(result)
        for result in run_public_cli("inbox", "check", "--json", environment=environment)
    ]
    assert derived(documents[0]) == derived(documents[1])
    return documents[0]


def derived(document: dict[str, object]) -> dict[str, object]:
    """Take only the facts a check derives, leaving run identity and timing behind."""

    return {key: document[key] for key in DERIVED}


def states(environment: dict[str, str]) -> dict[str, str]:
    """Map each candidate's file name to the state one check derived for it."""

    return {
        Path(str(candidate["resolved_path"])).name: str(candidate["state"])
        for candidate in entries(checked(environment), "candidates")
    }


def candidate(document: dict[str, object], name: str) -> dict[str, object]:
    """Find one candidate by the file name it was checked under."""

    found = [
        entry
        for entry in entries(document, "candidates")
        if Path(str(entry["resolved_path"])).name == name
    ]
    assert len(found) == 1
    return found[0]


def bundles(workspace: Path) -> dict[str, Path]:
    """Map each published Report's source path to the immutable bundle holding it.

    Evidence is keyed by the whole provenance pair, so one path can own several bundles. This
    helper is for the cases that published each source once; it refuses to answer for the rest
    rather than silently returning whichever bundle happened to sort last.
    """

    found = sorted((workspace / "ready" / "evidence").glob("*/report.json"))
    sources = [
        str(facts(report(path.read_text(encoding="utf-8")), "source")["path"]) for path in found
    ]
    assert len(set(sources)) == len(sources)
    return {source: path.parent for source, path in zip(sources, found)}

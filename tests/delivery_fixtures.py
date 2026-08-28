"""Shared helpers for the Delivery tests, which publish a real Ready Artifact first."""

import json
import subprocess
from pathlib import Path
from typing import cast

from tests.public_cli import run_public_cli
from tests.ready_fixtures import COMPLETED, facts, inbox_note, prepare_ready, report
from tests.workspace_fixtures import inbox_table, workspace_environment, write_configuration

REFUSED = 3
UNCONFIRMED = 5


def published(tmp_path: Path, name: str = "note.md") -> tuple[Path, Path, dict[str, str]]:
    """Publish one Markdown source as a Ready Artifact and return the Workspace and the book."""

    source = inbox_note(tmp_path, name)
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    _ = write_configuration(
        workspace, "version = 1\n\n" + inbox_table("galley", str(source.parent))
    )
    first, _ = prepare_ready(source, environment)
    assert first.returncode == COMPLETED, first.stderr
    artifact = Path(str(facts(report(first.stdout), "artifact")["path"]))
    return workspace, artifact, environment


def deliver(
    artifact: Path, environment: dict[str, str], *arguments: str
) -> list[subprocess.CompletedProcess[str]]:
    """Run `deliver` through both public entry points with per-invocation arguments."""

    return run_public_cli("deliver", str(artifact), "--json", *arguments, environment=environment)


def plan(
    artifact: Path, environment: dict[str, str], host: str, *arguments: str
) -> list[subprocess.CompletedProcess[str]]:
    """Plan one Delivery against a pinned loopback device."""

    return deliver(artifact, environment, "--plan", "--host", host, *arguments)


def records(workspace: Path) -> list[dict[str, object]]:
    """Read every immutable Delivery Record in one Workspace, in the order they were written."""

    collection = workspace / "delivery"
    if not collection.exists():
        return []
    return [
        cast(dict[str, object], cast(object, json.loads(path.read_text(encoding="utf-8"))))
        for path in sorted(collection.glob("*.json"))
    ]

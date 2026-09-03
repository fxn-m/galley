"""Shared helpers for the Ready publication tests, which own their own Workspaces."""

import json
import subprocess
from pathlib import Path
from typing import cast

from tests.public_cli import run_cli

COMPLETED = 0
INVOCATION_ERROR = 2
REFUSED = 3
PROFILE = "x4-crosspoint"
BODY = "# Ready\n\nA short body with enough words to make an honest little book.\n"


def inbox_note(root: Path, name: str = "note.md", body: str = BODY) -> Path:
    """Place one Markdown source in an Inbox outside the Workspace, as a reader would."""

    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    source = inbox / name
    _ = source.write_text(body, encoding="utf-8")
    return source


def prepare_ready(
    source: Path, environment: dict[str, str], *extra: str
) -> subprocess.CompletedProcess[str]:
    """Publish one source as a Ready Artifact through the installed command."""

    return run_cli(
        "prepare",
        str(source),
        "--profile",
        PROFILE,
        "--ready",
        "--json",
        *extra,
        environment=environment,
    )


def report(stdout: str) -> dict[str, object]:
    """Read the canonical Report one invocation emitted on stdout."""

    document = cast(object, json.loads(stdout))
    assert isinstance(document, dict)
    return cast(dict[str, object], document)


def facts(source: dict[str, object], key: str) -> dict[str, object]:
    """Read one object-valued field of a Report."""

    value = source[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def ready_reports(workspace: Path) -> list[dict[str, object]]:
    """Read every immutable Report in one Workspace's Ready evidence collection."""

    collection = workspace / "ready" / "evidence"
    if not collection.exists():
        return []
    return [
        report(bundle.read_text(encoding="utf-8"))
        for bundle in sorted(collection.glob("*/report.json"))
    ]

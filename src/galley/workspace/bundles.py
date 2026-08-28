"""Know where a published Ready evidence bundle keeps its Report, in exactly one place.

Two questions are asked of the same collection by different commands — what does the retained
evidence say about this Inbox Candidate, and which publication produced this Ready Artifact —
and both have to agree about what a bundle looks like. The layout lives here so that changing
it cannot leave one reader scanning for something the other no longer writes.
"""

import json
from pathlib import Path
from typing import cast

from galley.json_reading import mapping
from galley.workspace.ready import STAGED_PREFIX, ReadyWorkspace

REPORT_NAME = "report.json"


def published_bundles(home: ReadyWorkspace) -> list[Path]:
    """List every published evidence bundle in stable order, reading and creating nothing.

    A staged entry is skipped because that is a bundle a publication has not finished writing:
    an incomplete bundle is not evidence of anything. The prefix comes from the module that
    stages them, so the two cannot drift apart. A Workspace that has never published at all
    simply has no collection to list.
    """

    try:
        entries = sorted(home.collection.iterdir())
    except OSError:
        return []
    return [
        entry for entry in entries if entry.is_dir() and not entry.name.startswith(STAGED_PREFIX)
    ]


def retained_document(report: Path) -> dict[str, object] | None:
    """Read one retained Report, or say it offered nothing a reader could use."""

    try:
        return mapping(cast(object, json.loads(report.read_bytes())))
    except OSError, ValueError:
        return None

"""Name the fixed roles Galley owns beneath a Workspace, and say what state each path is in.

Work, Ready and Delivery Record storage have fixed roles rather than configurable ones: they are
Galley's own, not Inbox destinations, so a configuration cannot point them anywhere. Nothing here
creates a directory — the CLI never writes configuration or the tree it describes — so an absent
location is reported as absent and left for the Setup Skill to create.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from galley.locations import display_path

Role = Literal["work", "ready", "delivery"]

WORK: Role = "work"
READY: Role = "ready"
DELIVERY: Role = "delivery"
EVIDENCE = "evidence"
LAYOUT_STAGE = "workspace-layout"

PathState = Literal["usable", "absent", "not-a-directory", "unreadable", "unwritable"]


@dataclass(frozen=True)
class OwnedLocation:
    """One Galley-owned directory beneath a Workspace, and the state its path is in."""

    role: Role
    path: Path
    state: PathState

    def facts(self) -> dict[str, object]:
        """Report the resolved location and whether an existing path is usable for its role."""

        return {"role": self.role, "path": display_path(self.path), "state": self.state}


def work_directory(workspace: Path) -> Path:
    """Name where a refused attempt's evidence is retained, keyed by source provenance."""

    return workspace / WORK


def ready_directory(workspace: Path) -> Path:
    """Name where immutable Ready Artifacts are published."""

    return workspace / READY


def ready_evidence_directory(workspace: Path) -> Path:
    """Name the Ready evidence collection, keyed independently of any artifact filename."""

    return ready_directory(workspace) / EVIDENCE


def delivery_directory(workspace: Path) -> Path:
    """Name where immutable Delivery Records are written."""

    return workspace / DELIVERY


def owned_locations(workspace: Path) -> tuple[OwnedLocation, ...]:
    """Describe every Galley-owned location beneath one Workspace, in a fixed order."""

    return tuple(
        OwnedLocation(role, path, directory_state(path, writable=True))
        for role, path in _owned(workspace)
    )


def _owned(workspace: Path) -> tuple[tuple[Role, Path], ...]:
    return (
        (WORK, work_directory(workspace)),
        (READY, ready_directory(workspace)),
        (DELIVERY, delivery_directory(workspace)),
    )


def directory_state(path: Path, *, writable: bool = False) -> PathState:
    """Say what state one directory is in, without listing a single entry inside it.

    An Inbox is only ever read, so it is asked for read and traverse access and nothing more.
    A Galley-owned location is also asked for write access, because a run that cannot publish
    there should say so while the answer is still cheap.
    """

    if not path.exists():
        return "absent"
    if not path.is_dir():
        return "not-a-directory"
    if not os.access(path, os.R_OK | os.X_OK):
        return "unreadable"
    if writable and not os.access(path, os.W_OK):
        return "unwritable"
    return "usable"

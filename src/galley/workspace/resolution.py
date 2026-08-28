"""Resolve the Galley Workspace the one way every Workspace-aware command resolves it.

The precedence is fixed and short — an explicit option, then `GALLEY_HOME`, then the visible
default under the user's Documents directory — and the current directory and its parents are
never searched. That last part is the point: a Workspace found by walking upwards would make an
`inbox check` run from inside a repository check whatever that repository happened to contain.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from galley.locations import display_path, resolved

WORKSPACE_VARIABLE = "GALLEY_HOME"
DOCUMENTS_DIRECTORY = "Documents"
DEFAULT_DIRECTORY = "Galley"
CONFIGURATION_NAME = "galley.toml"
RESOLUTION_STAGE = "workspace-resolution"

WorkspaceSource = Literal["option", "environment", "default"]


@dataclass(frozen=True)
class Workspace:
    """One resolved Galley Workspace and the precedence step that chose it."""

    source: WorkspaceSource
    path: Path

    @property
    def configuration(self) -> Path:
        """Name the visible Workspace Configuration file this Workspace owns."""

        return self.path / CONFIGURATION_NAME

    def facts(self) -> dict[str, object]:
        """Describe where this Workspace came from, before anything inside it is read."""

        return {
            "source": self.source,
            "path": display_path(self.path),
            "configuration_path": display_path(self.configuration),
        }


def resolve_workspace(chosen: Path | None) -> Workspace:
    """Choose the Galley Workspace from the option, the environment, or the visible default."""

    if chosen is not None:
        return Workspace("option", resolved(chosen.expanduser()))
    named = os.environ.get(WORKSPACE_VARIABLE)
    if named:
        return Workspace("environment", resolved(Path(named).expanduser()))
    return Workspace("default", resolved(default_workspace()))


def default_workspace() -> Path:
    """Name the visible default Galley Workspace under the user's Documents directory."""

    return Path.home() / DOCUMENTS_DIRECTORY / DEFAULT_DIRECTORY

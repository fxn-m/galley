"""Build isolated Galley Workspaces for the Workspace-aware public commands.

Every Workspace test owns its own tree under `tmp_path` and selects it through `GALLEY_HOME` or
`--workspace`. `HOME` is redirected too, so a test that exercises the default precedence cannot
reach — or create anything in — the developer's real Documents directory.
"""

import json
import subprocess
from pathlib import Path
from typing import cast

CONFIGURATION_NAME = "galley.toml"
OWNED_DIRECTORIES = ("work", "ready", "delivery")


def isolated_home(home: Path) -> dict[str, str]:
    """Select a throwaway home directory, so the default Workspace is never the real one."""

    home.mkdir(parents=True, exist_ok=True)
    return {"HOME": str(home), "GALLEY_HOME": ""}


def workspace_environment(workspace: Path, home: Path) -> dict[str, str]:
    """Select one Workspace through `GALLEY_HOME`, from an isolated home directory."""

    return {**isolated_home(home), "GALLEY_HOME": str(workspace)}


def inbox_table(name: str, path: str, *, recursive: bool = False) -> str:
    """Write one `[[inbox]]` table exactly as the Setup Skill would author it."""

    recursion = "true" if recursive else "false"
    return f'[[inbox]]\nname = "{name}"\npath = "{path}"\nrecursive = {recursion}\n'


def write_configuration(workspace: Path, body: str) -> Path:
    """Place one Workspace Configuration in a Workspace, creating the Workspace itself."""

    workspace.mkdir(parents=True, exist_ok=True)
    configuration = workspace / CONFIGURATION_NAME
    _ = configuration.write_text(body, encoding="utf-8")
    return configuration


def valid_workspace(workspace: Path, *, owned: bool = True) -> Path:
    """Build the smallest complete Workspace: one relative Inbox and the owned directories."""

    (workspace / "inbox").mkdir(parents=True, exist_ok=True)
    if owned:
        for name in OWNED_DIRECTORIES:
            (workspace / name).mkdir(parents=True, exist_ok=True)
    return write_configuration(workspace, "version = 1\n\n" + inbox_table("galley", "inbox"))


def tree(root: Path) -> dict[str, int]:
    """Snapshot every path beneath one directory, so a read-only command can be proven so."""

    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.stat().st_size if path.is_file() else -1
        for path in sorted(root.rglob("*"))
    }


def command_document(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    """Read the versioned command document one invocation emitted on stdout."""

    document = cast(object, json.loads(result.stdout))
    assert isinstance(document, dict)
    return cast(dict[str, object], document)


def field(document: dict[str, object], key: str) -> dict[str, object]:
    """Read one object-valued field of a command document."""

    value = document[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def entries(document: dict[str, object], key: str) -> list[dict[str, object]]:
    """Read one array-valued field of a command document."""

    values = document[key]
    assert isinstance(values, list)
    return [cast(dict[str, object], value) for value in cast(list[object], values)]

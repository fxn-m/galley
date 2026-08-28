"""Resolve where skills are installed, and say what Galley finds already occupying that name.

The default is the standard user `.agents/skills` location. An explicit target exists so that
installation behaviour and discovery layout can be exercised without touching a real user
profile — every test in this repository installs into one.

Reading a destination is the whole of the safety story. Four states are distinguished because
each earns a different answer: nothing there may be written; an exact match of Galley's own
manifest may be left alone or replaced; a destination whose files no longer match that manifest,
or which carries no manifest Galley can read, is a conflict a person has to authorise, because
neither one can be attributed to a Galley installation.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from galley.digests import file_digest
from galley.installation.manifest import (
    MANIFEST_NAME,
    ManifestEntry,
    SkillManifest,
    read_manifest,
)
from galley.locations import display_path, resolved

DEFAULT_TARGET_PARTS = (".agents", "skills")
TARGET_STAGE = "skill-target"
DESTINATION_STAGE = "skill-destination"

TargetSource = Literal["option", "default"]
DestinationState = Literal["absent", "managed", "modified", "foreign"]


@dataclass(frozen=True)
class SkillTarget:
    """One resolved skills directory, and the precedence step that chose it."""

    source: TargetSource
    path: Path

    def facts(self) -> dict[str, object]:
        """Describe the target before anything inside it is read."""

        return {"source": self.source, "path": display_path(self.path)}

    def destination(self, name: str) -> Path:
        """Name the one directory inside the target that belongs to one skill."""

        return self.path / name


@dataclass(frozen=True)
class Destination:
    """What Galley found at one skill's place in the target, and why it reads that way."""

    name: str
    path: Path
    state: DestinationState
    manifest: SkillManifest | None
    present: tuple[ManifestEntry, ...]

    def facts(self) -> dict[str, object]:
        """Report the destination's own state, separately from what the command did about it.

        `differences` names every path that stops this destination from being the installation its
        own manifest describes. It is reported whether or not the command refuses, so a forced run
        states in its own document which conflict force was used to overrule.
        """

        return {
            "path": display_path(self.path),
            "state": self.state,
            "manifest": None if self.manifest is None else self.manifest.facts(),
            "differences": list(differences(self)),
        }


def resolve_target(chosen: Path | None) -> SkillTarget:
    """Choose the skills directory from the explicit option or the standard user location."""

    if chosen is not None:
        return SkillTarget("option", resolved(chosen.expanduser()))
    return SkillTarget("default", resolved(default_target()))


def default_target() -> Path:
    """Name the standard user skills location Galley installs into by default."""

    return Path.home().joinpath(*DEFAULT_TARGET_PARTS)


def inspect_destination(target: SkillTarget, name: str) -> Destination:
    """Decide which of the four states one skill's destination is in, reading nothing else."""

    path = target.destination(name)
    if not path.exists():
        return Destination(name, path, "absent", None, ())
    if not path.is_dir() or path.is_symlink():
        return Destination(name, path, "foreign", None, ())
    manifest = read_manifest(path)
    present = _present(path)
    if manifest is None:
        return Destination(name, path, "foreign", None, present)
    state: DestinationState = (
        "managed" if _digests(present) == _digests(manifest.entries) else "modified"
    )
    return Destination(name, path, state, manifest, present)


def _digests(entries: tuple[ManifestEntry, ...]) -> dict[str, str]:
    return {entry.path: entry.sha256 for entry in entries}


def differences(destination: Destination) -> tuple[str, ...]:
    """Name every path that stops a managed destination from matching its own manifest."""

    manifest = destination.manifest
    if manifest is None:
        return tuple(entry.path for entry in destination.present)
    recorded = _digests(manifest.entries)
    found = _digests(destination.present)
    return tuple(sorted(set(recorded) ^ set(found) | _changed(recorded, found)))


def _changed(recorded: dict[str, str], found: dict[str, str]) -> set[str]:
    return {path for path, digest in found.items() if path in recorded and recorded[path] != digest}


def _present(directory: Path) -> tuple[ManifestEntry, ...]:
    """Measure everything inside a destination except the manifest that speaks for them."""

    collected: list[ManifestEntry] = []
    _collect(directory, "", collected)
    return tuple(sorted(collected, key=lambda entry: entry.path))


def _collect(directory: Path, prefix: str, collected: list[ManifestEntry]) -> None:
    """Walk one destination without following a symlink out of it.

    A symlink is recorded with an empty digest rather than being followed or skipped. No SHA-256
    is empty, so it can never match a manifest entry, which is the answer that matters: a link
    Galley did not place is a local change, and an upgrade has to stop rather than replace a
    directory it cannot fully account for.
    """

    try:
        children = sorted(directory.iterdir())
    except OSError:
        collected.append(ManifestEntry(prefix or ".", "", -1))
        return
    for child in children:
        relative = f"{prefix}{child.name}"
        if child.is_symlink():
            collected.append(ManifestEntry(relative, "", -1))
        elif child.is_dir():
            _collect(child, f"{relative}/", collected)
        elif relative != MANIFEST_NAME:
            collected.append(_measured(relative, child))


def _measured(relative: str, path: Path) -> ManifestEntry:
    """Measure one file, treating anything unreadable as a difference rather than an error."""

    try:
        return ManifestEntry(relative, file_digest(path), path.stat().st_size)
    except OSError:
        return ManifestEntry(relative, "", -1)


def target_state(path: Path) -> str:
    """Say whether one target directory can be used, without listing a single entry in it."""

    if not path.exists():
        return "absent"
    if not path.is_dir():
        return "not-a-directory"
    if not os.access(path, os.R_OK | os.X_OK):
        return "unreadable"
    if not os.access(path, os.W_OK):
        return "unwritable"
    return "usable"

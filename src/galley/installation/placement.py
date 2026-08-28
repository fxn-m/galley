"""Put one skill directory in place, or leave the destination exactly as it was.

A directory cannot be replaced by a single atomic operation the way a file can, so atomicity here
means the narrower thing that is actually achievable and actually matters: the destination is
never a half-written tree. The complete new tree is built in a hidden sibling and only then moved
into place, an existing destination is moved aside first and removed only once the new one has
landed, and a failure part-way through puts the old one back.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from galley.digests import file_digest
from galley.installation.manifest import MANIFEST_NAME, SkillManifest, manifest_bytes
from galley.installation.packaged import PackagedSkill

STAGING_PREFIX = ".galley-staged-"
RETIRED_PREFIX = ".galley-replaced-"


@dataclass(frozen=True)
class PlacementFailure:
    """Why one skill could not be put in place, with the destination left as it was."""

    skill: str
    detail: str


def place_skill(
    destination: Path, skill: PackagedSkill, manifest: SkillManifest
) -> PlacementFailure | None:
    """Write one complete skill tree into its destination, replacing whatever was there."""

    staged = _sibling(destination, STAGING_PREFIX)
    try:
        _build(staged, skill, manifest)
    except OSError as error:
        _discard(staged)
        return PlacementFailure(skill.name, str(error))
    return _swap(destination, staged, skill.name)


def _swap(destination: Path, staged: Path, name: str) -> PlacementFailure | None:
    """Move the staged tree in, keeping the old one until the new one has landed."""

    retired = _sibling(destination, RETIRED_PREFIX) if destination.exists() else None
    try:
        if retired is not None:
            destination.rename(retired)
        try:
            staged.rename(destination)
        except OSError:
            if retired is not None:
                retired.rename(destination)
            raise
    except OSError as error:
        _discard(staged)
        return PlacementFailure(name, str(error))
    if retired is not None:
        _discard(retired)
    return None


def _build(staged: Path, skill: PackagedSkill, manifest: SkillManifest) -> None:
    """Materialise the whole tree, manifest last, so a crash leaves no attributable install."""

    staged.mkdir(parents=True)
    for file in skill.files:
        path = staged.joinpath(*file.path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(file.data)
    _ = (staged / MANIFEST_NAME).write_bytes(manifest_bytes(manifest))


def remove_matching(destination: Path, manifest: SkillManifest) -> tuple[list[str], list[str]]:
    """Remove only the files whose bytes are still the ones this manifest recorded.

    Anything else stays, whether it was edited, added or belongs to somebody else, and is
    reported. Force does not appear here at all: authorising a replacement of Galley's own
    directory is a different act from authorising the deletion of a file Galley cannot attribute
    to itself, and no option in this release grants the second.
    """

    removed: list[str] = []
    retained: list[str] = []
    for entry in manifest.entries:
        path = destination.joinpath(*entry.path.split("/"))
        try:
            if path.is_file() and not path.is_symlink() and file_digest(path) == entry.sha256:
                path.unlink()
                removed.append(entry.path)
            elif path.exists() or path.is_symlink():
                retained.append(entry.path)
        except OSError:
            retained.append(entry.path)
    return removed, retained


def prune(destination: Path) -> bool:
    """Remove the manifest and every directory this installation emptied, deepest first."""

    try:
        (destination / MANIFEST_NAME).unlink(missing_ok=True)
    except OSError:
        return False
    for directory in sorted(_directories(destination), key=lambda path: -len(path.parts)):
        _remove_empty(directory)
    return _remove_empty(destination)


def _directories(destination: Path) -> list[Path]:
    try:
        return [path for path in destination.rglob("*") if path.is_dir() and not path.is_symlink()]
    except OSError:
        return []


def _remove_empty(directory: Path) -> bool:
    try:
        directory.rmdir()
    except OSError:
        return False
    return True


def _sibling(destination: Path, prefix: str) -> Path:
    return destination.parent / f"{prefix}{destination.name}-{uuid4().hex[:12]}"


def _discard(path: Path) -> None:
    """Leave no staging or retired tree behind, whatever the outcome was."""

    shutil.rmtree(path, ignore_errors=True)

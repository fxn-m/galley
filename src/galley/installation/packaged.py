"""Read the two Agent Skill trees Galley ships inside its own importable package.

The skills are package data beside `data/` and `schemas/` rather than build-backend data, so one
`importlib.resources` path serves a checkout and an installed wheel alike. That matters more here
than anywhere else: a source-tree fallback would be a second place an installed CLI could read
its product surface from, and the version it required could then disagree with the version it is.
"""

from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

SKILLS_DIRECTORY = "skills"
SKILL_NAMES = ("galley", "galley-setup")


@dataclass(frozen=True)
class PackagedFile:
    """One file of one packaged skill, addressed by its path relative to the skill directory."""

    path: str
    data: bytes


@dataclass(frozen=True)
class PackagedSkill:
    """One complete packaged skill tree, in stable path order."""

    name: str
    files: tuple[PackagedFile, ...]


def packaged_root() -> Traversable:
    """Locate the packaged skill trees inside the installed `galley` package."""

    return files("galley").joinpath(SKILLS_DIRECTORY)


def packaged_root_path() -> str:
    """Name where the packaged skills were read from, so an install can be traced to bytes."""

    return str(packaged_root())


def packaged_skills() -> tuple[PackagedSkill, ...]:
    """Read every skill this release ships, in the fixed order it names them."""

    root = packaged_root()
    return tuple(PackagedSkill(name, _tree(root.joinpath(name))) for name in SKILL_NAMES)


def _tree(skill: Traversable) -> tuple[PackagedFile, ...]:
    """Read one skill directory depth-first, sorted, so the file order never varies."""

    return tuple(sorted(_walk(skill, ""), key=lambda entry: entry.path))


def _walk(directory: Traversable, prefix: str) -> list[PackagedFile]:
    collected: list[PackagedFile] = []
    for child in sorted(directory.iterdir(), key=lambda entry: entry.name):
        relative = f"{prefix}{child.name}"
        if child.is_dir():
            collected += _walk(child, f"{relative}/")
        else:
            collected.append(PackagedFile(relative, child.read_bytes()))
    return collected

"""Validate Galley's Agent Skill source tree and instruction budgets."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import cast

import yaml

from galley import __version__
from galley.digests import bytes_digest
from galley.installation.manifest import MANIFEST_NAME, SkillManifest, manifest_for
from galley.installation.packaged import packaged_root_path, packaged_skills

MAX_DESCRIPTION_WORDS = 50
MAX_PROHIBITIONS = 5
FRONTMATTER_FIELDS = {"name", "description"}
PROHIBITION_PHRASES = ("do not", "don't", "never", "must not", "may not")
# Galley ships exactly two Agent Skills, and both are product surfaces the CLI installs and
# removes by name. A third would be shipped without a lifecycle; a missing one would leave that
# supported CLI lifecycle incomplete.
REQUIRED_SKILLS = ("galley", "galley-setup")
# The skills ship as package data inside the importable package, so one path serves both the
# checkout and an installed wheel and no source-tree fallback exists to go stale.
SKILL_ROOT = "src/galley/skills"


def validate_skills(root: Path, *, required: Sequence[str] = REQUIRED_SKILLS) -> list[str]:
    """Return deterministic validation errors for every skill below ``root``."""

    if not root.is_dir():
        return [f"{root}: skill root does not exist"]

    errors: list[str] = []
    children = sorted(root.iterdir())
    for child in children:
        if not child.is_dir() or child.is_symlink():
            errors.append(f"{child.name}: expected one directory per skill")
            continue
        errors.extend(_validate_skill(root, child))
    return errors + _shipped_set(root, children, required)


def _shipped_set(root: Path, children: list[Path], required: Sequence[str]) -> list[str]:
    """Hold the skill root to exactly the skills this release ships, named."""

    present = {child.name for child in children if child.is_dir() and not child.is_symlink()}
    expected = set(required)
    return [
        *(f"{root}/{name}: required skill is missing" for name in sorted(expected - present)),
        *(f"{root}/{name}: unexpected skill directory" for name in sorted(present - expected)),
    ]


def validate_packaged_manifests(root: Path) -> list[str]:
    """Prove the manifest an installation writes accounts for exactly the packaged tree.

    The manifest is built at install time rather than shipped, so what has to be gated is the
    builder rather than a checked-in file: every file in the tree is named once, every hash is the
    hash of the bytes on disk, and the version recorded is the version of the CLI that would place
    it. A manifest committed into the source tree is refused outright, because it could only ever
    be a stale copy of what the installer computes.
    """

    errors: list[str] = []
    packaged = Path(packaged_root_path())
    if packaged.resolve() != root.resolve():
        return [f"{root}: the packaged skills are read from {packaged}, not from here"]
    for skill in packaged_skills():
        manifest = manifest_for(skill)
        label = f"{skill.name}/{MANIFEST_NAME}"
        if manifest.galley_version != __version__:
            errors.append(f"{label}: records version {manifest.galley_version}, not {__version__}")
        found = _tree_paths(root / skill.name)
        named = set(manifest.paths)
        errors += [
            f"{skill.name}/{path}: packaged file is missing from the manifest"
            for path in sorted(found - named)
        ]
        errors += [
            f"{skill.name}/{path}: manifest names a file the package does not carry"
            for path in sorted(named - found)
        ]
        errors += _hash_errors(root / skill.name, manifest)
        if MANIFEST_NAME in found:
            errors.append(f"{label}: a manifest committed to the source tree is always stale")
    return errors


def _tree_paths(skill: Path) -> set[str]:
    """Every file in one source skill tree, by path relative to the skill directory."""

    return {
        path.relative_to(skill).as_posix()
        for path in skill.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _hash_errors(skill: Path, manifest: SkillManifest) -> list[str]:
    """Hold every manifest entry to the bytes and length of the file it names."""

    errors: list[str] = []
    for entry in manifest.entries:
        path = skill.joinpath(*entry.path.split("/"))
        if not path.is_file():
            continue
        data = path.read_bytes()
        if bytes_digest(data) != entry.sha256 or len(data) != entry.byte_size:
            errors.append(f"{skill.name}/{entry.path}: manifest hash or size does not match")
    return errors


def _validate_skill(root: Path, skill: Path) -> list[str]:
    errors: list[str] = []
    relative = skill.relative_to(root)
    skill_file = skill / "SKILL.md"
    if not skill_file.is_file() or skill_file.is_symlink():
        return [f"{relative}/SKILL.md: required regular file is missing"]

    for child in sorted(skill.iterdir()):
        if child.name not in {"SKILL.md", "resources"}:
            errors.append(f"{relative}/{child.name}: unexpected skill entry")
        if child.name == "resources" and (not child.is_dir() or child.is_symlink()):
            errors.append(f"{relative}/resources: expected a regular directory")

    text = skill_file.read_text(encoding="utf-8")
    parsed = _parse_frontmatter(text)
    label = f"{relative}/SKILL.md"
    if isinstance(parsed, str):
        errors.append(f"{label}: {parsed}")
        return errors
    frontmatter, body = parsed

    missing = sorted(FRONTMATTER_FIELDS - frontmatter.keys())
    unexpected = sorted(frontmatter.keys() - FRONTMATTER_FIELDS)
    if missing:
        errors.append(f"{label}: missing frontmatter fields: {', '.join(missing)}")
    if unexpected:
        errors.append(f"{label}: unexpected frontmatter fields: {', '.join(unexpected)}")

    name = frontmatter.get("name")
    if name != skill.name:
        errors.append(f"{label}: name must match directory {skill.name!r}")

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{label}: description must be a non-empty string")
    else:
        word_count = len(description.split())
        if word_count > MAX_DESCRIPTION_WORDS:
            errors.append(
                f"{label}: description has {word_count} words; maximum is {MAX_DESCRIPTION_WORDS}"
            )

    lowered = body.casefold()
    prohibition_count = sum(lowered.count(phrase) for phrase in PROHIBITION_PHRASES)
    if prohibition_count > MAX_PROHIBITIONS:
        errors.append(
            f"{label}: body has {prohibition_count} prohibition phrases; "
            f"maximum is {MAX_PROHIBITIONS}"
        )

    for resource in _linked_resources(body):
        if resource.is_absolute() or ".." in resource.parts:
            errors.append(f"{label}: unsafe linked resource: {resource}")
        elif not (skill / Path(*resource.parts)).is_file():
            errors.append(f"{label}: linked resource does not exist: {resource}")
    return errors


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str] | str:
    if not text.startswith("---\n"):
        return "missing YAML frontmatter"
    end = text.find("\n---\n", 4)
    if end == -1:
        return "unterminated YAML frontmatter"
    raw = cast(object, yaml.safe_load(text[4:end]))
    if not isinstance(raw, dict):
        return "frontmatter must be a string-keyed mapping"
    mapping = cast(dict[object, object], raw)
    if not all(isinstance(key, str) for key in mapping):
        return "frontmatter must be a string-keyed mapping"
    frontmatter = cast(dict[str, object], mapping)
    return frontmatter, text[end + 5 :]


def _linked_resources(body: str) -> list[PurePosixPath]:
    resources: list[PurePosixPath] = []
    marker = "](resources/"
    offset = 0
    while (start := body.find(marker, offset)) != -1:
        target_start = start + 2
        target_end = body.find(")", target_start)
        if target_end == -1:
            break
        target = body[target_start:target_end].split("#", 1)[0]
        resources.append(PurePosixPath(target))
        offset = target_end + 1
    return resources


def main() -> int:
    """Validate a skill tree from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(SKILL_ROOT))
    args = parser.parse_args()
    root = cast(Path, args.root)
    errors = validate_skills(root) + validate_packaged_manifests(root)
    for error in errors:
        print(f"checkskill: {error}")
    if errors:
        return 1
    print(f"checkskill: OK ({len(list(root.iterdir()))} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

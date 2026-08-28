"""The Galley-managed manifest: which files one installed skill is, and what they hashed to.

The manifest is built from the packaged tree and written into the target, rather than shipped
inside the source tree. A shipped one would have to be regenerated whenever any skill file
changed, and a stale copy would claim hashes the distribution never had; built at install time it
cannot disagree with the bytes it was built from, and the version it records is by construction
the version of the CLI that placed it.

Reading one back is deliberately strict and deliberately quiet: anything Galley cannot parse as
its own manifest is treated as no manifest at all, which makes the destination foreign and makes
the next install refuse rather than overwrite. Failing towards "not mine" is the only safe
direction for a file in somebody else's directory.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from galley import __version__
from galley.digests import bytes_digest
from galley.installation.packaged import PackagedSkill
from galley.json_reading import integer, mapping, sequence, text

MANIFEST_SCHEMA = "galley/skill-manifest/1"
MANIFEST_NAME = ".galley-manifest.json"


@dataclass(frozen=True)
class ManifestEntry:
    """One file the manifest speaks for, by path relative to the skill directory."""

    path: str
    sha256: str
    byte_size: int

    def facts(self) -> dict[str, object]:
        """State the entry as it is written and as it is reported."""

        return {"path": self.path, "sha256": self.sha256, "byte_size": self.byte_size}


@dataclass(frozen=True)
class SkillManifest:
    """Everything one installed skill directory claims about itself."""

    skill: str
    galley_version: str
    entries: tuple[ManifestEntry, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        """List the relative paths this manifest speaks for, in stable order."""

        return tuple(entry.path for entry in self.entries)

    def digest_of(self, path: str) -> str | None:
        """Return the hash this manifest recorded for one relative path, if it named it."""

        return next((entry.sha256 for entry in self.entries if entry.path == path), None)

    def facts(self) -> dict[str, object]:
        """Summarise the manifest for a reader, without restating every hash twice."""

        return {"galley_version": self.galley_version, "files": len(self.entries)}

    def document(self) -> dict[str, object]:
        """Build the exact object written into the target as `.galley-manifest.json`."""

        return {
            "schema": MANIFEST_SCHEMA,
            "skill": self.skill,
            "galley_version": self.galley_version,
            "files": [entry.facts() for entry in self.entries],
        }


def reported(entries: tuple[ManifestEntry, ...], action: str) -> list[dict[str, object]]:
    """Report a run of entries under one disposition, which is the only way files are reported."""

    return [{**entry.facts(), "action": action} for entry in entries]


def manifest_for(skill: PackagedSkill) -> SkillManifest:
    """Build the manifest that describes one packaged skill as it would be installed."""

    return SkillManifest(
        skill.name,
        __version__,
        tuple(
            ManifestEntry(file.path, bytes_digest(file.data), len(file.data))
            for file in skill.files
        ),
    )


def manifest_bytes(manifest: SkillManifest) -> bytes:
    """Serialize one manifest the one stable way it is written."""

    return (json.dumps(manifest.document(), indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_manifest(directory: Path) -> SkillManifest | None:
    """Read the manifest one installed skill directory carries, or nothing Galley can trust."""

    try:
        raw = cast(object, json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8")))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    stated = mapping(raw)
    if text(stated.get("schema")) != MANIFEST_SCHEMA:
        return None
    skill = text(stated.get("skill"))
    version = text(stated.get("galley_version"))
    entries = _entries(stated.get("files"))
    if not skill or not version or entries is None:
        return None
    return SkillManifest(skill, version, entries)


def _entries(value: object) -> tuple[ManifestEntry, ...] | None:
    """Read the file list, rejecting the whole manifest rather than part of one."""

    collected: list[ManifestEntry] = []
    for stated in sequence(value):
        entry = mapping(stated)
        path = text(entry.get("path"))
        digest = text(entry.get("sha256"))
        size = integer(entry.get("byte_size"))
        if not path or not digest or size is None or size < 0:
            return None
        collected.append(ManifestEntry(path, digest, size))
    return tuple(collected)

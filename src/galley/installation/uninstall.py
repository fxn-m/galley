"""Remove what Galley installed, and only what Galley installed.

Uninstall is the asymmetric half of the lifecycle. Install can be forced, because replacing
Galley's own product surface with the packaged one is a decision a person can make; removal
cannot, because a file whose bytes are no longer the ones the manifest recorded is somebody's
work. So every file is checked against its recorded hash before it is unlinked, anything else is
retained and reported, and no option in this release authorises otherwise. The manifest is
removed either way: once its files are gone it would claim an installation that no longer exists,
and whatever is left behind is then plainly foreign to the next install.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from galley import __version__
from galley.documents import (
    SKILL_INSTALLATION_SCHEMA,
    CommandDocument,
    command_document,
    with_facts,
    with_refusal,
)
from galley.installation.manifest import ManifestEntry, reported
from galley.installation.packaged import SKILL_NAMES, packaged_root_path
from galley.installation.placement import prune, remove_matching
from galley.installation.refusals import InstallationRefusal
from galley.installation.target import (
    TARGET_STAGE,
    Destination,
    SkillTarget,
    inspect_destination,
    resolve_target,
    target_state,
)
from galley.locations import display_path
from galley.report.envelope import ReportRun

COMMAND = "skill uninstall"

RemovalAction = Literal["removed", "retained", "unchanged"]


@dataclass(frozen=True)
class Removal:
    """What one destination was, and what removal did about it."""

    destination: Destination
    action: RemovalAction
    files: list[dict[str, object]]

    def facts(self) -> dict[str, object]:
        """Report the state observed before removal beside the action taken."""

        return {
            "name": self.destination.name,
            **self.destination.facts(),
            "action": self.action,
            "files": self.files,
        }


def uninstall_skills(chosen: Path | None, *, run: ReportRun) -> CommandDocument:
    """Remove both managed skill installations, retaining everything Galley cannot claim."""

    target = resolve_target(chosen)
    document = command_document(
        COMMAND,
        SKILL_INSTALLATION_SCHEMA,
        run,
        {
            "source": {
                "galley_version": __version__,
                "path": packaged_root_path(),
                "skills": list(SKILL_NAMES),
            },
            "target": target.facts(),
            "skills": [],
        },
    )
    state = target_state(target.path)
    if state in ("not-a-directory", "unreadable"):
        return with_refusal(document, _unusable(target, state))
    return with_facts(
        document, {"skills": [_removed(target, name).facts() for name in SKILL_NAMES]}
    )


def _removed(target: SkillTarget, name: str) -> Removal:
    """Remove one skill's managed files, or leave the destination exactly as it was."""

    destination = inspect_destination(target, name)
    manifest = destination.manifest
    if destination.state == "absent":
        return Removal(destination, "unchanged", [])
    if manifest is None:
        return Removal(destination, "retained", _retained(destination))
    removed, retained = remove_matching(destination.path, manifest)
    emptied = prune(destination.path)
    untracked = tuple(
        entry for entry in destination.present if entry.path not in set(manifest.paths)
    )
    files = [
        *reported(_named(manifest.entries, removed), "removed"),
        *reported(_named(manifest.entries, retained), "retained"),
        *reported(untracked, "retained"),
    ]
    return Removal(destination, "removed" if emptied else "retained", files)


def _named(entries: tuple[ManifestEntry, ...], paths: list[str]) -> tuple[ManifestEntry, ...]:
    """Select the manifest entries one removal pass reported, keeping the manifest's own order."""

    return tuple(entry for entry in entries if entry.path in set(paths))


def _retained(destination: Destination) -> list[dict[str, object]]:
    """Report every file at a destination Galley cannot attribute to an installation of its own."""

    return reported(destination.present, "retained")


def _unusable(target: SkillTarget, detail: str) -> InstallationRefusal:
    return InstallationRefusal(
        boundary="skill-target-unusable",
        stage=TARGET_STAGE,
        summary=f"the skill target cannot be read as a directory: {display_path(target.path)}",
        fact={"path": display_path(target.path), "detail": detail},
    )

"""Install both version-matched Agent Skills into one discoverable target.

The order is the point. Every destination is read before anything is written, so a conflict
refuses having changed nothing; the target is then proved writable before the first byte is
placed; and only then is each skill materialised. Explicit force replaces the two named skill
directories and nothing else in the target — it is permission to overwrite Galley's own product
surface, never permission to tidy somebody else's directory.
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
from galley.installation.manifest import SkillManifest, manifest_for, reported
from galley.installation.packaged import PackagedSkill, packaged_root_path, packaged_skills
from galley.installation.placement import place_skill
from galley.installation.refusals import InstallationRefusal
from galley.installation.target import (
    DESTINATION_STAGE,
    TARGET_STAGE,
    Destination,
    SkillTarget,
    inspect_destination,
    resolve_target,
    target_state,
)
from galley.locations import display_path
from galley.report.envelope import ReportRun

COMMAND = "skill install"
PLACEMENT_STAGE = "skill-placement"
CONFLICTING_STATES = ("foreign", "modified")

InstallAction = Literal["installed", "upgraded", "replaced", "unchanged", "skipped"]


@dataclass(frozen=True)
class Placement:
    """One skill's destination, the packaged tree for it, and what will happen to it."""

    skill: PackagedSkill
    manifest: SkillManifest
    destination: Destination
    action: InstallAction

    def facts(self, action: InstallAction | None = None) -> dict[str, object]:
        """Report the destination as observed and the action actually taken there."""

        taken = self.action if action is None else action
        return {
            "name": self.skill.name,
            **self.destination.facts(),
            "action": taken,
            "files": _file_facts(self, taken),
        }


def install_skills(chosen: Path | None, *, force: bool, run: ReportRun) -> CommandDocument:
    """Install both packaged skills, or refuse without touching the target."""

    target = resolve_target(chosen)
    placements = _planned(target, force=force)
    document = _document(target, placements, run)
    conflicts = [placement for placement in placements if _conflicting(placement, force=force)]
    if conflicts:
        return with_refusal(_skipped(document, placements), _conflict(conflicts, force=force))
    unusable = _prepared(target)
    if unusable is not None:
        return with_refusal(_skipped(document, placements), unusable)
    return _placed(document, placements)


def _planned(target: SkillTarget, *, force: bool) -> tuple[Placement, ...]:
    """Read every destination first, so the whole decision is made before anything is written."""

    planned: list[Placement] = []
    for skill in packaged_skills():
        manifest = manifest_for(skill)
        destination = inspect_destination(target, skill.name)
        planned.append(
            Placement(skill, manifest, destination, _action(destination, manifest, force=force))
        )
    return tuple(planned)


def _action(destination: Destination, manifest: SkillManifest, *, force: bool) -> InstallAction:
    """Decide what one destination has earned, from its state alone."""

    if destination.state == "absent":
        return "installed"
    if destination.state == "managed":
        return "unchanged" if destination.manifest == manifest else "upgraded"
    return "replaced" if force else "skipped"


def _conflicting(placement: Placement, *, force: bool) -> bool:
    return placement.destination.state in CONFLICTING_STATES and not force


def _document(
    target: SkillTarget, placements: tuple[Placement, ...], run: ReportRun
) -> CommandDocument:
    return command_document(
        COMMAND,
        SKILL_INSTALLATION_SCHEMA,
        run,
        {
            "source": {
                "galley_version": __version__,
                "path": packaged_root_path(),
                "skills": [placement.skill.name for placement in placements],
            },
            "target": target.facts(),
            "skills": [placement.facts() for placement in placements],
        },
    )


def _skipped(document: CommandDocument, placements: tuple[Placement, ...]) -> CommandDocument:
    """State plainly that nothing was installed, for every skill, before refusing."""

    return with_facts(
        document, {"skills": [placement.facts("skipped") for placement in placements]}
    )


def _placed(document: CommandDocument, placements: tuple[Placement, ...]) -> CommandDocument:
    """Materialise each skill that needs it, reporting exactly what landed."""

    taken: list[dict[str, object]] = []
    for position, placement in enumerate(placements):
        if placement.action == "unchanged":
            taken.append(placement.facts())
            continue
        failure = place_skill(placement.destination.path, placement.skill, placement.manifest)
        if failure is None:
            taken.append(placement.facts())
            continue
        remaining = [later.facts("skipped") for later in placements[position + 1 :]]
        document = with_facts(
            document, {"skills": [*taken, placement.facts("skipped"), *remaining]}
        )
        return with_refusal(document, _unplaceable(placement, failure.detail))
    return with_facts(document, {"skills": taken})


def _conflict(conflicts: list[Placement], *, force: bool) -> InstallationRefusal:
    """Name every destination Galley cannot speak for, and what makes it unattributable."""

    named = ", ".join(placement.skill.name for placement in conflicts)
    return InstallationRefusal(
        boundary="unattributable-skill-destination",
        stage=DESTINATION_STAGE,
        summary=(
            f"the installed skill directories for {named} are not the ones Galley recorded, "
            "so replacing them needs explicit permission"
        ),
        fact={
            "force": force,
            "destinations": [
                {"name": placement.skill.name, **placement.destination.facts()}
                for placement in conflicts
            ],
        },
    )


def _prepared(target: SkillTarget) -> InstallationRefusal | None:
    """Prove the target can hold an installation before any of it is written."""

    try:
        target.path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return _unusable(target, str(error))
    state = target_state(target.path)
    return None if state == "usable" else _unusable(target, state)


def _unusable(target: SkillTarget, detail: str) -> InstallationRefusal:
    return InstallationRefusal(
        boundary="skill-target-unusable",
        stage=TARGET_STAGE,
        summary=f"the skill target cannot hold an installation: {display_path(target.path)}",
        fact={"path": display_path(target.path), "detail": detail},
    )


def _unplaceable(placement: Placement, detail: str) -> InstallationRefusal:
    return InstallationRefusal(
        boundary="skill-not-placed",
        stage=PLACEMENT_STAGE,
        summary=f"{placement.skill.name} could not be written into the target",
        fact={
            "name": placement.skill.name,
            "path": display_path(placement.destination.path),
            "detail": detail,
        },
    )


def _file_facts(placement: Placement, action: InstallAction) -> list[dict[str, object]]:
    """List the hashes this skill ends up with, or the ones it left alone."""

    if action == "skipped":
        return reported(placement.destination.present, "retained")
    return reported(placement.manifest.entries, "unchanged" if action == "unchanged" else "written")

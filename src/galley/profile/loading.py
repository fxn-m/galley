"""Public Device Profile loading and rendering."""

import sysconfig
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import cast

import galley
from galley.json_reading import integer, mapping, sequence, text
from galley.profile.reading import ProfileError
from galley.profile.validation import assemble_profile
from galley.reader_software import observed_software, render_observed_software

# Anchored to the package root, not this file: the checkout keeps profiles/ two levels above
# src/galley/ wherever this module sits inside the package.
SOURCE_PROFILES = Path(galley.__file__).resolve().parents[2] / "profiles"


def list_profiles() -> list[dict[str, object]]:
    """Return every validated Device Profile sorted by profile id."""

    profiles: list[dict[str, object]] = []
    identifiers: set[str] = set()
    for manifest in _profile_manifests():
        profile = assemble_profile(manifest)
        identifier = cast(str, profile["id"])
        if identifier in identifiers:
            raise ProfileError(f"duplicate Device Profile id: {identifier}")
        identifiers.add(identifier)
        profiles.append(profile)
    return sorted(profiles, key=lambda profile: cast(str, profile["id"]))


def _profile_manifests() -> list[Path]:
    """Find only this checkout's or installed distribution's packaged manifests."""

    if SOURCE_PROFILES.is_dir():
        return sorted(
            manifest
            for directory in SOURCE_PROFILES.iterdir()
            if directory.is_dir() and (manifest := directory / "profile.yaml").is_file()
        )
    try:
        package = distribution("galley")
    except PackageNotFoundError as error:
        raise ProfileError("installed Device Profile metadata is unavailable") from error
    data_root = Path(sysconfig.get_path("data")).resolve()
    manifests = {
        Path(str(package.locate_file(entry))).resolve()
        for entry in package.files or ()
        if entry.name == "profile.yaml"
    }
    return sorted(manifest for manifest in manifests if manifest.parent.parent == data_root)


def load_profile(profile_id: str) -> dict[str, object]:
    """Load one validated Device Profile by its public identifier."""

    for profile in list_profiles():
        if profile["id"] == profile_id:
            return profile
    raise ProfileError(f"unknown Device Profile: {profile_id}")


def profile_summary(profile: dict[str, object]) -> dict[str, object]:
    """Select the stable public summary fields for profile discovery."""

    return {
        "device": profile["device"],
        "id": profile["id"],
        "observed_software": observed_software(profile),
        "profile_version": profile["profile_version"],
        "reader": profile["reader"],
    }


def render_profile(profile: dict[str, object]) -> str:
    """Render concise human output from one validated public profile object."""

    software = cast(dict[str, object], profile["software"])
    observed = observed_software(profile)
    requirements = cast(list[dict[str, object]], profile["requirements"])
    non_requirements = cast(list[dict[str, object]], profile["non_requirements"])
    behaviour = cast(list[dict[str, object]], profile["behaviour"])
    activation = cast(dict[str, object], profile["activation"])
    observations = cast(list[dict[str, object]], profile["observations"])
    rechecks = cast(list[dict[str, object]], software["queued_changes"])
    software_kind = str(software["kind"])
    return (
        f"{profile['id']}: {profile['device']} / {profile['reader']}\n"
        f"Profile {profile['profile_version']}; observed {render_observed_software(observed)}\n"
        f"Requirements: {len(requirements)}; non-requirements: {len(non_requirements)}\n"
        f"Device Behaviour: {len(behaviour)}; activations: {len(activation)}; "
        f"observations: {len(observations)}\n"
        f"{software_kind.title()} rechecks: {len(rechecks)}\n"
    )


def requirement(profile: dict[str, object], requirement_id: str) -> dict[str, object]:
    """Return one Compatibility Requirement's data by its exact identifier."""

    for entry in sequence(profile.get("requirements")):
        candidate = mapping(entry)
        if text(candidate.get("id")) == requirement_id:
            return candidate
    return {}


def enforced_limit(profile: dict[str, object], requirement_id: str) -> int | None:
    """Return the limit one requirement enforces, or nothing where it states none.

    Nothing is the honest answer for a profile that records no limit, and it is not zero: a
    caller bounding something against this must do nothing rather than bound it to nothing.
    """

    return integer(mapping(requirement(profile, requirement_id).get("limit")).get("enforced"))


def counting_rule(profile: dict[str, object], requirement_id: str) -> dict[str, object]:
    """Return the counting rule one requirement states, rather than assuming it in code."""

    return mapping(requirement(profile, requirement_id).get("counting_rule"))


def observation_tuning(profile: dict[str, object], name: str, key: str) -> list[str]:
    """Take one activated observation's tuning list from profile data, never from code."""

    for entry in sequence(profile.get("observations")):
        activation = mapping(entry)
        if text(activation.get("name")) == name:
            tuning = mapping(activation.get("tuning"))
            return [value for item in sequence(tuning.get(key)) if (value := text(item))]
    return []


def observation_note(profile: dict[str, object], name: str) -> str:
    """Take one activated observation's own note from profile data rather than restating it."""

    for entry in sequence(profile.get("observations")):
        candidate = mapping(entry)
        if text(candidate.get("name")) == name:
            return " ".join((text(candidate.get("note")) or "").split())
    return ""


def activation(profile: dict[str, object], name: str) -> object:
    """Return one Device Behaviour activation's value, or None where the profile sets none."""

    return activation_entry(profile, name).get("value")


def activation_entry(profile: dict[str, object], name: str) -> dict[str, object]:
    """Return one Device Behaviour activation whole, with the justification it was decided on."""

    return mapping(mapping(profile.get("activation")).get(name))


def image_requirements(profile: dict[str, object]) -> list[str]:
    """Name every requirement judged by a support matrix, in stable identifier order."""

    return sorted(
        identifier
        for entry in sequence(profile.get("requirements"))
        if (candidate := mapping(entry)).get("support") is not None
        and (identifier := text(candidate.get("id"))) is not None
    )

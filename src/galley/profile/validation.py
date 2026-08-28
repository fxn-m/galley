"""Validate and assemble Device Profile manifests and fragments."""

from pathlib import Path, PurePosixPath
from typing import cast

from galley.observations import OBSERVATION_NAMES
from galley.profile.cover import (
    RASTER_COLOUR_TYPES,
    validate_cover_artwork,
    validate_cover_pipeline,
)
from galley.profile.reading import (
    ProfileError,
    load_mapping,
    mapping,
    mapping_list,
    register_id,
    require_keys,
    require_string,
    string_list,
)
from galley.profile.software import validate_software

CLAIM_KINDS = {
    "device-test",
    "firmware-source",
    "spec-document",
    "device-inference",
    "product-decision",
}
FAILURE_MODES = {
    "crash",
    "silent-misdirection",
    "silent-loss",
    "visible-loss",
    "graceful-degradation",
    "unknown",
}
REFUSAL_MODES = {"crash", "silent-misdirection"}
MATRIX_KEYS = {"sample_depth", "colour_types", "scan_mode", "colour_models"}
MATRIX_SECTIONS = {"compatible", "incompatible", "unlisted"}


def assemble_profile(manifest_path: Path) -> dict[str, object]:
    """Assemble one manifest and its fragments into a validated public object."""

    manifest_path = manifest_path.resolve()
    profile_root = manifest_path.parent
    manifest = load_mapping(manifest_path)
    if manifest.get("schema") != "galley/device-profile/2":
        raise ProfileError("unknown profile schema")
    require_string(manifest.get("profile_version"), "profile_version")
    require_string(manifest.get("id"), "profile id")
    validate_software(manifest.get("software"), manifest_path)

    parts = mapping(manifest.get("parts"), "parts")
    expected_part_names = {
        "requirements",
        "non_requirements",
        "behaviour",
        "activation",
        "observations",
    }
    if set(parts) != expected_part_names:
        raise ProfileError(
            "parts must name requirements, non_requirements, behaviour, activation, and observations"
        )

    requirement_paths = _fragment_paths(parts.get("requirements"), "requirements")
    non_requirement_paths = _fragment_paths(parts.get("non_requirements"), "non_requirements")
    singleton_paths = [
        require_string(parts.get(name), f"parts.{name}")
        for name in ("behaviour", "activation", "observations")
    ]
    relative_paths = requirement_paths + non_requirement_paths + singleton_paths
    if len(relative_paths) != len(set(relative_paths)):
        raise ProfileError("duplicate fragment path")

    resolved = [_resolve_fragment(profile_root, path) for path in relative_paths]
    listed = {manifest_path, *resolved}
    actual = {path.resolve() for path in profile_root.rglob("*.yaml")}
    unlisted = sorted(actual - listed)
    if unlisted:
        names = ", ".join(str(path.relative_to(profile_root)) for path in unlisted)
        raise ProfileError(f"unlisted fragment: {names}")

    identifiers: set[str] = set()
    requirements: dict[str, dict[str, object]] = {}
    for path in resolved[: len(requirement_paths)]:
        requirement = load_mapping(path)
        identifier = register_id(requirement, identifiers, path)
        _validate_requirement(requirement, path)
        requirements[identifier] = requirement

    start = len(requirement_paths)
    stop = start + len(non_requirement_paths)
    non_requirements: list[dict[str, object]] = []
    for path in resolved[start:stop]:
        non_requirement = load_mapping(path)
        _ = register_id(non_requirement, identifiers, path)
        require_keys(non_requirement, {"statement", "rationale", "provenance"}, path)
        _validate_claims(non_requirement.get("provenance"), path)
        non_requirements.append(non_requirement)

    behaviour_path, activation_path, observations_path = resolved[stop:]
    behaviour, behaviours = _validate_behaviour(behaviour_path, identifiers)
    activation, activations = _validate_activation(activation_path, behaviours, set(requirements))
    for behaviour_id, activation_names in behaviours.items():
        for activation_name in activation_names:
            if activation_name not in activations:
                raise ProfileError(
                    f"{behaviour_path}: {behaviour_id} references unknown activation {activation_name}"
                )
    observations = _validate_observations(observations_path)

    public = {key: value for key, value in manifest.items() if key != "parts"}
    public.update(
        requirements=list(requirements.values()),
        non_requirements=non_requirements,
        behaviour=behaviour,
        activation=activation,
        observations=observations,
    )
    return public


def _validate_requirement(requirement: dict[str, object], path: Path) -> None:
    require_keys(
        requirement,
        {"statement", "evaluable_on", "failure_mode", "authority", "provenance"},
        path,
    )
    failure_mode = require_string(requirement.get("failure_mode"), f"{path}: failure_mode")
    authority = require_string(requirement.get("authority"), f"{path}: authority")
    if failure_mode not in FAILURE_MODES:
        raise ProfileError(f"{path}: invalid failure_mode {failure_mode}")
    if authority not in {"report", "refuse"}:
        raise ProfileError(f"{path}: invalid authority {authority}")
    if authority == "refuse" and failure_mode not in REFUSAL_MODES:
        raise ProfileError(f"{path}: {failure_mode} cannot carry refusal authority")
    _validate_claims(requirement.get("provenance"), path)
    _validate_matrix(requirement.get("support"), path)
    _validate_subject(requirement.get("applies_to"), path)


def _validate_behaviour(
    path: Path, identifiers: set[str]
) -> tuple[list[dict[str, object]], dict[str, list[str]]]:
    document = load_mapping(path)
    entries = mapping_list(document.get("behaviour"), f"{path}: behaviour")
    behaviours: dict[str, list[str]] = {}
    for entry in entries:
        identifier = register_id(entry, identifiers, path)
        _validate_claim(entry, f"{path}: behaviour {identifier}")
        behaviours[identifier] = string_list(
            entry.get("justifies"), f"{path}: behaviour {identifier}.justifies"
        )
    return entries, behaviours


def _validate_activation(
    path: Path, behaviours: dict[str, list[str]], requirement_ids: set[str]
) -> tuple[dict[str, object], set[str]]:
    document = load_mapping(path)
    activation = mapping(document.get("activation"), f"{path}: activation")
    for name, raw in activation.items():
        entry = mapping(raw, f"{path}: activation {name}")
        justification = require_string(
            entry.get("justified_by"), f"{path}: activation {name}.justified_by"
        )
        if justification not in behaviours:
            raise ProfileError(f"{path}: activation {name} references {justification}")
        if name not in behaviours[justification]:
            raise ProfileError(f"{path}: activation {name} is not justified by {justification}")
        required_by = entry.get("required_by")
        if required_by is not None:
            for requirement in string_list(required_by, f"{path}: activation {name}.required_by"):
                if requirement not in requirement_ids:
                    raise ProfileError(f"{path}: activation {name} references {requirement}")
        if name == "image_encoding":
            _validate_image_encoding(entry, path)
        if name == "cover_artwork":
            validate_cover_artwork(entry, path)
    validate_cover_pipeline(activation, path)
    return activation, set(activation)


def _validate_image_encoding(entry: dict[str, object], path: Path) -> None:
    """Keep the selected PNG colour model and its independently checked types coherent."""

    value = mapping(entry.get("value"), f"{path}: activation image_encoding.value")
    colour_model = require_string(
        value.get("colour_model"), f"{path}: activation image_encoding.value.colour_model"
    )
    expected = RASTER_COLOUR_TYPES.get(colour_model)
    if expected is None:
        raise ProfileError(f"{path}: unknown raster colour model {colour_model}")
    actual = (value.get("opaque_colour_type"), value.get("alpha_colour_type"))
    if actual != expected:
        raise ProfileError(
            f"{path}: {colour_model} raster colour types must be {expected[0]} and {expected[1]}"
        )


def _validate_observations(path: Path) -> list[dict[str, object]]:
    document = load_mapping(path)
    observations = mapping_list(document.get("observations"), f"{path}: observations")
    names: list[str] = []
    allowed_fields = {"name", "enabled", "note", "tuning"}
    for observation in observations:
        unexpected = sorted(set(observation) - allowed_fields)
        if unexpected:
            raise ProfileError(f"{path}: profile observation redefines {', '.join(unexpected)}")
        name = require_string(observation.get("name"), f"{path}: observation name")
        if name not in OBSERVATION_NAMES:
            raise ProfileError(f"{path}: unknown observation {name}")
        if name in names:
            raise ProfileError(f"{path}: duplicate observation {name}")
        names.append(name)
    return observations


def _validate_claims(value: object, path: Path) -> None:
    for index, claim in enumerate(mapping_list(value, f"{path}: provenance")):
        _validate_claim(claim, f"{path}: provenance[{index}]")


def _validate_claim(claim: dict[str, object], label: str) -> None:
    require_string(claim.get("claim"), f"{label}.claim")
    kind = require_string(claim.get("kind"), f"{label}.kind")
    require_string(claim.get("date"), f"{label}.date")
    if kind not in CLAIM_KINDS:
        raise ProfileError(f"{label}: invalid claim kind {kind}")
    if kind == "firmware-source":
        require_string(claim.get("source_tag"), f"{label}.source_tag")
    status = claim.get("status")
    if status is not None:
        if status != "retracted":
            raise ProfileError(f"{label}: invalid claim status {status}")
        require_string(claim.get("retracted_by"), f"{label}.retracted_by")
        require_string(claim.get("retracted_on"), f"{label}.retracted_on")


def _resolve_fragment(root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or str(relative) != value:
        raise ProfileError(f"unsafe fragment path: {value}")
    resolved = (root / Path(*relative.parts)).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ProfileError(f"missing or unsafe fragment path: {value}")
    return resolved


def _fragment_paths(value: object, label: str) -> list[str]:
    paths = string_list(value, f"parts.{label}")
    if not paths:
        raise ProfileError(f"parts.{label} must not be empty")
    return paths


def _validate_matrix(value: object, path: Path) -> None:
    """Reject a support matrix naming a field no Galley measurement can answer."""

    if value is None:
        return
    matrix = mapping(value, f"{path}: support")
    _reject(set(matrix) - MATRIX_SECTIONS, path, "support")
    for section in ("compatible", "incompatible"):
        entries = matrix.get(section)
        if entries is None:
            continue
        for entry in string_or_shape_list(entries, f"{path}: support.{section}"):
            _reject(set(entry) - MATRIX_KEYS, path, f"support.{section}")


def _validate_subject(value: object, path: Path) -> None:
    """Reject a subject declaration Galley cannot bind to a measured media type."""

    if value is None:
        return
    stated = mapping(value, f"{path}: applies_to")
    if set(stated) != {"measured_media_types"}:
        raise ProfileError(f"{path}: applies_to must name measured_media_types alone")
    _ = string_list(stated.get("measured_media_types"), f"{path}: applies_to")


def string_or_shape_list(value: object, label: str) -> list[dict[str, object]]:
    """Return only the mapping entries of a matrix section, ignoring plain names."""

    if not isinstance(value, list):
        raise ProfileError(f"{label}: expected a list")
    return [mapping(item, label) for item in cast(list[object], value) if not isinstance(item, str)]


def _reject(unknown: set[str], path: Path, where: str) -> None:
    if unknown:
        raise ProfileError(f"{path}: {where} names unknown field {', '.join(sorted(unknown))}")

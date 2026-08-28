"""Read Device Profile documents without inventing values they do not state."""

from pathlib import Path
from typing import cast

import yaml


class ProfileError(ValueError):
    """A Device Profile violates its assembled schema."""


def load_mapping(path: Path) -> dict[str, object]:
    """Parse one profile fragment as a string-keyed mapping."""

    try:
        raw = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as error:
        raise ProfileError(f"{path}: malformed YAML: {error}") from error
    return mapping(raw, str(path))


def mapping(value: object, label: str) -> dict[str, object]:
    """Require a string-keyed mapping."""

    if not isinstance(value, dict):
        raise ProfileError(f"{label}: expected a string-keyed mapping")
    document = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in document):
        raise ProfileError(f"{label}: expected a string-keyed mapping")
    return cast(dict[str, object], document)


def mapping_list(value: object, label: str) -> list[dict[str, object]]:
    """Require a list of string-keyed mappings."""

    if not isinstance(value, list):
        raise ProfileError(f"{label}: expected a list")
    return [mapping(item, label) for item in cast(list[object], value)]


def string_list(value: object, label: str) -> list[str]:
    """Require a list of strings."""

    if not isinstance(value, list):
        raise ProfileError(f"{label}: expected a list of strings")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise ProfileError(f"{label}: expected a list of strings")
    return cast(list[str], items)


def require_string(value: object, label: str) -> str:
    """Require a non-empty string."""

    if not isinstance(value, str) or not value:
        raise ProfileError(f"{label}: expected a non-empty string")
    return value


def require_keys(document: dict[str, object], keys: set[str], path: Path) -> None:
    """Require every named field to be present."""

    missing = sorted(keys - document.keys())
    if missing:
        raise ProfileError(f"{path}: missing fields: {', '.join(missing)}")


def register_id(document: dict[str, object], seen: set[str], path: Path) -> str:
    """Claim one identifier, rejecting a duplicate across the whole profile."""

    identifier = require_string(document.get("id"), f"{path}: id")
    if identifier in seen:
        raise ProfileError(f"{path}: duplicate id {identifier}")
    seen.add(identifier)
    return identifier

"""Validate the Repair Convention data held beside the main Agent Skill.

The conventions ship as product knowledge rather than CLI capabilities. Each entry must explain
why it is source-specific and name only source kinds Galley can actually read.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

from galley.sources import supported_kind_ids

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src/galley/skills/galley/resources/repair-conventions.yaml"
SCHEMA = "galley/repair-conventions/3"
CONVENTION_FIELDS = {
    "id",
    "title",
    "source",
    "why_not_general",
    "pairing_key",
    "complete_when",
    "preserve_when_ambiguous",
    "carriers",
    "target",
    "retained_evidence",
}
CARRIER_FIELDS = {
    "kind",
    "reference",
    "definition",
    "pairing_evidence",
}


class RepairConventionError(ValueError):
    """The Repair Convention data violates the release contract."""


def validate_repair_conventions(path: Path) -> None:
    """Validate the schema, per-entry contract, and carrier source kinds."""

    data = _mapping(path)
    if data.get("schema") != SCHEMA:
        raise RepairConventionError("unknown Repair Convention schema")
    if data.get("version") != 3:
        raise RepairConventionError("Repair Convention version must be 3")
    entries = data.get("conventions")
    if not isinstance(entries, list) or not entries:
        raise RepairConventionError("conventions must be a non-empty list")
    kinds = set(supported_kind_ids())
    seen: set[str] = set()
    for index, raw in enumerate(cast(list[object], entries)):
        identifier = _convention(raw, index, kinds)
        if identifier in seen:
            raise RepairConventionError(f"duplicate convention id: {identifier}")
        seen.add(identifier)


def _convention(raw: object, index: int, kinds: set[str]) -> str:
    if not isinstance(raw, dict):
        raise RepairConventionError(f"convention {index} must be a string-keyed mapping")
    entry = cast(dict[str, object], raw)
    _fields(entry.keys(), CONVENTION_FIELDS, f"convention {index}")
    identifier = entry["id"]
    if not isinstance(identifier, str) or not identifier.strip():
        raise RepairConventionError(f"convention {index}: id must be a non-empty string")
    for field in sorted(CONVENTION_FIELDS - {"carriers"}):
        value = entry[field]
        if not isinstance(value, str) or not value.strip():
            raise RepairConventionError(f"{identifier}: {field} must be a non-empty string")
    _carriers(identifier, entry["carriers"], kinds)
    return identifier


def _carriers(identifier: str, raw: object, kinds: set[str]) -> None:
    """Require at least one carrier, each a Source Kind Galley reads, and each named once.

    A Repair Convention is recorded once naming every shape it takes, so a repeated kind is a
    second entry pretending to be one convention.
    """

    if not isinstance(raw, list) or not raw:
        raise RepairConventionError(f"{identifier}: carriers must be a non-empty list")
    seen: set[str] = set()
    for carrier in cast(list[object], raw):
        if not isinstance(carrier, dict):
            raise RepairConventionError(f"{identifier}: each carrier must be a mapping")
        fields = cast(dict[str, object], carrier)
        _fields(fields.keys(), CARRIER_FIELDS, identifier)
        for field in sorted(CARRIER_FIELDS):
            value = fields[field]
            if not isinstance(value, str) or not value.strip():
                raise RepairConventionError(f"{identifier}: carrier {field} must be a string")
        kind = cast(str, fields["kind"])
        if kind not in kinds:
            raise RepairConventionError(f"{identifier}: carrier names an unreadable kind: {kind}")
        if kind in seen:
            raise RepairConventionError(f"{identifier}: carrier kind named twice: {kind}")
        seen.add(kind)


def _fields(present: object, expected: set[str], label: str) -> None:
    keys = set(cast("set[str]", present))
    missing = sorted(expected - keys)
    unexpected = sorted(keys - expected)
    if missing:
        raise RepairConventionError(f"{label}: missing fields: {', '.join(missing)}")
    if unexpected:
        raise RepairConventionError(f"{label}: unexpected fields: {', '.join(unexpected)}")


def _mapping(path: Path) -> dict[str, object]:
    try:
        raw = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as error:
        raise RepairConventionError(f"{path}: malformed data: {error}") from error
    if not isinstance(raw, dict):
        raise RepairConventionError(f"{path}: expected a string-keyed mapping")
    return cast(dict[str, object], raw)


def main() -> int:
    """Validate the committed Repair Convention data from the command line."""

    try:
        validate_repair_conventions(DATA)
    except RepairConventionError as error:
        print(f"checkconventions: {error}")
        return 1
    print("checkconventions: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

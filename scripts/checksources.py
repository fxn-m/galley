"""Validate the release-scope source-kind data Galley classifies inputs with."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src/galley/data/source-kinds.yaml"
GROUPS = ("supported", "refused")
# The ids Galley's own code names. Renaming one in the data without changing the code would
# silently send every Markdown file down the unimplemented route, so the binding is checked here.
REQUIRED = {
    "supported": ("markdown", "article-url"),
    "refused": ("local-html", "pdf", "epub", "unsupported-url-scheme", "unknown-local-kind"),
}


class SourceKindError(ValueError):
    """The source-kind data violates the release contract."""


def validate_source_kinds(path: Path) -> None:
    """Validate schema, required ids, statements, reasons, and suffix and scheme uniqueness."""

    data = _load_mapping(path)
    if data.get("schema") != "galley/source-kinds/1":
        raise SourceKindError("unknown source-kind schema")
    if data.get("version") != 1:
        raise SourceKindError("source-kind version must be 1")

    seen: dict[str, str] = {}
    for group in GROUPS:
        identifiers = [_entry_id(entry, group) for entry in _entries(data, group)]
        missing = sorted(set(REQUIRED[group]) - set(identifiers))
        if missing:
            raise SourceKindError(f"{group} source kinds missing: {', '.join(missing)}")
        for entry in _entries(data, group):
            _validate_entry(entry, group, seen)


def _validate_entry(entry: dict[str, object], group: str, seen: dict[str, str]) -> None:
    identifier = _entry_id(entry, group)
    for field in ("statement", "reason") if group == "refused" else ("statement",):
        if not _text(entry.get(field)):
            raise SourceKindError(f"{identifier} has no {field}")
    for field in ("suffixes", "schemes"):
        for value in _string_list(entry.get(field), f"{identifier}.{field}"):
            claimed = value.lower()
            if claimed in seen:
                raise SourceKindError(f"{claimed} claimed by both {seen[claimed]} and {identifier}")
            seen[claimed] = identifier


def _entries(data: dict[str, object], group: str) -> list[dict[str, object]]:
    value = data.get(group)
    if not isinstance(value, list):
        raise SourceKindError(f"{group} must be a list of source kinds")
    entries = cast(list[object], value)
    if not all(isinstance(entry, dict) for entry in entries):
        raise SourceKindError(f"{group} must be a list of source kinds")
    return cast(list[dict[str, object]], entries)


def _entry_id(entry: dict[str, object], group: str) -> str:
    identifier = _text(entry.get("id"))
    if not identifier:
        raise SourceKindError(f"a {group} source kind has no id")
    return identifier


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SourceKindError(f"{label} must be a list of strings")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise SourceKindError(f"{label} must be a list of strings")
    return cast(list[str], items)


def _load_mapping(path: Path) -> dict[str, object]:
    raw = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise SourceKindError(f"{path}: expected a string-keyed mapping")
    mapping = cast(dict[object, object], raw)
    if not all(isinstance(key, str) for key in mapping):
        raise SourceKindError(f"{path}: expected a string-keyed mapping")
    return cast(dict[str, object], mapping)


def main() -> int:
    """Validate the committed source-kind data."""

    try:
        validate_source_kinds(DATA)
    except (SourceKindError, OSError) as error:
        print(f"checksources: {error}")
        return 1
    print("checksources: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

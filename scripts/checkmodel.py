"""Validate Galley's release-scope Pandoc data against the installed pinned Pandoc."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

import yaml

from galley.release_data import XHTML_ATTRIBUTES, ReleaseDataError, attribute_rules

ROOT = Path(__file__).resolve().parent.parent
VOCABULARY_FILTER = ROOT / "scripts/pandoc-vocabulary.lua"
DATA = ROOT / "src/galley/data"
AST_PARTS = ("blocks", "inlines", "other")
SUB_TYPES = "sub_types"


class ModelledSetError(ValueError):
    """Release-scope Pandoc data or the installed Pandoc violates the release contract."""


def validate_modelled_set(path: Path, ast_path: Path | None = None) -> None:
    """Validate schema, uniqueness, pinned version, and constructor names."""

    data = _pinned_document(path, "galley/modelled-set/1", "Modelled Set")
    constructors = _unique(_string_list(data.get("constructors"), "constructors"), "constructors")
    unknown = sorted(constructors - _pandoc_vocabulary()[0])
    if unknown:
        raise ModelledSetError(f"unknown Pandoc constructors: {', '.join(unknown)}")
    if ast_path is None:
        return
    document = _pinned_document(ast_path, "galley/pandoc-ast/1", "Pandoc AST vocabulary")
    nodes = _unique(_string_list(document.get("blocks"), "blocks"), "blocks") | _unique(
        _string_list(document.get("inlines"), "inlines"), "inlines"
    )
    outside = sorted(constructors - nodes)
    if outside:
        raise ModelledSetError(f"Modelled Set names outside the AST: {', '.join(outside)}")


def validate_pandoc_ast(path: Path) -> None:
    """Prove the AST vocabulary partitions Pandoc's own constructor list exactly."""

    data = _pinned_document(path, "galley/pandoc-ast/1", "Pandoc AST vocabulary")
    listed: set[str] = set()
    for part in (*AST_PARTS, SUB_TYPES):
        names = _unique(_string_list(data.get(part), part), part)
        overlap = sorted(names & listed)
        if overlap:
            raise ModelledSetError(f"{part} also listed elsewhere: {', '.join(overlap)}")
        listed |= names
    constructors, tags = _pandoc_vocabulary()
    nodes = listed - _unique(_string_list(data.get(SUB_TYPES), SUB_TYPES), SUB_TYPES)
    missing = sorted(constructors - nodes)
    if missing:
        raise ModelledSetError(
            f"Pandoc constructors absent from the AST data: {', '.join(missing)}"
        )
    unknown = sorted(nodes - constructors)
    if unknown:
        raise ModelledSetError(f"unknown Pandoc constructors: {', '.join(unknown)}")
    absent = sorted(tags - listed)
    if absent:
        raise ModelledSetError(
            f"Pandoc sub-type tags absent from the AST data: {', '.join(absent)}"
        )


def _pinned_document(path: Path, schema: str, label: str) -> dict[str, object]:
    data = _load_mapping(path)
    if data.get("schema") != schema:
        raise ModelledSetError(f"unknown {label} schema")
    if data.get("version") != 1:
        raise ModelledSetError(f"{label} version must be 1")
    pinned_version = data.get("pandoc_version")
    if not isinstance(pinned_version, str):
        raise ModelledSetError("pandoc_version must be a string")
    installed_version = _pandoc_version()
    if installed_version != pinned_version:
        raise ModelledSetError(
            f"installed Pandoc {installed_version} does not match pinned {pinned_version}"
        )
    return data


def _unique(names: list[str], label: str) -> set[str]:
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ModelledSetError(f"duplicate {label}: {', '.join(duplicates)}")
    return set(names)


def _pandoc_version() -> str:
    result = subprocess.run(
        ["pandoc", "--version"], check=False, capture_output=True, text=True, cwd=ROOT
    )
    if result.returncode != 0:
        raise ModelledSetError(f"pandoc --version failed: {result.stderr.strip()}")
    first_line = result.stdout.splitlines()[0].split()
    if len(first_line) != 2 or first_line[0] != "pandoc":
        raise ModelledSetError("could not parse installed Pandoc version")
    return first_line[1]


def _pandoc_vocabulary() -> tuple[set[str], set[str]]:
    """Ask Pandoc for its own constructor names and its own sub-type tag names."""

    result = subprocess.run(
        ["pandoc", "--lua-filter", str(VOCABULARY_FILTER), "--to", "plain"],
        input="",
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise ModelledSetError(f"Pandoc vocabulary query failed: {result.stderr.strip()}")
    exposed: dict[str, set[str]] = {"constructor": set(), "tag": set()}
    for line in result.stdout.splitlines():
        kind, _, name = line.strip().partition("\t")
        if name and kind in exposed:
            exposed[kind].add(name)
    return exposed["constructor"], exposed["tag"]


def _load_mapping(path: Path) -> dict[str, object]:
    raw = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise ModelledSetError(f"{path}: expected a string-keyed mapping")
    mapping = cast(dict[object, object], raw)
    if not all(isinstance(key, str) for key in mapping):
        raise ModelledSetError(f"{path}: expected a string-keyed mapping")
    return cast(dict[str, object], mapping)


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ModelledSetError(f"{label} must be a list of strings")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise ModelledSetError(f"{label} must be a list of strings")
    return cast(list[str], items)


def validate_xhtml_attributes(path: Path, ast_path: Path) -> None:
    """Validate the attribute rules against Pandoc's own vocabulary and against the code.

    Two halves have to agree for the filter to reach an element at all: this file names what each
    constructor's element admits, and `release_data.ATTR_POSITION` names where that constructor
    keeps its `Attr`. A name in one and not the other silently takes an element out of the filter,
    which is a book quietly becoming invalid rather than a failing gate.
    """

    document = _load_mapping(path)
    if document.get("schema") != "galley/xhtml-attributes/1":
        raise ModelledSetError(f"{path.name} is not galley/xhtml-attributes/1")
    entries = cast(list[object], document.get("elements") or [])
    named = _unique(
        [str(cast(dict[str, object], entry).get("constructor")) for entry in entries],
        "elements",
    )
    unknown = sorted(named - _pandoc_vocabulary()[0])
    if unknown:
        raise ModelledSetError(f"unknown Pandoc constructors: {', '.join(unknown)}")
    stated = _unique(_string_list(document.get("global"), "global"), "global")
    if not stated or not document.get("global_prefixes"):
        raise ModelledSetError(f"{path.name} states no global attributes or prefixes")
    attribute_rules(XHTML_ATTRIBUTES)  # raises where the code and the data disagree


def main() -> int:
    """Validate the committed Pandoc AST vocabulary, Modelled Set and attribute rules."""

    try:
        validate_pandoc_ast(DATA / "pandoc-ast.yaml")
        validate_modelled_set(DATA / "modelled-set.yaml", DATA / "pandoc-ast.yaml")
        validate_xhtml_attributes(DATA / "xhtml-attributes.yaml", DATA / "pandoc-ast.yaml")
    except (ModelledSetError, ReleaseDataError, OSError) as error:
        print(f"checkmodel: {error}")
        return 1
    print("checkmodel: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

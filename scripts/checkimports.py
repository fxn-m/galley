"""Validate the internal import graph against the declared layer data.

Two facts are enforced. The module-level graph must be acyclic, because every workflow in this
repo assumes it can reason about the package bottom-up. And the unit-level graph — packages,
plus each root module as its own unit — must equal `scripts/import-layers.yaml` exactly: an
undeclared edge fails, and a declared edge no longer exercised fails, so the data file is always
the true current graph rather than an aspiration (the `checkmodel.py` discipline, applied to the
repo's own shape).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src/galley"
DATA = ROOT / "scripts/import-layers.yaml"


class ImportLayerError(Exception):
    """The import graph or its declaration violates the layout contract."""


def module_name(path: Path, package_root: Path) -> str:
    """Dotted module name for one source file, with `__init__` naming its package."""
    relative = path.relative_to(package_root).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return ".".join(["galley", *parts])


def unit_of(module: str) -> str:
    """The unit one module belongs to: its package, or itself when it sits at the root."""
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def internal_graph(package_root: Path) -> dict[str, set[str]]:
    """Every `galley` -> `galley` import edge at module level."""
    modules = {module_name(path, package_root): path for path in sorted(package_root.rglob("*.py"))}
    top_level = {unit_of(module) for module in modules if module != "galley"}
    graph: dict[str, set[str]] = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    raise ImportLayerError(f"{module}: relative imports are not used here")
                if node.module == "galley":
                    for alias in node.names:
                        if alias.name in top_level:
                            graph[module].add(f"galley.{alias.name}")
                elif node.module and node.module.startswith("galley."):
                    graph[module].add(node.module)
            elif isinstance(node, ast.Import):
                # Bare `import galley` reaches the package object (metadata, __file__) and
                # creates no unit edge; submodule forms would evade the edge reader.
                for alias in node.names:
                    if alias.name.startswith("galley."):
                        raise ImportLayerError(
                            f"{module}: use `from galley... import`, not `import {alias.name}`"
                        )
    return graph


def validate_acyclic(graph: dict[str, set[str]]) -> None:
    """Fail on any module-level import cycle, naming one member path."""
    states: dict[str, int] = {}
    stack: list[str] = []

    def visit(module: str) -> None:
        state = states.get(module)
        if state == 1:
            cycle = stack[stack.index(module) :] + [module]
            raise ImportLayerError("import cycle: " + " -> ".join(cycle))
        if state == 2:
            return
        states[module] = 1
        stack.append(module)
        for target in sorted(graph.get(module, ())):
            visit(target)
        stack.pop()
        states[module] = 2

    for module in sorted(graph):
        visit(module)


def unit_edges(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    """Collapse the module graph to unit level, dropping same-unit edges."""
    edges: dict[str, set[str]] = {}
    for module, targets in graph.items():
        if module == "galley":
            continue
        source = unit_of(module)
        edges.setdefault(source, set())
        for target in targets:
            target_unit = unit_of(target)
            if target_unit != source:
                edges[source].add(target_unit)
    return edges


def validate_units(graph: dict[str, set[str]], data_path: Path) -> None:
    """The observed unit graph must equal the declared one exactly."""
    raw = cast(object, yaml.safe_load(data_path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise ImportLayerError(f"{data_path.name}: expected a mapping")
    data = cast(dict[str, object], raw)
    if data.get("schema") != "galley/import-layers/1":
        raise ImportLayerError(f"{data_path.name}: expected schema galley/import-layers/1")
    if data.get("version") != 1:
        raise ImportLayerError(f"{data_path.name}: expected version 1")
    units_raw = data.get("units")
    if not isinstance(units_raw, dict):
        raise ImportLayerError(f"{data_path.name}: units must be a mapping")
    declared: dict[str, set[str]] = {}
    for unit, targets in cast(dict[object, object], units_raw).items():
        if not isinstance(unit, str):
            raise ImportLayerError(f"{data_path.name}: unit names must be strings")
        if targets is None:
            declared[unit] = set()
            continue
        if not isinstance(targets, list):
            raise ImportLayerError(f"{data_path.name}: {unit} directions must be a list")
        directions: set[str] = set()
        for target in cast(list[object], targets):
            if not isinstance(target, str):
                raise ImportLayerError(f"{data_path.name}: {unit} directions must be strings")
            directions.add(target)
        declared[unit] = directions
    observed = unit_edges(graph)
    for unit in sorted(set(observed) - set(declared)):
        raise ImportLayerError(f"unit {unit} exists but is not declared in {data_path.name}")
    for unit in sorted(set(declared) - set(observed)):
        raise ImportLayerError(f"unit {unit} is declared in {data_path.name} but does not exist")
    for unit in sorted(declared):
        for edge in sorted(observed[unit] - declared[unit]):
            raise ImportLayerError(f"undeclared import direction: {unit} -> {edge}")
        for edge in sorted(declared[unit] - observed[unit]):
            raise ImportLayerError(
                f"declared import direction is unused, remove it: {unit} -> {edge}"
            )


def main() -> int:
    try:
        graph = internal_graph(PACKAGE)
        validate_acyclic(graph)
        validate_units(graph, DATA)
    except (ImportLayerError, OSError) as error:
        print(f"checkimports: {error}", file=sys.stderr)
        return 1
    units = len({unit_of(module) for module in graph if module != "galley"})
    print(f"checkimports: OK ({len(graph)} modules, {units} units, acyclic)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

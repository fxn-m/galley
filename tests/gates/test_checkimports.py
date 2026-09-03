from pathlib import Path

import pytest
from scripts.checkimports import (
    DATA,
    PACKAGE,
    ImportLayerError,
    internal_graph,
    validate_acyclic,
    validate_units,
)


def test_the_package_graph_is_acyclic_and_exactly_declared() -> None:
    graph = internal_graph(PACKAGE)
    validate_acyclic(graph)
    validate_units(graph, DATA)


def write_tree(root: Path, files: dict[str, str]) -> Path:
    package = root / "galley"
    for name, body in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(body, encoding="utf-8")
    return package


def write_layers(root: Path, units: str) -> Path:
    path = root / "import-layers.yaml"
    _ = path.write_text(
        f"schema: galley/import-layers/1\nversion: 1\nunits:\n{units}", encoding="utf-8"
    )
    return path


def test_a_module_cycle_is_rejected(tmp_path: Path) -> None:
    package = write_tree(
        tmp_path,
        {
            "__init__.py": "",
            "alpha.py": "from galley.beta import thing\n",
            "beta.py": "from galley.alpha import other\n",
        },
    )

    with pytest.raises(ImportLayerError, match="import cycle"):
        validate_acyclic(internal_graph(package))


def test_an_undeclared_direction_is_rejected(tmp_path: Path) -> None:
    package = write_tree(
        tmp_path,
        {"__init__.py": "", "alpha.py": "from galley.beta import thing\n", "beta.py": ""},
    )
    layers = write_layers(tmp_path, "  alpha: []\n  beta: []\n")

    with pytest.raises(ImportLayerError, match="undeclared import direction: alpha -> beta"):
        validate_units(internal_graph(package), layers)


def test_an_unused_declared_direction_is_rejected(tmp_path: Path) -> None:
    package = write_tree(tmp_path, {"__init__.py": "", "alpha.py": "", "beta.py": ""})
    layers = write_layers(tmp_path, "  alpha: [beta]\n  beta: []\n")

    with pytest.raises(ImportLayerError, match="unused, remove it: alpha -> beta"):
        validate_units(internal_graph(package), layers)


def test_an_undeclared_unit_is_rejected(tmp_path: Path) -> None:
    package = write_tree(tmp_path, {"__init__.py": "", "alpha.py": ""})
    layers = write_layers(tmp_path, "  alpha: []\n  beta: []\n")

    with pytest.raises(ImportLayerError, match="beta is declared .* but does not exist"):
        validate_units(internal_graph(package), layers)


def test_a_plain_import_is_rejected(tmp_path: Path) -> None:
    package = write_tree(tmp_path, {"__init__.py": "", "alpha.py": "import galley.beta\n"})

    with pytest.raises(ImportLayerError, match="not `import galley.beta`"):
        internal_graph(package)


def test_a_bare_package_import_names_its_unit(tmp_path: Path) -> None:
    """`from galley import x` counts as an edge to root module x, as image facts uses it."""
    package = write_tree(
        tmp_path,
        {"__init__.py": "", "alpha.py": "from galley import beta as registry\n", "beta.py": ""},
    )
    layers = write_layers(tmp_path, "  alpha: []\n  beta: []\n")

    with pytest.raises(ImportLayerError, match="undeclared import direction: alpha -> beta"):
        validate_units(internal_graph(package), layers)

from pathlib import Path

import pytest

from scripts.checkmodel import ModelledSetError, validate_modelled_set, validate_pandoc_ast

DATA = Path("src/galley/data")
AST = DATA / "pandoc-ast.yaml"
MODELLED_SET = DATA / "modelled-set.yaml"


def test_modelled_set_matches_pinned_pandoc() -> None:
    validate_modelled_set(MODELLED_SET, AST)


def test_ast_vocabulary_partitions_pinned_pandoc() -> None:
    validate_pandoc_ast(AST)


def test_unknown_pandoc_constructor_is_rejected(tmp_path: Path) -> None:
    modelled_set = tmp_path / "modelled-set.yaml"
    source = MODELLED_SET.read_text(encoding="utf-8")
    _ = modelled_set.write_text(source.replace("  - Para\n", "  - Paraa\n"), encoding="utf-8")

    with pytest.raises(ModelledSetError, match="Paraa"):
        validate_modelled_set(modelled_set)


def test_a_constructor_missing_from_the_ast_data_is_rejected(tmp_path: Path) -> None:
    """A Pandoc constructor absent from every list would be silently skipped by every reader."""

    vocabulary = tmp_path / "pandoc-ast.yaml"
    source = AST.read_text(encoding="utf-8")
    _ = vocabulary.write_text(source.replace("  - Strikeout\n", ""), encoding="utf-8")

    with pytest.raises(ModelledSetError, match="Strikeout"):
        validate_pandoc_ast(vocabulary)


def test_a_constructor_listed_twice_is_rejected(tmp_path: Path) -> None:
    vocabulary = tmp_path / "pandoc-ast.yaml"
    source = AST.read_text(encoding="utf-8")
    _ = vocabulary.write_text(
        source.replace("  - Note\n", "  - Note\n  - Table\n"), encoding="utf-8"
    )

    with pytest.raises(ModelledSetError, match="Table"):
        validate_pandoc_ast(vocabulary)

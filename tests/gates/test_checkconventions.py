"""Hold Repair Convention data to its release contract, the way the other release data is held."""

from pathlib import Path

import pytest
from scripts.checkconventions import DATA, RepairConventionError, validate_repair_conventions


def test_the_committed_repair_conventions_are_valid() -> None:
    validate_repair_conventions(DATA)


def test_a_carrier_naming_a_kind_galley_cannot_read_is_rejected(tmp_path: Path) -> None:
    """A convention describes shapes a source arrives in, so its carriers are Source Kinds."""

    data = _edited(tmp_path, "      - kind: markdown", "      - kind: local-html")

    with pytest.raises(RepairConventionError, match="local-html"):
        validate_repair_conventions(data)


def test_a_convention_repeating_one_carrier_kind_is_rejected(tmp_path: Path) -> None:
    """One convention names each shape it takes once, rather than once per input path."""

    data = _edited(tmp_path, "      - kind: markdown", "      - kind: article-url")

    with pytest.raises(RepairConventionError, match="article-url"):
        validate_repair_conventions(data)


def test_a_convention_without_its_generality_argument_is_rejected(tmp_path: Path) -> None:
    """Recording why this is not a CLI capability is what keeps it out of the CLI."""

    data = _edited(tmp_path, "    why_not_general: >-", "    unexplained: >-")

    with pytest.raises(RepairConventionError, match="why_not_general"):
        validate_repair_conventions(data)


def test_two_conventions_sharing_an_id_are_rejected(tmp_path: Path) -> None:
    text = DATA.read_text(encoding="utf-8")
    body = text[text.index("  - id: ") :]
    data = tmp_path / "repair-conventions.yaml"
    _ = data.write_text(f"{text}{body}", encoding="utf-8")

    with pytest.raises(RepairConventionError, match="paul-graham-hand-rolled-endnotes"):
        validate_repair_conventions(data)


def _edited(tmp_path: Path, original: str, replacement: str) -> Path:
    data = tmp_path / "repair-conventions.yaml"
    text = DATA.read_text(encoding="utf-8")
    assert original in text
    _ = data.write_text(text.replace(original, replacement), encoding="utf-8")
    return data

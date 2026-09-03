from pathlib import Path

import pytest
from scripts.checksources import DATA, SourceKindError, validate_source_kinds


def test_committed_source_kinds_are_valid() -> None:
    validate_source_kinds(DATA)


def test_a_renamed_id_the_code_depends_on_is_rejected(tmp_path: Path) -> None:
    """Renaming `markdown` would send every Markdown file down the unimplemented route."""

    data = tmp_path / "source-kinds.yaml"
    _ = data.write_text(
        DATA.read_text(encoding="utf-8").replace("id: markdown", "id: md"), encoding="utf-8"
    )

    with pytest.raises(SourceKindError, match="markdown"):
        validate_source_kinds(data)


def test_a_suffix_claimed_by_two_kinds_is_rejected(tmp_path: Path) -> None:
    """`classify` takes the first match, so an overlap would decide by list order."""

    data = tmp_path / "source-kinds.yaml"
    _ = data.write_text(
        DATA.read_text(encoding="utf-8").replace('suffixes: [".pdf"]', 'suffixes: [".pdf", ".md"]'),
        encoding="utf-8",
    )

    with pytest.raises(SourceKindError, match=".md"):
        validate_source_kinds(data)


def test_a_refused_kind_without_a_reason_is_rejected(tmp_path: Path) -> None:
    """A refusal must name why, so an agent is left somewhere it can act."""

    data = tmp_path / "source-kinds.yaml"
    _ = data.write_text(
        DATA.read_text(encoding="utf-8").replace(
            "    reason: PDF input, extraction, OCR and preparation are outside this release's scope.\n",
            "",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SourceKindError, match="pdf has no reason"):
        validate_source_kinds(data)

from pathlib import Path

from scripts.checkregex import find_unapproved_regex_imports


def test_production_tree_has_no_unapproved_regex_imports() -> None:
    assert find_unapproved_regex_imports(Path("src")) == []


def test_regex_import_requires_an_explicit_allowlist_entry(tmp_path: Path) -> None:
    source = tmp_path / "rules.py"
    _ = source.write_text("import re\n", encoding="utf-8")

    assert find_unapproved_regex_imports(tmp_path) == [source]
    assert find_unapproved_regex_imports(tmp_path, allowed={source}) == []

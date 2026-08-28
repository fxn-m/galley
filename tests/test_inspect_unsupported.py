import json
from pathlib import Path
from typing import Any, cast

from galley.document.constructors import constructor_facts
from galley.release_data import MODELLED_SET, names
from tests.markdown_fixtures import (
    INSIDE_THE_MODELLED_SET,
    MODELLED_WORDS,
    OUTSIDE_THE_MODELLED_SET,
    STRUCK_THROUGH_TITLE,
    native_ast,
    write_markdown,
)
from tests.public_cli import public_cli_commands, run_command, run_public_cli

CARRIED = "carried-through"
# Every constructor Pandoc's Markdown reader produces that the Modelled Set does not name.
OUTSIDE = ("Cite", "LineBlock", "Math", "RawBlock", "RawInline", "Strikeout", "Table", "Underline")
MODELLED_SET_NAMES = names(MODELLED_SET, "constructors")


def inspect_json(source: Path) -> list[Any]:
    results = run_public_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json")
    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    return [json.loads(result.stdout) for result in results]


def test_canonical_document_facts_count_every_constructor(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "outside.md", OUTSIDE_THE_MODELLED_SET)

    for report in inspect_json(source):
        constructors = report["canonical_document"]["constructors"]
        assert constructors["Table"] == {"basis": "measured", "unit": "nodes", "value": 1}
        assert constructors["Header"] == {"basis": "measured", "unit": "nodes", "value": 1}
        assert constructors["RawBlock"]["value"] > 1
        assert set(OUTSIDE) <= set(constructors)
        # A sub-type tag is not a constructor and must never be counted as one.
        assert "AlignDefault" not in constructors
        assert "ColWidthDefault" not in constructors
        assert "InlineMath" not in constructors


def test_every_unsupported_constructor_is_recorded_and_carried(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "outside.md", OUTSIDE_THE_MODELLED_SET)

    for report in inspect_json(source):
        canonical = report["canonical_document"]
        assert canonical["modelled_set"] == "galley/modelled-set/1"
        unsupported = canonical["unsupported"]
        assert [record["constructor"] for record in unsupported] == sorted(OUTSIDE)
        for record in unsupported:
            assert record["disposition"] == CARRIED
            assert record["in_modelled_set"] is False
            assert record["count"]["value"] == len(record["locations"])
            assert record["count"]["basis"] == "measured"
        by_name = {record["constructor"]: record for record in unsupported}
        assert by_name["Table"]["locations"] == ["/blocks/1"]
        assert by_name["Strikeout"]["locations"] == ["/blocks/2/c/4"]


def test_every_unsupported_location_points_at_its_own_node(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "outside.md", OUTSIDE_THE_MODELLED_SET)
    ast = native_ast(source)

    for report in inspect_json(source):
        for record in report["canonical_document"]["unsupported"]:
            for pointer in record["locations"]:
                assert _resolve(ast, pointer)["t"] == record["constructor"]


def test_the_modelled_set_produces_no_unsupported_records(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "modelled.md")

    for report in inspect_json(source):
        canonical = report["canonical_document"]
        assert canonical["unsupported"] == []
        assert set(canonical["constructors"]) == {
            "BlockQuote",
            "BulletList",
            "Emph",
            "Header",
            "Image",
            "Para",
            "Plain",
            "Space",
            "Str",
        }


def test_unsupported_content_alone_never_refuses(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "outside.md", OUTSIDE_THE_MODELLED_SET)

    for report in inspect_json(source):
        assert (report["outcome"], report["refusal"]) == ("completed", None)
        # No requirement is answered from Unsupported Content: it creates no refusal authority.
        unsupported = [
            record["constructor"] for record in report["canonical_document"]["unsupported"]
        ]
        assert unsupported
        assert [entry for entry in report["compatibility"] if entry["verdict"] == "false"] == []


def test_unsupported_content_survives_verbatim_and_stays_out_of_warnings(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "outside.md", OUTSIDE_THE_MODELLED_SET)

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        evidence = tmp_path / f"carried-{index}"
        result = run_command(
            command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        assert json.loads(result.stdout)["warnings"] == []
        document = json.loads((evidence / "canonical-document.json").read_text(encoding="utf-8"))
        assert document["pandoc"] == native_ast(source)
        assert document["warnings"] == []
        carried = {record["t"] for record in _nodes(document["pandoc"]["blocks"])}
        assert set(OUTSIDE) <= carried


def _nodes(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [node for item in cast(list[Any], value) for node in _nodes(item)]
    if not isinstance(value, dict):
        return []
    node = cast(dict[str, Any], value)
    found: list[Any] = [node] if "t" in node else []
    return found + [found_node for child in node.values() for found_node in _nodes(child)]


def _resolve(ast: Any, pointer: str) -> Any:
    node = ast
    for step in pointer.lstrip("/").split("/"):
        node = node[int(step)] if step.isdigit() else node[step]
    return node


def test_human_output_names_unsupported_content_it_carried(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "outside.md", OUTSIDE_THE_MODELLED_SET)

    results = run_public_cli("inspect", str(source), "--profile", "x4-crosspoint")

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    for result in results:
        assert "Unsupported Content: carried through; " in result.stdout
        assert "Table 1" in result.stdout
        assert "RawBlock 6" in result.stdout


def test_the_reader_reaches_the_text_of_every_modelled_constructor(tmp_path: Path) -> None:
    """The Modelled Set names twenty-six constructors; a missing branch would drop one silently."""

    source = write_markdown(tmp_path / "modelled.md", INSIDE_THE_MODELLED_SET)

    for index, command in enumerate(public_cli_commands("inspect", str(source))):
        evidence = tmp_path / f"modelled-{index}"
        result = run_command(
            command, "--profile", "x4-crosspoint", "--json", "--evidence-dir", str(evidence)
        )

        assert (result.returncode, result.stderr) == (0, "")
        canonical = json.loads(result.stdout)["canonical_document"]
        assert canonical["unsupported"] == []
        assert set(canonical["constructors"]) == set(MODELLED_SET_NAMES)
        baseline = (evidence / "preservation-baseline.txt").read_text(encoding="utf-8")
        assert [word for word in MODELLED_WORDS if word not in baseline] == []


def test_unsupported_content_in_metadata_is_reported_too(tmp_path: Path) -> None:
    """Pandoc's writers put metadata on the page, so its constructors are carried through too."""

    source = write_markdown(tmp_path / "struck.md", STRUCK_THROUGH_TITLE)

    for report in inspect_json(source):
        canonical = report["canonical_document"]
        assert canonical["location_base"] == "pandoc"
        assert [record["constructor"] for record in canonical["unsupported"]] == ["Strikeout"]
        assert canonical["unsupported"][0]["locations"] == ["/meta/title/c/2"]


def test_a_table_reports_no_unknown_constructor(tmp_path: Path) -> None:
    """Alignments and column widths are sub-type tags, not content Galley failed to recognise."""

    source = write_markdown(tmp_path / "outside.md", OUTSIDE_THE_MODELLED_SET)

    for report in inspect_json(source):
        unsupported = report["canonical_document"]["unsupported"]
        assert [record["constructor"] for record in unsupported if not record["recognised"]] == []
        assert "AlignDefault" not in report["canonical_document"]["constructors"]


def test_a_constructor_galley_has_never_met_is_reported_not_skipped() -> None:
    """A silent skip would count a node's children while the node itself vanished."""

    ast: dict[str, object] = {
        "blocks": [{"t": "Para", "c": [{"t": "FutureInline", "c": [{"t": "Str", "c": "hi"}]}]}],
        "meta": {},
    }

    facts = constructor_facts(ast)
    unsupported = cast(list[Any], facts["unsupported"])
    assert [record["constructor"] for record in unsupported] == ["FutureInline"]
    assert unsupported[0]["recognised"] is False
    assert unsupported[0]["locations"] == ["/blocks/0/c/0"]
    assert unsupported[0]["disposition"] == CARRIED
    assert set(cast(dict[str, object], facts["constructors"])) == {"FutureInline", "Para", "Str"}

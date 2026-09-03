import json
from pathlib import Path
from typing import Any

from galley.observations import OBSERVATION_REGISTRY
from tests.markdown_fixtures import (
    DESTROYED_STRUCTURE,
    MARKED_CONTENT,
    PROJECTED_NAVIGATION,
    RENUMBERED_LISTS,
    blocked_links,
    write_markdown,
)
from tests.public_cli import run_cli

NAVIGATION = ("anchors-per-chapter", "footnote-href-length", "recorded-links-per-block")
BLOCK_CEILING = "recorded-links-per-block"
# Each construct the device destroys unconditionally, with the unit its count carries, the probe
# its profile note must cite, and every place it sits in `DESTROYED_STRUCTURE`. The strikeout in
# the title is the one that proves the count surveys `meta` and not only `blocks`.
DESTROYED = (
    ("strikethrough-inversion", "strikeouts", "Probe A5", ["/blocks/1/c/0", "/meta/title/c/2"]),
    ("code-block-reflow", "code blocks", "Probe A4", ["/blocks/2"]),
    ("table-relationship-loss", "tables", "Probe A3", ["/blocks/3"]),
)


def inspect_json(source: Path) -> Any:
    result = run_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json")
    assert (result.returncode, result.stderr) == (0, "")
    return json.loads(result.stdout)


def entries(report: Any) -> dict[str, Any]:
    return {result["requirement_id"]: result for result in report["compatibility"]}


def observations(report: Any) -> dict[str, Any]:
    return {entry["name"]: entry for entry in report["observations"]}


def test_inspect_projects_navigation_without_claiming_a_measurement(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    report = inspect_json(source)
    assert report["artifact"] is None
    results = entries(report)
    for requirement in NAVIGATION:
        measurement = results[requirement]["measurement"]
        assert measurement["basis"] == "projected"
        assert measurement["relation"] in {"lower-bound", "indeterminate"}
        assert measurement["definition"]
    assert results[BLOCK_CEILING]["measurement"]["value"] == 2
    assert results[BLOCK_CEILING]["measurement"]["unit"] == "recorded links"
    assert results["anchors-per-chapter"]["measurement"]["value"] == 1
    assert results["footnote-href-length"]["measurement"]["value"] == 50
    assert results["anchors-per-chapter"]["measurement"]["relation"] == "indeterminate"


def test_a_projection_below_a_limit_proves_nothing(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    report = inspect_json(source)
    results = entries(report)
    assert results[BLOCK_CEILING]["verdict"] == "unknown"
    assert results["anchors-per-chapter"]["verdict"] == "unknown"
    assert results["footnote-href-length"]["verdict"] == "unknown"
    # This source carries a note, so preparation strips cross-references and no floor holds.
    assert results[BLOCK_CEILING]["measurement"]["relation"] == "indeterminate"


def test_a_lower_bound_above_a_limit_settles_the_requirement(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "many.md", blocked_links(129))

    report = inspect_json(source)
    result = entries(report)[BLOCK_CEILING]
    assert result["measurement"] == {
        "basis": "projected",
        "definition": result["measurement"]["definition"],
        "note": result["measurement"]["note"],
        "relation": "lower-bound",
        "unit": "recorded links",
        "value": 129,
    }
    assert result["verdict"] == "false"
    assert result["failure_mode"] == "crash"
    assert result["authority"] == "refuse"
    # Inspect projects a refusal without promising one: it has no authority over its subject.
    assert report["outcome"] == "completed"


def test_requirements_with_no_instrument_stay_unknown(tmp_path: Path) -> None:
    """Image bytes are measured when preparation resolves them, so inspect claims nothing."""

    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    report = inspect_json(source)
    results = entries(report)
    for requirement in ("image-media-type", "jpeg-decoding", "png-decoding"):
        assert results[requirement]["verdict"] == "unknown"
        assert results[requirement]["measurement"] is None
    assert results["footnotes-per-screen"]["verdict"] == "unevaluable"


def test_every_observation_uses_its_registry_definition(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    report = inspect_json(source)
    emitted = observations(report)
    assert set(emitted) <= set(OBSERVATION_REGISTRY)
    assert len(emitted) == 13
    for name, entry in emitted.items():
        evidence, consequence = OBSERVATION_REGISTRY[name]
        assert (entry["evidence"], entry["consequence"]) == (evidence, consequence)


def test_only_the_owning_layer_judges_an_observation(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "marked.md", MARKED_CONTENT)

    report = inspect_json(source)
    emitted = observations(report)
    for name, entry in emitted.items():
        if entry["evidence"] != "computable":
            assert entry["fired"] is None, name
    assert emitted["page-break-content-destruction"]["fired"] is True
    assert emitted["unrenderable-glyphs"]["fired"] is True
    assert emitted["unrenderable-glyphs"]["locations"] == ["U+21A9", "U+251C"]
    assert emitted["page-break-content-destruction"]["locations"] == [
        "/blocks/1",
        "/blocks/2/c/0",
    ]


def test_observations_inspect_cannot_yet_compute_stay_undecided(tmp_path: Path) -> None:
    """A computable observation measured on the artifact is outstanding, not false, before one."""

    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    report = inspect_json(source)
    emitted = observations(report)
    for name in (
        "footnote-target-reliability",
        "unrenderable-images",
        "alt-text-fallback-absence",
    ):
        assert emitted[name]["fired"] is None, name
        assert emitted[name]["note"]
    assert emitted["alt-text-fallback-absence"]["applicability"] is True


def test_ordered_list_numbering_is_computed_from_the_source(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "lists.md", RENUMBERED_LISTS)

    report = inspect_json(source)
    entry = observations(report)["ordered-list-numbering-loss"]
    assert entry["fired"] is True
    assert entry["measurement"] == {"basis": "measured", "unit": "lists", "value": 2}
    assert entry["locations"] == ["/blocks/1", "/blocks/3"]


def test_reading_facts_describe_the_source_independently_of_the_profile(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    report = inspect_json(source)
    reading = report["canonical_document"]["reading"]
    assert reading["links"]["value"] == 4
    assert reading["images"]["value"] == 1
    assert reading["images_without_alt_text"]["value"] == 0
    assert reading["notes"]["value"] == 1
    assert reading["identifiers"]["value"] == 1
    # By level, because a count of headings cannot show a demotion and the levels can.
    assert reading["heading_levels"] == {"1": {"basis": "measured", "unit": "headings", "value": 1}}
    assert all(
        fact["basis"] == "measured" for name, fact in reading.items() if name != "heading_levels"
    )


def test_two_documents_with_the_same_headings_at_different_levels_are_told_apart(
    tmp_path: Path,
) -> None:
    """Extraction demotes a page's own headings routinely, and a count cannot show it.

    Two observed documents carried the same one-level heading demotion, which a constructor count
    could not distinguish. Before this the Report said `Header: 60` and nothing else.
    """

    def document(title: str, depth: int) -> Path:
        headings = "\n\n".join(
            f"{'#' * (level + depth)} Heading {level}\n\nProse under it." for level in (1, 2)
        )
        return write_markdown(tmp_path / f"{title}.md", f"---\ntitle: {title}\n---\n\n{headings}\n")

    # The same two headings, one level apart. Nothing else about the documents differs.
    top = inspect_json(document("top", 0))
    low = inspect_json(document("low", 1))
    assert top["canonical_document"]["constructors"]["Header"]["value"] == 2
    assert low["canonical_document"]["constructors"]["Header"]["value"] == 2
    assert list(top["canonical_document"]["reading"]["heading_levels"]) == ["1", "2"]
    assert list(low["canonical_document"]["reading"]["heading_levels"]) == ["2", "3"]


def test_human_output_names_projections_and_outstanding_judgements(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    result = run_cli("inspect", str(source), "--profile", "x4-crosspoint")

    assert (result.returncode, result.stderr) == (0, "")
    assert (
        "Projected, not measured: anchors-per-chapter 1 anchors (indeterminate); "
        "footnote-href-length 50 bytes (indeterminate); "
        "recorded-links-per-block 2 recorded links (indeterminate)\n"
    ) in result.stdout
    assert "7 awaiting agent or human judgement" in result.stdout


def test_a_footnote_apparatus_removes_the_projection_floor(tmp_path: Path) -> None:
    """The interlock fires on a counted zero: a note means cross-references are stripped."""

    bounded = write_markdown(tmp_path / "bounded.md", blocked_links(129))
    unbounded = write_markdown(tmp_path / "unbounded.md", blocked_links(129, note=True))

    report = inspect_json(bounded)
    result = entries(report)[BLOCK_CEILING]
    assert (result["measurement"]["relation"], result["verdict"]) == ("lower-bound", "false")
    report = inspect_json(unbounded)
    result = entries(report)[BLOCK_CEILING]
    assert (result["measurement"]["relation"], result["verdict"]) == (
        "indeterminate",
        "unknown",
    )
    assert result["measurement"]["value"] == 129


def test_the_constructs_the_device_destroys_fire_on_one_occurrence(tmp_path: Path) -> None:
    """The July probes recorded unconditional destruction, so nothing here waits on a threshold."""

    source = write_markdown(tmp_path / "destroyed.md", DESTROYED_STRUCTURE)

    report = inspect_json(source)
    emitted = observations(report)
    for name, unit, probe, locations in DESTROYED:
        entry = emitted[name]
        assert entry["fired"] is True, name
        measured = {"basis": "measured", "unit": unit, "value": len(locations)}
        assert entry["measurement"] == measured, name
        assert entry["locations"] == locations, name
        assert probe in entry["note"], name


def test_a_document_carrying_none_of_them_is_measured_rather_than_excused(tmp_path: Path) -> None:
    """Applicability is the device's, not the document's: these three are destroyed wherever they
    occur, so a document without one has been measured at zero rather than left out of scope."""

    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    report = inspect_json(source)
    emitted = observations(report)
    for name, unit, _, _ in DESTROYED:
        entry = emitted[name]
        assert (entry["applicability"], entry["fired"]) == (True, False), name
        assert entry["measurement"] == {"basis": "measured", "unit": unit, "value": 0}
        assert entry["locations"] == [], name


def test_boundary_chrome_is_activated_without_the_cli_judging_it(tmp_path: Path) -> None:
    """Activating this observation must not smuggle in a second extraction threshold."""

    source = write_markdown(tmp_path / "linked.md", PROJECTED_NAVIGATION)

    report = inspect_json(source)
    entry = observations(report)["boundary-chrome-presence"]
    assert (entry["evidence"], entry["applicability"], entry["fired"]) == (
        "flaggable",
        True,
        None,
    )
    assert entry["measurement"] is None
    assert entry["locations"] == []
    assert "link" in entry["note"] and "word" in entry["note"]

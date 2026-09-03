"""The Report states how far a book's figures were reduced, without judging whether they read."""

from pathlib import Path
from typing import Any

from tests.support.image_fixtures import (
    NORMALISED_IMAGES,
    colour_png,
    grayscale_png,
    progressive_jpeg,
    transparent_webp,
    vector_svg,
)
from tests.support.markdown_fixtures import PLAIN_BOOK, write_markdown
from tests.support.public_cli import prepare, run_cli

ARGUMENTS = ("--profile", "x4-crosspoint")
# The fixture references five images and names a sixth as the cover. The cover is not a figure
# the work leans on, so the aggregate counts five.
FIGURES = 5
OVERSIZE = (900, 1500)


def transformable(directory: Path) -> None:
    """Write the fixture's six resources: one oversize figure, four that fit, and a cover."""

    _ = colour_png(directory / "oversize.png", width=OVERSIZE[0], height=OVERSIZE[1])
    _ = colour_png(directory / "deep.png", width=20, height=20, depth=16)
    _ = transparent_webp(directory / "alpha.webp")
    _ = progressive_jpeg(directory / "progressive.jpg")
    _ = vector_svg(directory / "diagram.svg")
    _ = grayscale_png(directory / "cover.png", width=8, height=12)


def reduction(report: Any) -> Any:
    return report["preparation"]["images"]["reduction"]


def test_the_aggregate_summarises_every_figure_the_book_carries(tmp_path: Path) -> None:
    transformable(tmp_path)
    prepared_source = write_markdown(tmp_path / "source-0.md", NORMALISED_IMAGES)
    journey = prepare(tmp_path, prepared_source)
    report = journey.report

    stated = reduction(report)
    assert stated["images"]["value"] == FIGURES
    assert stated["reduced"]["value"] == 1
    assert stated["scale"]["minimum"]["value"] == 53
    assert stated["scale"]["median"]["value"] == 100
    assert stated["scale"]["maximum"]["value"] == 100
    assert stated["scale"]["minimum"]["unit"] == "percent"


def test_the_aggregate_answers_what_walking_the_records_answers(tmp_path: Path) -> None:
    transformable(tmp_path)
    prepared_source = write_markdown(tmp_path / "source-0.md", NORMALISED_IMAGES)
    journey = prepare(tmp_path, prepared_source)
    report = journey.report

    records = report["preparation"]["images"]["records"]
    scales = sorted(entry["packaged"]["scale"]["value"] for entry in records if not entry["cover"])
    stated = reduction(report)
    assert stated["images"]["value"] == len(scales)
    assert stated["reduced"]["value"] == sum(1 for scale in scales if scale < 100)
    assert stated["scale"]["minimum"]["value"] == scales[0]
    assert stated["scale"]["maximum"]["value"] == scales[-1]
    assert stated["scale"]["median"]["value"] == scales[len(scales) // 2]


def test_the_cover_is_named_a_reference_and_left_out_of_the_aggregate(tmp_path: Path) -> None:
    transformable(tmp_path)
    prepared_source = write_markdown(tmp_path / "source-0.md", NORMALISED_IMAGES)
    journey = prepare(tmp_path, prepared_source)
    report = journey.report

    records = report["preparation"]["images"]["records"]
    assert sum(1 for entry in records if entry["cover"]) == 1
    assert len(records) == FIGURES + 1
    assert reduction(report)["images"]["value"] == FIGURES


def test_a_book_with_no_figures_states_none_rather_than_a_scale(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", PLAIN_BOOK)
    journey = prepare(tmp_path, prepared_source)
    report = journey.report

    stated = reduction(report)
    assert stated["images"]["value"] == 0
    assert stated["reduced"]["value"] == 0
    assert stated["scale"] is None


def test_the_aggregate_states_that_it_does_not_settle_legibility(tmp_path: Path) -> None:
    transformable(tmp_path)
    prepared_source = write_markdown(tmp_path / "source-0.md", NORMALISED_IMAGES)
    journey = prepare(tmp_path, prepared_source)
    report = journey.report

    definition = reduction(report)["definition"]
    assert "legibility" in definition
    assert "device reads" in definition.lower()


def test_the_terminal_names_the_reduction_without_the_records(tmp_path: Path) -> None:
    transformable(tmp_path)
    source = write_markdown(tmp_path / "terminal-0.md", NORMALISED_IMAGES)
    output = tmp_path / "terminal-0.epub"
    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS)

    assert (result.returncode, result.stderr) == (0, "")
    assert "Figures: 5 carried, 1 reduced to fit; scale 53/100/100 percent" in result.stdout

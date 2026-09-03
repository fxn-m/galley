"""Preparation resolves, measures and preserves the images a Canonical Document references."""

import json
from pathlib import Path
from typing import Any

from tests.support.image_fixtures import (
    MISSING_IMAGE,
    PRESERVED_IMAGES,
    baseline_jpeg,
    grayscale_png,
)
from tests.support.markdown_fixtures import NOTE_POSITIONS, write_markdown
from tests.support.prepared_epub import PreparedEpub
from tests.support.public_cli import prepare, run_cli

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
REFERENCES = 4


def illustrated(directory: Path) -> tuple[Path, Path, Path]:
    """Write the three resources the illustrated fixture references, one of them mislabelled."""

    square = grayscale_png(directory / "figure.png", width=4, height=3)
    photo = baseline_jpeg(directory / "photo.jpg")
    mislabelled = grayscale_png(directory / "labelled.jpg", width=2, height=2)
    return square, photo, mislabelled


def records(report: Any) -> list[Any]:
    return report["preparation"]["images"]["records"]


def transform(report: Any) -> Any:
    return next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "image-preparation"
    )


def test_preparation_preserves_and_measures_each_resource_and_reference(tmp_path: Path) -> None:
    square, photo, mislabelled = illustrated(tmp_path)
    prepared_source = write_markdown(tmp_path / "source-0.md", PRESERVED_IMAGES)
    journey = prepare(tmp_path, prepared_source)
    output, report = journey.output, journey.report

    record = records(report)[0]
    assert record["transform"] == "preserved"
    assert record["device_support"] == "true"
    assert record["source"]["measured_media_type"] == "image/png"
    assert record["source"]["sample_depth"]["value"] == 8
    assert record["source"]["colour_type"]["value"] == 0
    assert (record["source"]["width"]["value"], record["source"]["height"]["value"]) == (4, 3)
    book = PreparedEpub(output)
    published = book.media_resources()[_relative(record["artifact"]["path"])]
    assert published == square.read_bytes()

    record = next(entry for entry in records(report) if entry["src"] == "photo.jpg")
    assert record["transform"] == "preserved"
    assert record["source"]["measured_media_type"] == "image/jpeg"
    assert record["source"]["scan_mode"] == "baseline"
    assert record["source"]["colour_model"] == "greyscale"
    assert book.media_resources()[_relative(record["artifact"]["path"])] == photo.read_bytes()

    repeated = [entry for entry in records(report) if entry["src"] == "figure.png"]
    assert len(repeated) == 2
    assert repeated[0]["reference"] != repeated[1]["reference"]
    assert repeated[0]["artifact"] == repeated[1]["artifact"]
    assert transform(report)["references"]["value"] == REFERENCES + 1
    assert transform(report)["resources"]["value"] == 4
    assert len(book.media_resources()) == 4
    assert len({src for _, src, _ in book.image_sources()}) == 3
    assert len(book.image_sources()) == REFERENCES

    assert [entry["reference"] for entry in records(report) if not entry["cover"]] == [
        f"image-{number}" for number in range(1, REFERENCES + 1)
    ]
    first = records(report)[0]
    assert first["src"] == "figure.png"
    assert first["source"]["path"] == str(square.resolve())
    assert first["alt"] == "grey square"
    assert first["title"] == "Square title"
    assert first["packaged"]["sha256"] == first["source"]["sha256"]
    assert first["artifact"]["sha256"] == first["source"]["sha256"]
    assert first["artifact"]["referenced"] is True

    record = next(entry for entry in records(report) if entry["src"] == "labelled.jpg")
    assert record["source"]["measured_media_type"] == "image/png"
    assert record["artifact"]["measured_media_type"] == "image/png"
    assert record["artifact"]["path"].endswith(".png")
    assert book.media_resources()[_relative(record["artifact"]["path"])] == (
        mislabelled.read_bytes()
    )

    measured = {entry["sha256"]: entry for entry in report["artifact"]["images"]["resources"]}
    figures = [record for record in records(report) if not record["cover"]]
    assert len(measured) == 4
    assert len(figures) == REFERENCES
    for record in figures:
        resource = measured[record["source"]["sha256"]]
        assert record["artifact"]["path"] == resource["path"]
        assert resource["device_support"] == record["device_support"]
        assert resource["measured_media_type"] == record["source"]["measured_media_type"]
        assert resource["width"] == record["source"]["width"]
        assert resource["referenced"] is True
    assert not report["artifact"]["images"]["unresolved_references"]
    assert report["artifact"]["conformance"]["counts"]["error"]["value"] == 0

    entry = transform(report)
    assert entry["fired"] is True
    assert (entry["activation"], entry["justified_by"]) == (
        "image_encoding",
        "four-level-panel",
    )
    assert entry["device_judged"] is True
    assert entry["fit"] == {
        "activation": "image_fit",
        "device_judged": True,
        "justified_by": "panel-geometry",
        "max_height": {"basis": "reported", "unit": "pixels", "value": 800},
        "max_width": {"basis": "reported", "unit": "pixels", "value": 480},
    }
    assert entry["preserved"]["value"] == 3


def test_the_recorded_alt_text_is_the_alt_text_the_book_carries(tmp_path: Path) -> None:
    """Pandoc copies a figure's caption into the image description and drops the note from it."""

    _ = grayscale_png(tmp_path / "figure.png")
    prepared_source = write_markdown(tmp_path / "source-0.md", NOTE_POSITIONS)
    journey = prepare(tmp_path, prepared_source)
    output, report = journey.output, journey.report

    record = records(report)[0]
    assert record["alt"] == "Figure caption note."
    book = PreparedEpub(output)
    assert [alt for _, _, alt in book.image_sources() if alt] == [record["alt"]]
    caption = next(text for text in book.document_texts().values() if "Figure caption" in text)
    assert "Figure caption note." in caption


def test_a_reference_to_a_missing_resource_refuses_before_any_book_is_written(
    tmp_path: Path,
) -> None:
    source = write_markdown(tmp_path / "missing-0.md", MISSING_IMAGE)
    output = tmp_path / "missing-0.epub"

    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS)

    assert result.returncode == 3
    report = json.loads(result.stdout)
    assert report["outcome"] == "refused"
    assert report["refusal"]["boundary"] == "image-processing-failure"
    assert report["refusal"]["stage"] == "image-preparation"
    assert report["refusal"]["artifact_written"] is False
    assert report["refusal"]["fact"]["failures"] == [
        {"reason": "missing-resource", "reference": "image-1", "src": "absent.png"}
    ]
    assert not output.exists()
    assert (tmp_path / "missing-0.galley" / "report.json").is_file()


def test_human_output_names_the_images_preparation_carried(tmp_path: Path) -> None:
    _ = illustrated(tmp_path)
    source = write_markdown(tmp_path / "human-0.md", PRESERVED_IMAGES)

    result = run_cli(
        "prepare",
        str(source),
        "--output",
        str(tmp_path / "human-0.epub"),
        "--profile",
        "x4-crosspoint",
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert "Transform: image-preparation (fired)\n" in result.stdout
    assert (
        f"Images: {REFERENCES + 1} references to 4 resources, 3 preserved, 1 normalised\n"
    ) in result.stdout


def _relative(path: str) -> str:
    """Name one archive member the way the package manifest does, relative to the OPF."""

    return path.removeprefix("EPUB/")

"""Preparation resolves, measures and preserves the images a Canonical Document references."""

import json
from pathlib import Path
from typing import Any

from tests.image_fixtures import (
    MISSING_IMAGE,
    PRESERVED_IMAGES,
    baseline_jpeg,
    grayscale_png,
)
from tests.markdown_fixtures import NOTE_POSITIONS, write_markdown
from tests.prepared_epub import document_texts, image_sources, media_resources
from tests.public_cli import public_cli_commands, run_command

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
REFERENCES = 4


def illustrated(directory: Path) -> tuple[Path, Path, Path]:
    """Write the three resources the illustrated fixture references, one of them mislabelled."""

    square = grayscale_png(directory / "figure.png", width=4, height=3)
    photo = baseline_jpeg(directory / "photo.jpg")
    mislabelled = grayscale_png(directory / "labelled.jpg", width=2, height=2)
    return square, photo, mislabelled


def prepared(tmp_path: Path, index: int, command: list[str], text: str) -> tuple[Path, Any]:
    source = write_markdown(tmp_path / f"source-{index}.md", text)
    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, str(source), "--output", str(output), *ARGUMENTS)
    assert (result.returncode, result.stderr) == (0, "")
    return output, json.loads(result.stdout)


def records(report: Any) -> list[Any]:
    return report["preparation"]["images"]["records"]


def transform(report: Any) -> Any:
    return next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "image-preparation"
    )


def test_a_compatible_fitting_png_is_preserved_byte_for_byte(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        square, _, _ = illustrated(tmp_path)
        output, report = prepared(tmp_path, index, command, PRESERVED_IMAGES)

        record = records(report)[0]
        assert record["transform"] == "preserved"
        assert record["device_support"] == "true"
        assert record["source"]["measured_media_type"] == "image/png"
        assert record["source"]["sample_depth"]["value"] == 8
        assert record["source"]["colour_type"]["value"] == 0
        assert (record["source"]["width"]["value"], record["source"]["height"]["value"]) == (4, 3)
        published = media_resources(output)[_relative(record["artifact"]["path"])]
        assert published == square.read_bytes()


def test_a_baseline_jpeg_is_preserved_byte_for_byte(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        _, photo, _ = illustrated(tmp_path)
        output, report = prepared(tmp_path, index, command, PRESERVED_IMAGES)

        record = next(entry for entry in records(report) if entry["src"] == "photo.jpg")
        assert record["transform"] == "preserved"
        assert record["source"]["measured_media_type"] == "image/jpeg"
        assert record["source"]["scan_mode"] == "baseline"
        assert record["source"]["colour_model"] == "greyscale"
        assert media_resources(output)[_relative(record["artifact"]["path"])] == photo.read_bytes()


def test_repeated_references_to_one_resource_are_not_duplicated(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        _ = illustrated(tmp_path)
        output, report = prepared(tmp_path, index, command, PRESERVED_IMAGES)

        repeated = [entry for entry in records(report) if entry["src"] == "figure.png"]
        assert len(repeated) == 2
        assert repeated[0]["reference"] != repeated[1]["reference"]
        assert repeated[0]["artifact"] == repeated[1]["artifact"]
        assert transform(report)["references"]["value"] == REFERENCES
        assert transform(report)["resources"]["value"] == 3
        assert len(media_resources(output)) == 3
        assert len({src for _, src, _ in image_sources(output)}) == 3
        assert len(image_sources(output)) == REFERENCES


def test_every_reference_keeps_an_identity_connecting_its_source_to_the_artifact(
    tmp_path: Path,
) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        square, _, _ = illustrated(tmp_path)
        _, report = prepared(tmp_path, index, command, PRESERVED_IMAGES)

        assert [entry["reference"] for entry in records(report)] == [
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


def test_measurement_reads_the_bytes_rather_than_the_file_name(tmp_path: Path) -> None:
    """Every reference is measured, so a PNG called `.jpg` is packaged as the PNG it is."""

    for index, command in enumerate(public_cli_commands("prepare")):
        _, _, mislabelled = illustrated(tmp_path)
        output, report = prepared(tmp_path, index, command, PRESERVED_IMAGES)

        record = next(entry for entry in records(report) if entry["src"] == "labelled.jpg")
        assert record["source"]["measured_media_type"] == "image/png"
        assert record["artifact"]["measured_media_type"] == "image/png"
        assert record["artifact"]["path"].endswith(".png")
        assert media_resources(output)[_relative(record["artifact"]["path"])] == (
            mislabelled.read_bytes()
        )


def test_audit_measures_the_published_resources_and_agrees_with_preparation(
    tmp_path: Path,
) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        _ = illustrated(tmp_path)
        _, report = prepared(tmp_path, index, command, PRESERVED_IMAGES)

        measured = {entry["sha256"]: entry for entry in report["artifact"]["images"]["resources"]}
        assert len(measured) == 3
        for record in records(report):
            resource = measured[record["source"]["sha256"]]
            assert record["artifact"]["path"] == resource["path"]
            assert resource["device_support"] == record["device_support"]
            assert resource["measured_media_type"] == record["source"]["measured_media_type"]
            assert resource["width"] == record["source"]["width"]
            assert resource["referenced"] is True
        assert not report["artifact"]["images"]["unresolved_references"]
        assert report["artifact"]["conformance"]["counts"]["error"]["value"] == 0


def test_the_transform_names_the_activations_the_profile_decided(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        _ = illustrated(tmp_path)
        _, report = prepared(tmp_path, index, command, PRESERVED_IMAGES)

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

    for index, command in enumerate(public_cli_commands("prepare")):
        _ = grayscale_png(tmp_path / "figure.png")
        output, report = prepared(tmp_path, index, command, NOTE_POSITIONS)

        record = records(report)[0]
        assert record["alt"] == "Figure caption note."
        assert [alt for _, _, alt in image_sources(output)] == [record["alt"]]
        caption = next(text for text in document_texts(output).values() if "Figure caption" in text)
        assert "Figure caption note." in caption


def test_a_reference_to_a_missing_resource_refuses_before_any_book_is_written(
    tmp_path: Path,
) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        source = write_markdown(tmp_path / f"missing-{index}.md", MISSING_IMAGE)
        output = tmp_path / f"missing-{index}.epub"

        result = run_command(command, str(source), "--output", str(output), *ARGUMENTS)

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
        assert (tmp_path / f"missing-{index}.galley" / "report.json").is_file()


def test_human_output_names_the_images_preparation_carried(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        _ = illustrated(tmp_path)
        source = write_markdown(tmp_path / f"human-{index}.md", PRESERVED_IMAGES)

        result = run_command(
            command,
            str(source),
            "--output",
            str(tmp_path / f"human-{index}.epub"),
            "--profile",
            "x4-crosspoint",
        )

        assert (result.returncode, result.stderr) == (0, "")
        assert "Transform: image-preparation (fired)\n" in result.stdout
        assert (
            f"Images: {REFERENCES} references to 3 resources, 3 preserved, 0 normalised\n"
        ) in result.stdout


def _relative(path: str) -> str:
    """Name one archive member the way the package manifest does, relative to the OPF."""

    return path.removeprefix("EPUB/")

"""Incompatible images become the profile's safe form, and the book proves every one survived."""

import json
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from tests.image_fixtures import (
    NORMALISED_IMAGES,
    RESPONSIVE_IMAGE,
    colour_png,
    grayscale_png,
    progressive_jpeg,
    transparent_webp,
    vector_svg,
)
from tests.markdown_fixtures import write_markdown
from tests.prepared_epub import image_sources, media_resources, names, spine_documents
from tests.public_cli import public_cli_commands, run_command

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
MAXIMUM = (480, 800)
REFERENCES = 6
OVERSIZE = (900, 1500)
TRANSFORMED = {
    "oversize.png": ("true", False),
    "deep.png": ("false", True),
    "progressive.jpg": ("false", True),
    # WebP and SVG are measured as present rather than as geometry, so nothing Galley measured
    # can say either one fits the panel. Both are transformed anyway, which settles it.
    "alpha.webp": ("false", False),
    "diagram.svg": ("false", False),
}


def transformable(directory: Path) -> None:
    """Write one source resource for every input shape the profile does not render."""

    _ = colour_png(directory / "oversize.png", width=OVERSIZE[0], height=OVERSIZE[1])
    _ = colour_png(directory / "deep.png", width=20, height=20, depth=16)
    _ = transparent_webp(directory / "alpha.webp")
    _ = progressive_jpeg(directory / "progressive.jpg")
    _ = vector_svg(directory / "diagram.svg")
    _ = grayscale_png(directory / "cover.png", width=8, height=12)


def prepared(tmp_path: Path, index: int, command: list[str], text: str) -> tuple[Path, Any]:
    source = write_markdown(tmp_path / f"source-{index}.md", text)
    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, str(source), "--output", str(output), *ARGUMENTS)
    assert (result.returncode, result.stderr) == (0, "")
    return output, json.loads(result.stdout)


def records(report: Any) -> dict[str, Any]:
    return {entry["src"]: entry for entry in report["preparation"]["images"]["records"]}


def measured(entry: Any, side: str, key: str) -> Any:
    value = entry[side][key]
    return None if value is None else value["value"]


def test_every_unsupported_input_becomes_an_eight_bit_greyscale_png(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        _, report = prepared(tmp_path, index, command, NORMALISED_IMAGES)

        prepared_records = records(report)
        assert len(prepared_records) == REFERENCES
        # A colour PNG at 8 bits is device-verified, so only its size sends it through the
        # transform; every other input is transformed because the device does not render it.
        for src, support in TRANSFORMED.items():
            entry = prepared_records[src]
            assert entry["transform"] == "normalised"
            assert (entry["device_support"], entry["fits_panel"]) == support
            assert entry["packaged"]["measured_media_type"] == "image/png"
            assert measured(entry, "packaged", "sample_depth") == 8
            assert measured(entry, "packaged", "colour_type") in {0, 4}
        assert measured(prepared_records["alpha.webp"], "packaged", "colour_type") == 4
        assert measured(prepared_records["diagram.svg"], "packaged", "colour_type") == 0


def test_resizing_preserves_aspect_ratio_and_never_upscales(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        _, report = prepared(tmp_path, index, command, NORMALISED_IMAGES)

        oversize = records(report)["oversize.png"]
        width = measured(oversize, "packaged", "width")
        height = measured(oversize, "packaged", "height")
        assert (width, height) == MAXIMUM
        assert width / height == OVERSIZE[0] / OVERSIZE[1]
        assert measured(oversize, "packaged", "scale") == 53
        small = records(report)["progressive.jpg"]
        assert (measured(small, "packaged", "width"), measured(small, "packaged", "height")) == (
            measured(small, "source", "width"),
            measured(small, "source", "height"),
        )
        assert measured(small, "packaged", "scale") == 100


def test_transparency_survives_as_the_colour_type_the_profile_names(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        output, report = prepared(tmp_path, index, command, NORMALISED_IMAGES)

        entry = records(report)["alpha.webp"]
        assert entry["source"]["measured_media_type"] == "image/webp"
        assert entry["packaged"]["alpha"] is True
        published = media_resources(output)[entry["artifact"]["path"].removeprefix("EPUB/")]
        assert published.startswith(b"\x89PNG\r\n\x1a\n")


def test_the_svg_is_rasterised_by_the_pinned_renderer(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        _, report = prepared(tmp_path, index, command, NORMALISED_IMAGES)

        renderer = records(report)["diagram.svg"]["packaged"]["renderer"]
        assert renderer["tool"] == "resvg"
        assert renderer["matches_pinned_version"] is True
        assert renderer["system_fonts"] is False
        assert report["galley"]["dependencies"]["resvg"] == renderer["version"]
        assert report["galley"]["dependencies"]["pillow"]


def test_the_cover_is_a_direct_image_element_referencing_the_opf_cover(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        output, report = prepared(tmp_path, index, command, NORMALISED_IMAGES)

        cover = next(entry for entry in records(report).values() if entry["cover"] is True)
        assert cover["transform"] == "preserved"
        assert cover["artifact"]["cover"] is True
        assert cover["artifact"]["referenced"] is True
        document = next(href for href in spine_documents(output) if "cover" in href)
        sources = [src for href, src, _ in image_sources(output) if href == document]
        assert sources == [f"../{cover['artifact']['path'].removeprefix('EPUB/')}"]
        assert b"<svg" not in _markup(output, document)


def test_responsive_candidates_are_recorded_and_removed(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        _ = grayscale_png(tmp_path / "figure.png")
        output, report = prepared(tmp_path, index, command, RESPONSIVE_IMAGE)

        entry = records(report)["figure.png"]
        assert entry["srcset_candidates"] == ["figure.png 1x", "wide.png 2x"]
        assert entry["alt"] == "grey square"
        assert entry["title"] == "Square title"
        markup = b"".join(_markup(output, href) for href in spine_documents(output))
        assert b"srcset" not in markup
        assert b"sizes" not in markup
        assert report["artifact"]["conformance"]["counts"]["error"]["value"] == 0


def test_alt_and_title_stay_with_the_image_they_belong_to(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        output, report = prepared(tmp_path, index, command, NORMALISED_IMAGES)

        published = {src.removeprefix("../"): alt for _, src, alt in image_sources(output)}
        for entry in records(report).values():
            if entry["cover"] or entry["artifact"] is None:
                continue
            member = entry["artifact"]["path"].removeprefix("EPUB/")
            assert published[member] == entry["alt"]


def test_evidence_holds_deterministic_previews_without_claiming_a_verdict(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        _, report = prepared(tmp_path, index, command, NORMALISED_IMAGES)
        previews = tmp_path / f"book-{index}.galley" / "previews"

        entry = records(report)["oversize.png"]
        assert entry["previews"] == {
            "prepared": "previews/image-1-prepared.png",
            "source": "previews/image-1-source.png",
            "viewing": "previews/image-1-viewing.png",
        }
        viewing = previews / "image-1-viewing.png"
        assert viewing.is_file()
        assert len(_levels(viewing)) <= 4
        repeated = run_command(
            command,
            str(tmp_path / f"source-{index}.md"),
            "--output",
            str(tmp_path / f"again-{index}.epub"),
            *ARGUMENTS,
        )
        assert repeated.returncode == 0
        again = json.loads(repeated.stdout)
        assert (
            again["preparation"]["images"]["records"] == report["preparation"]["images"]["records"]
        )
        assert _preview_bytes(previews) == _preview_bytes(
            tmp_path / f"again-{index}.galley" / "previews"
        )
        judged = [
            observation
            for observation in report["observations"]
            if observation["name"] in {"colour-meaning-collapse", "diagram-text-legibility"}
        ]
        assert len(judged) == 2
        for observation in judged:
            assert observation["fired"] is None
            assert "previews/image-1-viewing.png" in observation["locations"]
        assert report["reading_verdict"] == {"value": "not_tested", "predicted": None}


def test_image_preservation_maps_every_reference_to_a_decoded_artifact_resource(
    tmp_path: Path,
) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        output, report = prepared(tmp_path, index, command, NORMALISED_IMAGES)

        preservation = report["preparation"]["images"]["preservation"]
        assert preservation["claimed"] is True
        assert preservation["mapped"]["value"] == REFERENCES
        assert preservation["unmapped"]["value"] == 0
        resources = {entry["sha256"] for entry in report["artifact"]["images"]["resources"]}
        assert {entry["packaged"]["sha256"] for entry in records(report).values()} == resources
        assert len(media_resources(output)) == REFERENCES
        assert report["compatibility"]
        for result in report["compatibility"]:
            assert result["verdict"] != "false"


def test_a_source_that_cannot_be_decoded_refuses_with_no_final_epub(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        _ = (tmp_path / "diagram.svg").write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'")
        source = write_markdown(tmp_path / f"broken-{index}.md", NORMALISED_IMAGES)
        output = tmp_path / f"broken-{index}.epub"

        result = run_command(command, str(source), "--output", str(output), *ARGUMENTS)

        assert result.returncode == 3
        report = json.loads(result.stdout)
        assert report["refusal"]["boundary"] == "image-processing-failure"
        assert report["refusal"]["stage"] == "image-preparation"
        assert [entry["reason"] for entry in report["refusal"]["fact"]["failures"]] == [
            "render-failure"
        ]
        assert not output.exists()


def test_human_output_names_what_the_images_became(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        transformable(tmp_path)
        source = write_markdown(tmp_path / f"human-{index}.md", NORMALISED_IMAGES)

        result = run_command(
            command,
            str(source),
            "--output",
            str(tmp_path / f"human-{index}.epub"),
            "--profile",
            "x4-crosspoint",
        )

        assert (result.returncode, result.stderr) == (0, "")
        assert "Images: 6 references to 6 resources, 1 preserved, 5 normalised\n" in result.stdout


def _markup(artifact: Path, href: str) -> bytes:
    member = next(name for name in names(artifact) if name.endswith(href))
    with zipfile.ZipFile(artifact) as archive:
        return archive.read(member)


def _preview_bytes(directory: Path) -> dict[str, bytes]:
    """Read one run's whole preview bundle, so a repeat run can be compared byte for byte."""

    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _levels(path: Path) -> set[int]:
    """Read the distinct grey values one preview carries, rather than trusting the renderer."""

    with Image.open(path) as opened:
        return set(opened.convert("L").tobytes())

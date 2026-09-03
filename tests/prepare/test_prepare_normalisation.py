"""Incompatible images become the profile's safe form, and the book proves every one survived."""

import json
from pathlib import Path
from typing import Any

from PIL import Image

from tests.support.image_fixtures import (
    NORMALISED_IMAGES,
    RESPONSIVE_IMAGE,
    colour_png,
    grayscale_png,
    progressive_jpeg,
    transparent_webp,
    vector_svg,
)
from tests.support.markdown_fixtures import write_markdown
from tests.support.prepared_epub import PreparedEpub
from tests.support.public_cli import prepare, run_cli

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


def records(report: Any) -> dict[str, Any]:
    return {entry["src"]: entry for entry in report["preparation"]["images"]["records"]}


def measured(entry: Any, side: str, key: str) -> Any:
    value = entry[side][key]
    return None if value is None else value["value"]


def test_preparation_normalises_images_and_preserves_their_artifact_relationships(
    tmp_path: Path,
) -> None:
    transformable(tmp_path)
    prepared_source = write_markdown(tmp_path / "source-0.md", NORMALISED_IMAGES)
    journey = prepare(tmp_path, prepared_source)
    output, report = journey.output, journey.report

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

    entry = records(report)["alpha.webp"]
    assert entry["source"]["measured_media_type"] == "image/webp"
    assert entry["packaged"]["alpha"] is True
    book = PreparedEpub(output)
    published = book.media_resources()[entry["artifact"]["path"].removeprefix("EPUB/")]
    assert published.startswith(b"\x89PNG\r\n\x1a\n")

    renderer = records(report)["diagram.svg"]["packaged"]["renderer"]
    assert renderer["tool"] == "resvg"
    assert renderer["matches_pinned_version"] is True
    assert renderer["system_fonts"] is False
    assert report["galley"]["dependencies"]["resvg"] == renderer["version"]
    assert report["galley"]["dependencies"]["pillow"]

    cover = next(entry for entry in records(report).values() if entry["cover"] is True)
    assert cover["transform"] == "preserved"
    assert cover["artifact"]["cover"] is True
    assert cover["artifact"]["referenced"] is True
    (document,) = book.cover_documents()
    sources = [src for _, src, _ in book.image_sources(role="cover")]
    assert sources == [f"../{cover['artifact']['path'].removeprefix('EPUB/')}"]
    assert b"<svg" not in book.member(document)

    published = {
        book.resource_for(document, src): alt for document, src, alt in book.image_sources()
    }
    for entry in records(report).values():
        if entry["cover"] or entry["artifact"] is None:
            continue
        member = entry["artifact"]["path"].removeprefix("EPUB/")
        assert published[member] == entry["alt"]

    preservation = report["preparation"]["images"]["preservation"]
    assert preservation["claimed"] is True
    assert preservation["mapped"]["value"] == REFERENCES
    assert preservation["unmapped"]["value"] == 0
    resources = {entry["sha256"] for entry in report["artifact"]["images"]["resources"]}
    assert {entry["packaged"]["sha256"] for entry in records(report).values()} == resources
    assert len(book.media_resources()) == REFERENCES
    assert report["compatibility"]
    for result in report["compatibility"]:
        assert result["verdict"] != "false"


def test_responsive_candidates_are_recorded_and_removed(tmp_path: Path) -> None:
    _ = grayscale_png(tmp_path / "figure.png")
    prepared_source = write_markdown(tmp_path / "source-0.md", RESPONSIVE_IMAGE)
    journey = prepare(tmp_path, prepared_source)
    output, report = journey.output, journey.report

    entry = records(report)["figure.png"]
    assert entry["srcset_candidates"] == ["figure.png 1x", "wide.png 2x"]
    assert entry["alt"] == "grey square"
    assert entry["title"] == "Square title"
    book = PreparedEpub(output)
    markup = b"".join(book.member(href) for href in book.spine_documents())
    assert b"srcset" not in markup
    assert b"sizes" not in markup
    assert report["artifact"]["conformance"]["counts"]["error"]["value"] == 0


def test_evidence_holds_deterministic_previews_without_claiming_a_verdict(tmp_path: Path) -> None:
    transformable(tmp_path)
    prepared_source = write_markdown(tmp_path / "source-0.md", NORMALISED_IMAGES)
    journey = prepare(tmp_path, prepared_source)
    _, report = journey.output, journey.report
    previews = journey.evidence / "previews"

    entry = records(report)["oversize.png"]
    assert entry["previews"] == {
        "prepared": "previews/image-1-prepared.png",
        "source": "previews/image-1-source.png",
        "viewing": "previews/image-1-viewing.png",
    }
    viewing = previews / "image-1-viewing.png"
    assert viewing.is_file()
    assert len(_levels(viewing)) <= 4
    repeated = run_cli(
        "prepare",
        str(tmp_path / "source-0.md"),
        "--output",
        str(tmp_path / "again-0.epub"),
        *ARGUMENTS,
    )
    assert repeated.returncode == 0
    again = json.loads(repeated.stdout)
    assert again["preparation"]["images"]["records"] == report["preparation"]["images"]["records"]
    assert _preview_bytes(previews) == _preview_bytes(tmp_path / "again-0.galley" / "previews")
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


def test_a_source_that_cannot_be_decoded_refuses_with_no_final_epub(tmp_path: Path) -> None:
    transformable(tmp_path)
    _ = (tmp_path / "diagram.svg").write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'")
    source = write_markdown(tmp_path / "broken-0.md", NORMALISED_IMAGES)
    output = tmp_path / "broken-0.epub"

    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS)

    assert result.returncode == 3
    report = json.loads(result.stdout)
    assert report["refusal"]["boundary"] == "image-processing-failure"
    assert report["refusal"]["stage"] == "image-preparation"
    assert [entry["reason"] for entry in report["refusal"]["fact"]["failures"]] == [
        "render-failure"
    ]
    assert not output.exists()


def test_human_output_names_what_the_images_became(tmp_path: Path) -> None:
    transformable(tmp_path)
    source = write_markdown(tmp_path / "human-0.md", NORMALISED_IMAGES)

    result = run_cli(
        "prepare",
        str(source),
        "--output",
        str(tmp_path / "human-0.epub"),
        "--profile",
        "x4-crosspoint",
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert "Images: 6 references to 6 resources, 1 preserved, 5 normalised\n" in result.stdout


def _preview_bytes(directory: Path) -> dict[str, bytes]:
    """Read one run's whole preview bundle, so a repeat run can be compared byte for byte."""

    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _levels(path: Path) -> set[int]:
    """Read the distinct grey values one preview carries, rather than trusting the renderer."""

    with Image.open(path) as opened:
        return set(opened.convert("L").tobytes())

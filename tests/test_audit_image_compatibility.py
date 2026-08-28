import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from tests.epub_fixtures import (
    CHAPTER_PATH,
    FIGURE_PATH,
    chapter,
    default_entries,
    jpeg,
    png,
    replace,
    svg,
    webp,
    without,
    write_epub,
)
from tests.public_cli import NO_EPUBCHECK, run_public_cli

FIGURE_BODY = '<p><img src="images/figure.png" alt="A measured figure"/></p>'


def audited(book: Path) -> dict[str, Any]:
    before = sha256(book.read_bytes()).hexdigest()
    results = run_public_cli(
        "audit", str(book), "--profile", "x4-crosspoint", "--json", environment=NO_EPUBCHECK
    )

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    assert sha256(book.read_bytes()).hexdigest() == before
    reports: list[dict[str, Any]] = [json.loads(result.stdout) for result in results]
    assert reports[0]["artifact"] == reports[1]["artifact"]
    return reports[0]


def with_figure(tmp_path: Path, data: bytes, name: str, body: str = FIGURE_BODY) -> dict[str, Any]:
    entries = replace(default_entries(), FIGURE_PATH, data)
    entries = replace(entries, CHAPTER_PATH, chapter(body))
    return audited(write_epub(tmp_path / name, entries))


def verdict(report: dict[str, Any], identifier: str) -> str:
    entry = next(
        candidate
        for candidate in report["compatibility"]
        if candidate["requirement_id"] == identifier
    )
    return str(entry["verdict"])


def observation(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entry for entry in report["observations"] if entry["name"] == name)


def figure(report: dict[str, Any]) -> dict[str, Any]:
    return next(
        resource
        for resource in report["artifact"]["images"]["resources"]
        if resource["path"] == FIGURE_PATH
    )


def test_image_facts_are_measured_from_the_resource_bytes(tmp_path: Path) -> None:
    data = png(sample_depth=8, colour_type=6, width=120, height=64)
    report = with_figure(tmp_path, data, "measured.epub")

    measured = figure(report)
    assert measured["measured_media_type"] == "image/png"
    assert measured["declared_media_type"] == "image/png"
    assert measured["width"] == {"basis": "measured", "unit": "pixels", "value": 120}
    assert measured["height"] == {"basis": "measured", "unit": "pixels", "value": 64}
    assert measured["sample_depth"] == {"basis": "measured", "unit": "bits", "value": 8}
    assert measured["colour_type"] == {"basis": "measured", "unit": "colour type", "value": 6}
    assert measured["alpha"] is True
    assert measured["byte_size"]["value"] == len(data)
    assert measured["sha256"] == sha256(data).hexdigest()
    assert measured["referenced"] is True


def test_a_declared_media_type_never_stands_in_for_the_measured_one(tmp_path: Path) -> None:
    report = with_figure(tmp_path, webp(), "mislabelled.epub")

    measured = figure(report)
    assert measured["declared_media_type"] == "image/png"
    assert measured["measured_media_type"] == "image/webp"
    assert measured["device_support"] == "false"
    assert verdict(report, "image-media-type") == "false"
    assert verdict(report, "png-decoding") == "not_applicable"


@pytest.mark.parametrize(
    ("sample_depth", "colour_type", "expected"),
    ((8, 0, "true"), (8, 3, "true"), (8, 6, "true"), (16, 0, "false"), (4, 0, "unknown")),
)
def test_png_support_follows_the_profile_matrix(
    tmp_path: Path, sample_depth: int, colour_type: int, expected: str
) -> None:
    data = png(sample_depth=sample_depth, colour_type=colour_type)
    report = with_figure(tmp_path, data, f"png-{sample_depth}-{colour_type}.epub")

    assert verdict(report, "png-decoding") == expected
    assert verdict(report, "image-media-type") == "true"


@pytest.mark.parametrize(
    ("progressive", "components", "expected"),
    ((False, 1, "true"), (False, 3, "true"), (True, 3, "false"), (True, 1, "unknown")),
)
def test_jpeg_support_follows_the_profile_matrix(
    tmp_path: Path, progressive: bool, components: int, expected: str
) -> None:
    data = jpeg(progressive=progressive, components=components)
    report = with_figure(tmp_path, data, f"jpeg-{progressive}-{components}.epub")

    assert verdict(report, "jpeg-decoding") == expected
    assert verdict(report, "png-decoding") == "not_applicable"


def test_an_incompatible_media_type_is_reported_against_the_profile(tmp_path: Path) -> None:
    report = with_figure(tmp_path, svg(), "svg.epub")

    assert figure(report)["measured_media_type"] == "image/svg+xml"
    assert verdict(report, "image-media-type") == "false"


def test_an_image_free_artifact_is_not_applicable(tmp_path: Path) -> None:
    entries = without(default_entries(), FIGURE_PATH)
    entries = replace(entries, CHAPTER_PATH, chapter("<p>No images here.</p>"))
    report = audited(write_epub(tmp_path / "image-free.epub", entries))

    for identifier in ("image-media-type", "png-decoding", "jpeg-decoding"):
        assert verdict(report, identifier) == "not_applicable"
    assert report["artifact"]["images"]["resources"] == []


def test_unrenderable_images_is_computed_from_measured_bytes(tmp_path: Path) -> None:
    report = with_figure(tmp_path, webp(), "unrenderable.epub")

    entry = observation(report, "unrenderable-images")
    assert entry["evidence"] == "computable"
    assert entry["consequence"] == "content-loss"
    assert entry["applicability"] is True
    assert entry["fired"] is True
    assert entry["measurement"]["value"] == 1
    assert entry["locations"] == [FIGURE_PATH]


def test_a_device_verified_image_leaves_unrenderable_images_unfired(tmp_path: Path) -> None:
    report = with_figure(tmp_path, png(), "renderable.epub")

    assert observation(report, "unrenderable-images")["fired"] is False


def test_alt_text_fallback_absence_fires_only_with_an_unrenderable_image(tmp_path: Path) -> None:
    blank = '<p><img src="images/figure.png" alt=""/></p>'

    with_alt = with_figure(tmp_path, webp(), "unrenderable-with-alt.epub")
    without_alt = with_figure(tmp_path, webp(), "unrenderable-blank-alt.epub", blank)
    renderable = with_figure(tmp_path, png(), "renderable-blank-alt.epub", blank)

    assert observation(with_alt, "alt-text-fallback-absence")["fired"] is False
    assert observation(without_alt, "alt-text-fallback-absence")["fired"] is True
    assert observation(renderable, "alt-text-fallback-absence")["fired"] is False


@pytest.mark.parametrize("name", ("diagram-text-legibility", "colour-meaning-collapse"))
def test_agent_judged_image_observations_stay_applicable_and_null(
    tmp_path: Path, name: str
) -> None:
    report = with_figure(tmp_path, png(), f"judgement-{name}.epub")

    entry = observation(report, name)
    assert entry["evidence"] == "flaggable"
    assert entry["applicability"] is True
    assert entry["fired"] is None
    assert entry["measurement"] is None


def test_a_broken_image_reference_is_reported_apart_from_decoding(tmp_path: Path) -> None:
    body = '<p><img src="images/absent.png" alt="Gone"/></p>'
    entries = replace(default_entries(), CHAPTER_PATH, chapter(body))
    report = audited(write_epub(tmp_path / "broken-image.epub", entries))

    images = report["artifact"]["images"]
    assert images["unresolved_references"] == [
        {"document": CHAPTER_PATH, "src": "images/absent.png"}
    ]
    assert verdict(report, "image-media-type") == "not_applicable"
    assert figure(report)["referenced"] is False
    assert figure(report)["displayed"] is False


def test_audit_claims_no_image_preservation_without_a_canonical_document(
    tmp_path: Path,
) -> None:
    report = with_figure(tmp_path, png(), "preservation.epub")

    preservation = report["artifact"]["images"]["image_preservation"]
    assert preservation["claimed"] is False
    assert "Canonical Document" in str(preservation["reason"])
    assert report["canonical_document"] is None


@pytest.mark.parametrize(
    ("data", "requirement_id"),
    (
        (png(sample_depth=16, colour_type=0), "png-decoding"),
        (jpeg(progressive=True), "jpeg-decoding"),
    ),
)
def test_a_decoding_failure_makes_the_image_unrenderable(
    tmp_path: Path, data: bytes, requirement_id: str
) -> None:
    report = with_figure(tmp_path, data, f"decoding-{requirement_id}.epub")

    assert verdict(report, "image-media-type") == "true"
    assert verdict(report, requirement_id) == "false"
    assert figure(report)["device_support"] == "false"
    entry = observation(report, "unrenderable-images")
    assert entry["fired"] is True
    assert entry["locations"] == [FIGURE_PATH]


def test_a_decoding_failure_with_blank_alt_also_fires_the_fallback_observation(
    tmp_path: Path,
) -> None:
    blank = '<p><img src="images/figure.png" alt=""/></p>'
    report = with_figure(tmp_path, png(sample_depth=16), "sixteen-bit-blank.epub", blank)

    assert observation(report, "alt-text-fallback-absence")["fired"] is True
    assert observation(report, "alt-text-fallback-absence")["locations"] == [FIGURE_PATH]


@pytest.mark.parametrize(
    "data",
    (
        png()[:-6],
        jpeg()[:-2],
        webp(truncated=True),
    ),
)
def test_truncated_bytes_are_never_reported_as_device_verified(tmp_path: Path, data: bytes) -> None:
    report = with_figure(tmp_path, data, "truncated.epub")

    measured = figure(report)
    assert measured["intact"] is False
    assert measured["device_support"] == "unknown"
    assert "end marker" in str(measured["note"])
    assert observation(report, "unrenderable-images")["fired"] is True


def test_an_unreferenced_resource_never_drives_a_requirement_verdict(tmp_path: Path) -> None:
    entries = replace(default_entries(), FIGURE_PATH, jpeg(progressive=True))
    entries = replace(entries, CHAPTER_PATH, chapter("<p>The figure is never shown.</p>"))
    report = audited(write_epub(tmp_path / "orphan.epub", entries))

    assert figure(report)["displayed"] is False
    assert figure(report)["measured_media_type"] == "image/jpeg"
    assert verdict(report, "jpeg-decoding") == "not_applicable"
    assert observation(report, "unrenderable-images")["applicability"] is False

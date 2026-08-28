"""Profile-directed SVG Cover Artwork becomes deterministic, evidenced raster covers."""

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image

from galley.profile.loading import load_profile
from galley.tools import resvg
from tests.markdown_fixtures import write_markdown
from tests.prepared_epub import media_resources
from tests.public_cli import public_cli_commands, run_command

FONT = {
    "family": "Atkinson Hyperlegible",
    "file": "AtkinsonHyperlegible-Regular.otf",
    "license": "SIL Open Font License 1.1",
    "license_file": "AtkinsonHyperlegible-OFL.txt",
    "license_sha256": "64b9cae8727cb41ea9e8843103e69647c82383f3a902e2bb39b2c5d92083b6e1",
    "matches_expected_sha256": True,
    "sha256": "4a0397a3709c5fc99e38d05469dcfbf1b3481196e89a01b7377f3163b188258e",
    "source_commit": "1cb311624b2ddf88e9e37873999d165a8cd28b46",
    "style": "Regular",
    "version": "1.006",
}
DIRECTIONS = {
    "x4-crosspoint": {
        "canvas": {"width_px": 480, "height_px": 800},
        "colour_model": "grayscale",
        "colour_type": 0,
        "density": "restrained",
        "shape_scale": "large",
        "type_scale": "large",
        "visual_hierarchy": "one-dominant-form",
        "typography_role": "work-responsive",
        "thumbnail_intent": "legible-at-device-cover-thumbnail",
        "viewing_preview": {"kind": "quantised", "levels": 4},
    },
    "kindle-ios-personal-documents": {
        "canvas": {"width_px": 1600, "height_px": 2560},
        "colour_model": "rgb",
        "colour_type": 2,
        "density": "restrained",
        "shape_scale": "dominant",
        "type_scale": "flexible",
        "visual_hierarchy": "one-dominant-form",
        "typography_role": "work-responsive",
        "thumbnail_intent": "legible-at-kindle-library-thumbnail",
        "viewing_preview": {"kind": "prepared-colour", "levels": None},
    },
}


def _svg(profile: str, width: int, height: int) -> str:
    if profile == "x4-crosspoint":
        background, foreground, accent = "#fff", "#000", "#555"
        shape = f'<circle cx="{width // 2}" cy="240" r="150" fill="{accent}"/>'
    else:
        background, foreground, accent = "#102040", "#f6e7b0", "#e45172"
        shape = f'<path d="M0 0 L{width} 0 L{width} 900 Z" fill="{accent}"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="{background}"/>{shape}'
        f'<text x="{width // 2}" y="{height // 2}" text-anchor="middle" '
        f'font-family="Atkinson Hyperlegible" font-size="{width // 7}" fill="{foreground}">'
        "A DISTINCT COVER</text>"
        f'<text x="{width // 2}" y="{height // 2 + width // 7}" text-anchor="middle" '
        f'font-family="Atkinson Hyperlegible" font-size="{width // 14}" fill="{foreground}">'
        "EXAMPLE AUTHOR</text></svg>"
    )


def _prepare(
    tmp_path: Path, profile: str, index: int, command: list[str]
) -> tuple[Path, Path, Any]:
    direction = DIRECTIONS[profile]
    canvas = cast(dict[str, int], direction["canvas"])
    directory = tmp_path / f"{profile}-{index}"
    directory.mkdir()
    _ = (directory / "cover.svg").write_text(
        _svg(profile, canvas["width_px"], canvas["height_px"]), encoding="utf-8"
    )
    source = write_markdown(
        directory / "source.md",
        "---\ntitle: A Distinct Cover\nauthor: Example Author\ncover-image: cover.svg\n---\n\n"
        "# A Distinct Cover\n\nA work with its own visual identity.\n",
    )
    output = directory / "book.epub"
    evidence = directory / "evidence"
    result = run_command(
        command,
        str(source),
        "--output",
        str(output),
        "--evidence-dir",
        str(evidence),
        "--profile",
        profile,
        "--json",
    )
    assert (result.returncode, result.stderr) == (0, "")
    return output, evidence, json.loads(result.stdout)


def _cover(report: Any) -> Any:
    return next(
        entry for entry in report["preparation"]["images"]["records"] if entry["cover"] is True
    )


def test_profiles_expose_validated_separate_cover_directions() -> None:
    for profile_id, expected in DIRECTIONS.items():
        profile = load_profile(profile_id)
        activations = cast(dict[str, dict[str, object]], profile["activation"])
        direction = cast(dict[str, object], activations["cover_artwork"]["value"])

        profile_values = {key: value for key, value in expected.items() if key != "colour_type"}
        assert {key: direction[key] for key in profile_values} == profile_values
        assert direction["contrast"] == "high"
        assert direction["separate_composition"] is True
        assert direction is not activations["image_fit"]["value"]


@pytest.mark.parametrize("profile", tuple(DIRECTIONS))
def test_public_prepare_makes_distinct_deterministic_evidenced_raster_covers(
    tmp_path: Path, profile: str
) -> None:
    outputs = [
        _prepare(tmp_path, profile, index, command)
        for index, command in enumerate(public_cli_commands("prepare"))
    ]
    payloads: list[bytes] = []

    for output, evidence, report in outputs:
        direction = DIRECTIONS[profile]
        canvas = cast(dict[str, int], direction["canvas"])
        record = _cover(report)
        renderer = record["packaged"]["renderer"]
        assert record["src"] == "cover.svg"
        assert record["transform"] == "normalised"
        assert record["packaged"]["measured_media_type"] == "image/png"
        assert record["packaged"]["sample_depth"]["value"] == 8
        assert record["packaged"]["colour_type"]["value"] == direction["colour_type"]
        assert (record["packaged"]["width"]["value"], record["packaged"]["height"]["value"]) == (
            canvas["width_px"],
            canvas["height_px"],
        )
        assert renderer["tool"] == "resvg"
        assert renderer["matches_pinned_version"] is True
        assert renderer["messages"] == []
        assert renderer["system_fonts"] is False
        assert renderer["fonts"] == [FONT]
        assert record["artifact"]["cover"] is True
        assert record["artifact"]["referenced"] is True
        assert record["artifact"]["sha256"] == record["packaged"]["sha256"]
        member = record["artifact"]["path"].removeprefix("EPUB/")
        payload = media_resources(output)[member]
        assert hashlib.sha256(payload).hexdigest() == record["packaged"]["sha256"]
        payloads.append(payload)
        assert not any(path.endswith(".svg") for path in media_resources(output))

        previews = record["previews"]
        with Image.open(evidence / previews["prepared"]) as prepared:
            assert prepared.size == (canvas["width_px"], canvas["height_px"])
        if profile == "x4-crosspoint":
            with Image.open(evidence / previews["viewing"]) as viewed:
                assert len(set(viewed.convert("L").tobytes())) <= 4
        else:
            assert "viewing" not in previews

    assert payloads[0] == payloads[1]


@pytest.mark.parametrize(
    ("payload", "reason"),
    ((None, "missing-resource"), (b"<svg xmlns='http://www.w3.org/2000/svg'", "render-failure")),
)
def test_a_missing_or_unrenderable_requested_cover_refuses(
    tmp_path: Path, payload: bytes | None, reason: str
) -> None:
    source = write_markdown(
        tmp_path / f"{reason}.md",
        "---\ntitle: Broken Cover\ncover-image: cover.svg\n---\n\n# Broken Cover\n",
    )
    if payload is not None:
        _ = (tmp_path / "cover.svg").write_bytes(payload)
    output = tmp_path / f"{reason}.epub"

    result = run_command(
        public_cli_commands("prepare")[0],
        str(source),
        "--output",
        str(output),
        "--profile",
        "x4-crosspoint",
        "--json",
    )

    assert (result.returncode, result.stderr) == (3, "")
    report = json.loads(result.stdout)
    assert report["refusal"]["boundary"] == "image-processing-failure"
    assert report["refusal"]["fact"]["failures"] == [
        {"reason": reason, "reference": "cover-image", "src": "cover.svg"}
    ]
    assert not output.exists()


def test_a_changed_bundled_cover_font_refuses_rasterisation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fonts = tmp_path / "bundled-fonts"
    fonts.mkdir()
    _ = (fonts / resvg.FONT_FILE).write_bytes(b"not the recorded font")
    _ = (fonts / resvg.FONT_LICENSE_FILE).write_bytes(
        (resvg.FONT_DIRECTORY / resvg.FONT_LICENSE_FILE).read_bytes()
    )
    monkeypatch.setattr(resvg, "FONT_DIRECTORY", fonts)

    rendering = resvg.rasterise(b"<svg xmlns='http://www.w3.org/2000/svg'/>", tmp_path / "work")

    assert rendering.data is None
    assert rendering.reason == "font-unavailable"
    assert rendering.detail == "bundled cover font does not match its recorded SHA-256"
    assert rendering.facts["fonts"] == [
        {
            **FONT,
            "matches_expected_sha256": False,
            "sha256": hashlib.sha256(b"not the recorded font").hexdigest(),
        }
    ]

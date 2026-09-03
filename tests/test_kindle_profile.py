"""Kindle for iOS is a packaged, empirically observed personal-document Device Profile."""

import json
from pathlib import Path
from typing import Any, cast

from galley.profile.loading import load_profile
from tests.image_fixtures import transparent_webp, vector_svg
from tests.markdown_fixtures import write_markdown
from tests.public_cli import run_cli

PROFILE = "kindle-ios-personal-documents"
OBSERVATIONS = [
    "ingress-conversion-acceptance",
    "library-title-presentation",
    "library-author-presentation",
    "library-cover-presentation",
    "navigation-usability",
    "typography-preservation",
    "colour-image-presentation",
    "footnote-usability",
    "theme-adaptation",
    "large-text-adaptation",
]
SOURCE = """---
title: A Kindle Probe
author: Example Author
cover-image: cover.svg
---

# A chapter

One transparent ![colour probe](alpha.webp) for the conversion path.[^1]

[^1]: A footnote to observe after conversion.
"""


def _json(result: Any) -> Any:
    assert (result.returncode, result.stderr) == (0, "")
    return json.loads(result.stdout)


def _observation_names(report: Any) -> list[str]:
    entries = cast(list[dict[str, object]], report["observations"])
    assert all(entry["applicability"] is None and entry["fired"] is None for entry in entries)
    return [str(entry["name"]) for entry in entries]


def test_profile_records_the_observed_app_identity_and_product_boundaries_explicitly() -> None:
    profile = load_profile(PROFILE)

    assert profile["profile_version"] == "0.3.0"
    assert profile["device"] == "iPhone 15 Pro"
    assert profile["reader"] == "Kindle for iOS"
    assert profile["software"] == {
        "kind": "application",
        "version": "7.65",
        "observed_at": "2026-08-27",
        "operating_system": {"name": "iOS", "version": "26.6"},
        "queued_changes": [],
    }
    requirement = cast(list[dict[str, object]], profile["requirements"])[0]
    assert requirement["id"] == "personal-document-conversion"
    assert "Galley-produced reflowable EPUB" in str(requirement["statement"])
    assert {claim["kind"] for claim in cast(list[dict[str, str]], requirement["provenance"])} == {
        "device-test",
        "product-decision",
        "spec-document",
    }
    assert {entry["kind"] for entry in cast(list[dict[str, object]], profile["behaviour"])} == {
        "product-decision"
    }
    non_requirements = cast(list[dict[str, object]], profile["non_requirements"])
    assert {entry["id"] for entry in non_requirements} == {
        "kdp-publication",
        "raw-usb-epub",
        "arbitrary-epub-input",
        "automated-submission",
        "raw-epub-runtime",
    }


def test_public_profile_show_exposes_the_assembled_kindle_contract() -> None:
    result = run_cli("profiles", "show", PROFILE, "--json")

    profiles = _json(result)

    assert profiles["id"] == PROFILE
    assert [entry["name"] for entry in profiles["observations"]] == OBSERVATIONS


def test_profile_requests_rgb_rasterised_svg_and_a_separate_exact_cover_canvas() -> None:
    profile = load_profile(PROFILE)
    activations = cast(dict[str, dict[str, object]], profile["activation"])
    encoding = cast(dict[str, object], activations["image_encoding"]["value"])
    fit = cast(dict[str, object], activations["image_fit"]["value"])
    cover = cast(dict[str, object], activations["cover_artwork"]["value"])

    assert encoding["colour_model"] == "rgb"
    assert (encoding["opaque_colour_type"], encoding["alpha_colour_type"]) == (2, 6)
    assert encoding["rasterize_svg"] is True
    assert encoding["preserve_compatible_fitting_bytes"] is False
    assert (fit["max_width_px"], fit["max_height_px"]) == (1600, 2560)
    assert cover["canvas"] == {"width_px": 1600, "height_px": 2560}
    assert cover["colour_model"] == "rgb"
    assert "cover_artwork" not in {
        entry["id"] for entry in cast(list[dict[str, object]], profile["requirements"])
    }


def test_public_workflows_keep_kindles_post_conversion_observations_unawarded(
    tmp_path: Path,
) -> None:
    source = write_markdown(tmp_path / "probe.md", SOURCE)
    _ = vector_svg(tmp_path / "cover.svg", width=1600, height=2560)
    _ = transparent_webp(tmp_path / "alpha.webp")

    inspected = _json(run_cli("inspect", str(source), "--profile", PROFILE, "--json"))
    assert _observation_names(inspected) == OBSERVATIONS

    output = tmp_path / "probe.epub"
    prepared = _json(
        run_cli("prepare", str(source), "--output", str(output), "--profile", PROFILE, "--json")
    )
    assert _observation_names(prepared) == OBSERVATIONS
    records = {
        entry["src"]: entry
        for entry in cast(list[dict[str, Any]], prepared["preparation"]["images"]["records"])
    }
    assert records["cover.svg"]["packaged"]["colour_type"]["value"] == 2
    assert records["alpha.webp"]["packaged"]["colour_type"]["value"] == 6

    audited = _json(run_cli("audit", str(output), "--profile", PROFILE, "--json"))
    assert _observation_names(audited) == OBSERVATIONS
    assert audited["artifact"]["conformance"]["valid"] is True
    assert {entry["id"] for entry in audited["artifact"]["conformance"]["non_requirements"]} == {
        "kdp-publication",
        "raw-usb-epub",
        "arbitrary-epub-input",
        "automated-submission",
        "raw-epub-runtime",
    }

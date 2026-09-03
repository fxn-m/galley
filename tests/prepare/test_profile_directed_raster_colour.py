"""Device Profile data, not a named reader, selects prepared raster colour."""

from copy import deepcopy
from pathlib import Path
from typing import cast

from galley.images.facts import IMAGES_PREPARED
from galley.images.measurement import measure_image
from galley.images.normalisation import ImageRule, image_rule, normalise
from galley.images.resolution import ResourceOrigin
from galley.images.resources import PackagedResource, ResourcePreparation
from galley.profile.loading import load_profile
from tests.support.image_fixtures import colour_png, transparent_webp, vector_svg


def _rule(
    colour_model: str, *, opaque_colour_type: int, alpha_colour_type: int
) -> tuple[dict[str, object], ImageRule]:
    """Return the X4 profile with only its generic output policy varied."""

    profile = deepcopy(load_profile("x4-crosspoint"))
    activations = cast(dict[str, object], profile["activation"])
    image_encoding = cast(dict[str, object], activations["image_encoding"])
    value = cast(dict[str, object], image_encoding["value"])
    value.update(
        colour_model=colour_model,
        opaque_colour_type=opaque_colour_type,
        alpha_colour_type=alpha_colour_type,
    )
    return profile, image_rule(profile)


def test_rgb_policy_produces_eight_bit_truecolour_with_and_without_alpha(tmp_path: Path) -> None:
    _, rule = _rule("rgb", opaque_colour_type=2, alpha_colour_type=6)
    sources = (
        colour_png(tmp_path / "opaque.png").read_bytes(),
        transparent_webp(tmp_path / "alpha.webp").read_bytes(),
    )

    produced = [
        normalise(data, measure_image(data), rule, tmp_path / f"work-{index}")
        for index, data in enumerate(sources)
    ]

    assert [result.reason for result in produced] == [None, None]
    assert [result.measurement.sample_depth for result in produced if result.measurement] == [8, 8]
    assert [result.measurement.colour_type for result in produced if result.measurement] == [2, 6]


def test_svg_rasterisation_uses_the_same_rgb_policy(tmp_path: Path) -> None:
    _, rule = _rule("rgb", opaque_colour_type=2, alpha_colour_type=6)
    data = vector_svg(tmp_path / "diagram.svg").read_bytes()

    produced = normalise(data, measure_image(data), rule, tmp_path / "svg-work")

    assert produced.reason is None
    assert produced.renderer is not None
    assert produced.measurement is not None
    assert (produced.measurement.sample_depth, produced.measurement.colour_type) == (8, 2)


def test_measured_output_must_match_the_selected_policy(tmp_path: Path) -> None:
    _, inconsistent = _rule("grayscale", opaque_colour_type=2, alpha_colour_type=6)
    data = colour_png(tmp_path / "source.png").read_bytes()

    produced = normalise(data, measure_image(data), inconsistent, tmp_path / "work")

    assert produced.data is None
    assert produced.measurement is None
    assert produced.reason == "unexpected-encoding"


def test_colour_policy_does_not_rewrite_compatible_fitting_bytes(tmp_path: Path) -> None:
    profile, _ = _rule("rgb", opaque_colour_type=2, alpha_colour_type=6)
    source = colour_png(tmp_path / "source.png")

    preparation = ResourcePreparation(
        profile=profile,
        origin=ResourceOrigin(directory=tmp_path),
        workspace=tmp_path / "packaged",
    )
    resource = preparation.resolve(str(source), "image-1")

    assert isinstance(resource, PackagedResource)
    assert resource.transform == "preserved"
    assert resource.packaged.path.read_bytes() == source.read_bytes()


def test_report_narration_describes_profile_selected_bytes_without_a_colour_claim() -> None:
    assert "profile-selected 8-bit PNG colour model" in IMAGES_PREPARED
    assert "Source, prepared, and viewing bytes are reported separately" in IMAGES_PREPARED
    assert "greyscale PNG" not in IMAGES_PREPARED
    assert "makes no claim" in IMAGES_PREPARED

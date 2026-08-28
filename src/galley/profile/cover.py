"""Validate the profile direction for agent-authored Cover Artwork."""

from pathlib import Path

from galley.profile.reading import ProfileError, mapping, require_string

RASTER_COLOUR_TYPES = {
    "grayscale": (0, 4),
    "rgb": (2, 6),
}
COVER_DIRECTION_FIELDS = {
    "canvas",
    "colour_model",
    "contrast",
    "density",
    "type_scale",
    "shape_scale",
    "visual_hierarchy",
    "typography_role",
    "thumbnail_intent",
    "viewing_preview",
    "font_family",
    "separate_composition",
    "source_format",
    "packaged_format",
}


def validate_cover_artwork(entry: dict[str, object], path: Path) -> None:
    """Validate the creative direction separately from ordinary image compatibility."""

    label = f"{path}: activation cover_artwork.value"
    value = mapping(entry.get("value"), label)
    if set(value) != COVER_DIRECTION_FIELDS:
        fields = ", ".join(sorted(COVER_DIRECTION_FIELDS))
        raise ProfileError(f"{label} must name exactly {fields}")
    canvas = mapping(value.get("canvas"), f"{label}.canvas")
    if set(canvas) != {"width_px", "height_px"}:
        raise ProfileError(f"{label}.canvas must name width_px and height_px")
    _ = _positive_integer(canvas.get("width_px"), f"{label}.canvas.width_px")
    _ = _positive_integer(canvas.get("height_px"), f"{label}.canvas.height_px")
    colour_model = require_string(value.get("colour_model"), f"{label}.colour_model")
    if colour_model not in RASTER_COLOUR_TYPES:
        raise ProfileError(f"{label}: unknown raster colour model {colour_model}")
    for field in (
        "contrast",
        "density",
        "type_scale",
        "shape_scale",
        "visual_hierarchy",
        "typography_role",
        "thumbnail_intent",
    ):
        require_string(value.get(field), f"{label}.{field}")
    if value.get("font_family") != "Atkinson Hyperlegible":
        raise ProfileError(f"{label}.font_family must name the bundled cover font")
    if value.get("separate_composition") is not True:
        raise ProfileError(f"{label}.separate_composition must be true")
    if value.get("source_format") != "svg" or value.get("packaged_format") != "png":
        raise ProfileError(f"{label} must direct SVG source to packaged PNG")
    preview = mapping(value.get("viewing_preview"), f"{label}.viewing_preview")
    if set(preview) != {"kind", "levels"}:
        raise ProfileError(f"{label}.viewing_preview must name kind and levels")
    kind = require_string(preview.get("kind"), f"{label}.viewing_preview.kind")
    levels = preview.get("levels")
    if kind == "quantised":
        if _positive_integer(levels, f"{label}.viewing_preview.levels") < 2:
            raise ProfileError(f"{label}.viewing_preview.levels must be at least 2")
    elif kind != "prepared-colour" or levels is not None:
        raise ProfileError(f"{label}.viewing_preview is not a supported preview policy")


def validate_cover_pipeline(activation: dict[str, object], path: Path) -> None:
    """Keep the cover direction coherent with the raster path that packages it."""

    cover_entry = mapping(activation.get("cover_artwork"), f"{path}: activation cover_artwork")
    cover = mapping(cover_entry.get("value"), f"{path}: activation cover_artwork.value")
    encoding = mapping(
        mapping(activation.get("image_encoding"), f"{path}: activation image_encoding").get(
            "value"
        ),
        f"{path}: activation image_encoding.value",
    )
    fit = mapping(
        mapping(activation.get("image_fit"), f"{path}: activation image_fit").get("value"),
        f"{path}: activation image_fit.value",
    )
    if cover.get("colour_model") != encoding.get("colour_model"):
        raise ProfileError(f"{path}: cover and image raster colour models disagree")
    canvas = mapping(cover.get("canvas"), f"{path}: activation cover_artwork.value.canvas")
    dimensions = (("width_px", "max_width_px"), ("height_px", "max_height_px"))
    for cover_name, fit_name in dimensions:
        dimension = _positive_integer(canvas.get(cover_name), f"{path}: cover {cover_name}")
        maximum = _positive_integer(fit.get(fit_name), f"{path}: image fit {fit_name}")
        if dimension > maximum:
            raise ProfileError(f"{path}: cover canvas exceeds image fit {fit_name}")
    preview = mapping(
        cover.get("viewing_preview"), f"{path}: activation cover_artwork.value.viewing_preview"
    )
    if preview.get("levels") != encoding.get("viewing_levels"):
        raise ProfileError(f"{path}: cover and image viewing preview levels disagree")


def _positive_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProfileError(f"{label}: expected a positive integer")
    return value

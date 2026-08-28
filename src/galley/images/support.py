"""Ask a Device Profile whether it renders one measured image.

The question is the same wherever the bytes came from: a resource `audit` read out of a package
and a source resource `prepare` has just resolved are both answered by the same recorded support
matrices. Nothing here decides which encodings are compatible — every pair comes from profile
data, which makes a retracted claim a data change.
"""

from typing import cast

from galley.profile.compatibility import Verdict, aggregate, to_verdict
from galley.json_reading import mapping, sequence, text
from galley.images.measurement import ImageMeasurement
from galley.profile.loading import image_requirements, requirement

MATRIX_FIELDS = {
    "sample_depth": "sample_depth",
    "colour_types": "colour_type",
    "scan_mode": "scan_mode",
    "colour_models": "colour_model",
}


def applies_to(
    profile: dict[str, object], requirement_id: str, measurement: ImageMeasurement
) -> bool:
    """Ask the profile, not the code, which images one requirement covers."""

    stated = mapping(requirement(profile, requirement_id).get("applies_to"))
    media_types = sequence(stated.get("measured_media_types"))
    return not media_types or measurement.media_type in media_types


def support_for(
    profile: dict[str, object], requirement_id: str, measurement: ImageMeasurement
) -> Verdict:
    """Judge one image against one requirement's recorded support matrix."""

    if not measurement.intact:
        return "unknown"
    matrix = mapping(requirement(profile, requirement_id).get("support"))
    if _matches(matrix.get("incompatible"), measurement):
        return "false"
    if _matches(matrix.get("compatible"), measurement):
        return "true"
    return to_verdict(text(matrix.get("unlisted")))


def device_support(profile: dict[str, object], measurement: ImageMeasurement) -> Verdict:
    """Join one measurement to every image requirement that covers it."""

    return aggregate(
        [
            support_for(profile, requirement_id, measurement)
            for requirement_id in image_requirements(profile)
            if applies_to(profile, requirement_id, measurement)
        ]
    )


def _matches(entries: object, measurement: ImageMeasurement) -> bool:
    for entry in sequence(entries):
        if isinstance(entry, str):
            if entry == measurement.media_type:
                return True
            continue
        if _matches_shape(mapping(entry), measurement):
            return True
    return False


def _matches_shape(shape: dict[str, object], measurement: ImageMeasurement) -> bool:
    if not shape or any(key not in MATRIX_FIELDS for key in shape):
        return False
    for key, expected in shape.items():
        measured = cast(object, getattr(measurement, MATRIX_FIELDS[key]))
        allowed = sequence(cast(object, expected)) if isinstance(expected, list) else [expected]
        if measured is None or measured not in allowed:
            return False
    return True

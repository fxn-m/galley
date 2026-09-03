"""Hold the two authored record shapes to the separation between the three layers.

These shapes are the only place the agent's and the human's artifacts are decided, so the gate on
them has to fail for the reasons that matter: a Reading Verdict appearing in the agent's record,
a vocabulary drifting from the Registry, and a read whose bytes were rewritten on the device.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from scripts.checkrecords import (
    ASSESSMENT,
    READING_RECORD,
    RESOURCES,
    SCHEMAS,
    RecordShapeError,
    flaggable_names,
    report_verdicts,
    validate_record_shapes,
)

from galley.observations import OBSERVATION_NAMES


def test_the_shipped_record_shapes_are_valid() -> None:
    validate_record_shapes(RESOURCES)


def test_the_flaggable_set_is_the_registrys_and_not_a_second_list() -> None:
    """Five names, taken from the Registry rather than copied beside it."""

    assert flaggable_names() == [
        "colour-meaning-collapse",
        "alignment-meaning-flattening",
        "boundary-chrome-presence",
        "diagram-text-legibility",
        "link-footnote-dilution",
    ]
    assert set(flaggable_names()) < set(OBSERVATION_NAMES)


def test_the_agent_record_may_not_grow_a_reading_verdict(tmp_path: Path) -> None:
    """The boundary is structural: the shape has nowhere to write the human's answer."""

    resources = _edited(tmp_path, ASSESSMENT, _add_property("reading_verdict", {"type": "string"}))

    with pytest.raises(RecordShapeError, match="not the agent's"):
        validate_record_shapes(resources)


def test_the_agent_record_may_not_settle_a_computable_observation(tmp_path: Path) -> None:
    """A finding on a name the CLI measures would be a second answer to a settled question."""

    def widen(schema: dict[str, object]) -> None:
        finding = _at(schema, "$defs", "finding", "properties", "observation")
        finding["enum"] = [*flaggable_names(), "code-block-reflow"]

    resources = _edited(tmp_path, ASSESSMENT, widen)

    with pytest.raises(RecordShapeError, match="observation"):
        validate_record_shapes(resources)


def test_a_reading_record_that_records_no_read_is_rejected(tmp_path: Path) -> None:
    """`not_tested` is the absence of this record, so it cannot be one of its values."""

    def widen(schema: dict[str, object]) -> None:
        _at(schema, "properties", "reading_verdict")["enum"] = report_verdicts()

    resources = _edited(tmp_path, READING_RECORD, widen)

    with pytest.raises(RecordShapeError, match="reading_verdict"):
        validate_record_shapes(resources)


def test_a_read_with_optimize_left_on_is_rejected(tmp_path: Path) -> None:
    """Optimize rewrites the bytes on the device, so the artifact hash stops naming them."""

    def relax(schema: dict[str, object]) -> None:
        _at(schema, "properties")["optimize_disabled"] = {"type": "boolean"}

    resources = _edited(tmp_path, READING_RECORD, relax)

    with pytest.raises(RecordShapeError, match="Optimize"):
        validate_record_shapes(resources)


def test_a_dropped_anchor_is_rejected(tmp_path: Path) -> None:
    """The Delivery Record id is what says these bytes reached this device."""

    def drop(schema: dict[str, object]) -> None:
        required = cast(list[object], schema["required"])
        schema["required"] = [name for name in required if name != "delivery_record_id"]

    resources = _edited(tmp_path, READING_RECORD, drop)

    with pytest.raises(RecordShapeError, match="delivery_record_id"):
        validate_record_shapes(resources)


def test_an_example_the_skill_teaches_must_satisfy_the_shape(tmp_path: Path) -> None:
    """A worked example that would not validate is guidance that cannot be followed."""

    resources = _copy(tmp_path)
    document = resources / "device-read.md"
    _ = document.write_text(
        document.read_text("utf-8").replace('"reading_verdict": "acceptable"', '"x": 1'),
        encoding="utf-8",
    )

    with pytest.raises(RecordShapeError, match="device-read.md"):
        validate_record_shapes(resources)


def _add_property(name: str, definition: dict[str, object]) -> Callable[[dict[str, object]], None]:
    def edit(schema: dict[str, object]) -> None:
        _at(schema, "properties")[name] = definition
        cast(list[object], schema["required"]).append(name)

    return edit


def _at(schema: dict[str, object], *path: str) -> dict[str, object]:
    node = schema
    for step in path:
        node = cast(dict[str, object], node[step])
    return node


def _copy(tmp_path: Path) -> Path:
    resources = tmp_path / "resources"
    shutil.copytree(RESOURCES, resources)
    return resources


def _edited(tmp_path: Path, identifier: str, edit: Callable[[dict[str, object]], None]) -> Path:
    resources = _copy(tmp_path)
    path = resources / SCHEMAS[identifier]
    schema = cast(dict[str, object], json.loads(path.read_text("utf-8")))
    edit(schema)
    _ = path.write_text(json.dumps(schema), encoding="utf-8")
    return resources


def test_an_agent_may_not_predict_excellent(tmp_path: Path) -> None:
    """`excellent` requires a human device read, so no estimate can reach it."""

    def widen(schema: dict[str, object]) -> None:
        _at(schema, "properties", "predicted_verdict")["enum"] = report_verdicts()

    resources = _edited(tmp_path, ASSESSMENT, widen)

    with pytest.raises(RecordShapeError, match="predicted_verdict"):
        validate_record_shapes(resources)

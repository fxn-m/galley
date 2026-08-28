"""Validate the two records Galley's layers author outside the CLI.

Three layers have three jobs: the CLI computes, the agent flags, and the human judges. The CLI's
own output is gated by the Report schema, and the two layers above it need the same treatment or
their fields are only prose. These shapes ship beside the main Agent Skill rather
than in `galley.schemas`, because no command emits or reads either one — putting them where the
Report and the Delivery Record live would imply a writer that must not exist.

What is gated is the separation itself: the agent's record may settle only the flaggable
observations, carries a Predicted Verdict and has nowhere to write a Reading Verdict; the human's
record carries the Reading Verdict and cannot state that no read happened. Both vocabularies are
compared against the Registry and the Report schema, so a name can never be added in one place.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, ValidationError

from galley.observations import OBSERVATION_NAMES, OBSERVATION_REGISTRY
from galley.validation import SchemaValidator

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "src/galley/skills/galley/resources"
REPORT_SCHEMA = ROOT / "src/galley/schemas/report.json"
ASSESSMENT = "galley/agent-assessment/1"
READING_RECORD = "galley/reading-record/1"
SCHEMAS = {ASSESSMENT: "agent-assessment.schema.json", READING_RECORD: "reading-record.schema.json"}
# The fields each record is required to carry. A later field is added here first, so nobody can
# quietly drop the Delivery Record or the Optimize-off condition.
ASSESSMENT_FIELDS = {
    "schema",
    "assessed_by",
    "assessed_at",
    "report_path",
    "report_sha256",
    "artifact_sha256",
    "profile",
    "worklist",
    "findings",
    "outstanding",
    "predicted_verdict",
    "predicted_basis",
}
READING_FIELDS = {
    "schema",
    "reader",
    "read_on",
    "artifact_sha256",
    "ready_artifact_path",
    "report_path",
    "report_sha256",
    "delivery_record_id",
    "assessment_sha256",
    "profile",
    "firmware",
    "optimize_disabled",
    "observations",
    "reading_verdict",
    "note",
}
VERDICT_FORBIDDEN = re.compile(r"reading[_-]?verdict")
# The one verdict a human read alone can grant, and the one that says no read happened.
EXCELLENT, NOT_TESTED = "excellent", "not_tested"


class RecordShapeError(ValueError):
    """A record shape violates the separation between CLI, agent and reader."""


def flaggable_names() -> list[str]:
    """The observations assigned to the agent, in Registry order."""

    return [name for name in OBSERVATION_NAMES if OBSERVATION_REGISTRY[name][0] == "flaggable"]


def report_verdicts() -> list[str]:
    """The Reading Verdict vocabulary the Report schema already fixes."""

    document = _json(REPORT_SCHEMA)
    definitions = _mapping(document.get("$defs"), "$defs")
    verdict = _mapping(definitions.get("readingVerdict"), "readingVerdict")
    properties = _mapping(verdict.get("properties"), "readingVerdict.properties")
    value = _mapping(properties.get("value"), "readingVerdict.value")
    return [str(item) for item in cast(list[object], value.get("enum", []))]


def record_validator(
    identifier: str, resources: Path = RESOURCES
) -> tuple[dict[str, object], SchemaValidator]:
    """Return one authored record shape and the validator that enforces it.

    The shapes are the only decided statement of what an assessment and a reading record contain,
    so anything that checks a real one reads them from here rather than restating the fields. The
    pair matches `galley.validation.load_schema`, which is how every packaged schema is applied.
    """

    schema = _schema(resources, identifier)
    return schema, cast(SchemaValidator, Draft202012Validator(schema))


def validate_record_shapes(resources: Path) -> None:
    """Validate both shapes, their vocabularies, and the examples the skill teaches."""

    schemas = {identifier: _schema(resources, identifier) for identifier in SCHEMAS}
    _validate_assessment(schemas[ASSESSMENT])
    _validate_reading_record(schemas[READING_RECORD])
    _validate_examples(resources, schemas)


def _schema(resources: Path, identifier: str) -> dict[str, object]:
    document = _json(resources / SCHEMAS[identifier])
    if document.get("$id") != identifier:
        raise RecordShapeError(f"{SCHEMAS[identifier]}: expected $id {identifier}")
    if document.get("additionalProperties") is not False:
        raise RecordShapeError(f"{identifier}: an open record is not a decided record")
    Draft202012Validator.check_schema(document)
    return document


def _validate_assessment(schema: dict[str, object]) -> None:
    """The agent's record settles flaggable observations and predicts; it never judges."""

    properties = _mapping(schema.get("properties"), "properties")
    named = [key for key in properties if VERDICT_FORBIDDEN.search(key)]
    if named:
        raise RecordShapeError(f"{ASSESSMENT}: the Reading Verdict is not the agent's: {named}")
    _required(schema, ASSESSMENT, ASSESSMENT_FIELDS)
    _enum(schema, "$defs.finding.properties.observation", flaggable_names())
    # `excellent` requires a human device read, so an agent's estimate cannot reach it.
    _enum(schema, "properties.predicted_verdict", [v for v in report_verdicts() if v != EXCELLENT])


def _validate_reading_record(schema: dict[str, object]) -> None:
    """The human's record is anchored to a delivered artifact and states a verdict reached."""

    _required(schema, READING_RECORD, READING_FIELDS)
    _enum(schema, "$defs.observation.properties.observation", list(OBSERVATION_NAMES))
    _enum(schema, "properties.reading_verdict", [v for v in report_verdicts() if v != NOT_TESTED])
    optimize = _mapping(
        _mapping(schema.get("properties"), "properties").get("optimize_disabled"),
        "optimize_disabled",
    )
    if optimize.get("const") is not True:
        raise RecordShapeError(f"{READING_RECORD}: a read with Optimize on records other bytes")


def _validate_examples(resources: Path, schemas: dict[str, dict[str, object]]) -> None:
    """Every example the skill teaches must validate against the shape it claims."""

    seen = 0
    for document in sorted(resources.glob("*.md")):
        for block in re.findall(r"```json\n(.*?)```", document.read_text("utf-8"), re.DOTALL):
            example = cast(dict[str, object], cast(object, json.loads(block)))
            identifier = str(example.get("schema", ""))
            if identifier not in schemas:
                raise RecordShapeError(f"{document.name}: example claims no known record shape")
            _validate(schemas[identifier], example, document.name)
            seen += 1
    if seen < len(schemas):
        raise RecordShapeError("each record shape needs a worked example the skill can be read on")


def _validate(schema: dict[str, object], example: dict[str, object], label: str) -> None:
    try:
        cast(SchemaValidator, Draft202012Validator(schema)).validate(example)
    except ValidationError as error:
        raise RecordShapeError(f"{label}: {error.json_path}: {error.message}") from error


def _required(schema: dict[str, object], identifier: str, fields: set[str]) -> None:
    required = {str(item) for item in cast(list[object], schema.get("required", []))}
    properties = set(_mapping(schema.get("properties"), "properties"))
    for label, difference in (("missing", fields - required), ("unexpected", required - fields)):
        if difference:
            raise RecordShapeError(f"{identifier}: {label} required fields: {sorted(difference)}")
    if properties != fields:
        raise RecordShapeError(f"{identifier}: properties and required fields disagree")


def _enum(schema: dict[str, object], path: str, expected: list[str]) -> None:
    """Hold one vocabulary in a record shape to the list that already decides it."""

    node: object = schema
    for step in path.split("."):
        node = _mapping(node, path).get(step)
    values = [str(item) for item in cast(list[object], _mapping(node, path).get("enum", []))]
    if values != expected:
        raise RecordShapeError(f"{path}: expected {expected}, found {values}")


def _json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RecordShapeError(f"{path}: required record shape is missing")
    return cast(dict[str, object], cast(object, json.loads(path.read_text("utf-8"))))


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RecordShapeError(f"{label}: expected an object")
    return cast(dict[str, object], value)


def main() -> int:
    """Validate the authored record shapes from the command line."""

    try:
        validate_record_shapes(RESOURCES)
    except (RecordShapeError, json.JSONDecodeError) as error:
        print(f"checkrecords: {error}", file=sys.stderr)
        return 1
    print(f"checkrecords: OK ({len(SCHEMAS)} record shapes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

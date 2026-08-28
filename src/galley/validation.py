"""Load the JSON Schemas Galley ships and apply them the same way everywhere."""

import json
from importlib.resources import files
from typing import Protocol, cast

from jsonschema import Draft202012Validator


class SchemaValidator(Protocol):
    """The one validator behaviour Galley depends on."""

    def validate(self, instance: object) -> None: ...


def load_schema(name: str) -> tuple[dict[str, object], SchemaValidator]:
    """Return one packaged schema and the validator that enforces it."""

    document = cast(
        dict[str, object],
        json.loads(files("galley.schemas").joinpath(name).read_text(encoding="utf-8")),
    )
    return document, cast(SchemaValidator, Draft202012Validator(document))

"""Run pinned EPUBCheck and retain its conformance facts."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast

from galley.tools.dependencies import diagnostic, run_dependency, selected_command
from galley.json_reading import integer, mapping, sequence, text
from galley.report.quantities import quantity, reported

COMMAND_VARIABLE = "GALLEY_EPUBCHECK"
DEFAULT_COMMAND = "epubcheck"
PINNED_VERSION = "5.3.0"
SEVERITY_FIELDS = {
    "fatal": "nFatal",
    "error": "nError",
    "warning": "nWarning",
    "usage": "nUsage",
}
PUBLICATION_FACTS = {
    "ePubVersion": "epub_version",
    "isBackwardCompatible": "is_backward_compatible",
    "isScripted": "is_scripted",
    "charsCount": "chars_count",
}
INVENTORY_FACTS = {
    "fileName": "file_name",
    "media_type": "declared_media_type",
    "compressedSize": "compressed_size",
    "uncompressedSize": "uncompressed_size",
    "compressionMethod": "compression_method",
    "checkSum": "checksum",
    "isSpineItem": "is_spine_item",
    "spineIndex": "spine_index",
    "isLinear": "is_linear",
    "referencedItems": "referenced_items",
}

UnavailableReason = Literal[
    "not-found", "not-executable", "timeout", "no-output", "malformed-output"
]


@dataclass(frozen=True)
class Conformance:
    """One EPUBCheck outcome and the exact version that produced it."""

    facts: dict[str, object]
    version: str | None


def check_conformance(subject: Path) -> Conformance:
    """Run EPUBCheck read-only over one EPUB and retain everything it reports."""

    command = selected_command(COMMAND_VARIABLE, DEFAULT_COMMAND)
    with TemporaryDirectory() as workspace:
        destination = Path(workspace) / "epubcheck.json"
        execution = run_dependency(command, [str(subject), "--json", str(destination)])
        completed = execution.completed
        if completed is None:
            return _unavailable(command, execution.reason or "not-found", execution.detail)
        written = destination.is_file()
        document = _read_document(destination) if written else None
    if document is None:
        return _unavailable(command, *_unusable_output(written), completed=completed)
    return _conformance(command, document, completed.returncode)


def _unusable_output(written: bool) -> tuple[UnavailableReason, str]:
    if not written:
        return "no-output", "EPUBCheck wrote no JSON document"
    return "malformed-output", "EPUBCheck wrote no JSON document naming a checker version"


def _read_document(destination: Path) -> dict[str, object] | None:
    """Return EPUBCheck's document only when it carries the checker block Galley needs."""

    try:
        raw = cast(object, json.loads(destination.read_text(encoding="utf-8")))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    document = cast(dict[str, object], raw)
    checker = mapping(document.get("checker"))
    return document if text(checker.get("checkerVersion")) is not None else None


def _conformance(command: str, document: dict[str, object], exit_code: int) -> Conformance:
    checker = mapping(document.get("checker"))
    version = text(checker.get("checkerVersion"))
    tallies = {name: integer(checker.get(field)) or 0 for name, field in SEVERITY_FIELDS.items()}
    messages = sorted(sequence(document.get("messages")), key=_message_order)
    inventory = sorted(sequence(document.get("items")), key=_inventory_order)
    facts: dict[str, object] = {
        "checked": True,
        "command": command,
        "counts": {name: reported(value) for name, value in tallies.items()},
        "exit_code": quantity(exit_code, "exit code"),
        "inventory": [_inventory_item(item) for item in inventory],
        "matches_pinned_version": version == PINNED_VERSION,
        "messages": [_message(entry) for entry in messages],
        "pinned_version": PINNED_VERSION,
        "publication": _mapped_facts(document.get("publication"), PUBLICATION_FACTS),
        "tool": "epubcheck",
        "valid": tallies["fatal"] == 0 and tallies["error"] == 0,
        "version": version,
    }
    return Conformance(facts=facts, version=version)


def _unavailable(
    command: str,
    reason: UnavailableReason,
    detail: str,
    *,
    completed: subprocess.CompletedProcess[str] | None = None,
) -> Conformance:
    facts: dict[str, object] = {
        "checked": False,
        "command": command,
        "detail": detail,
        "pinned_version": PINNED_VERSION,
        "reason": reason,
        "tool": "epubcheck",
    }
    if completed is not None:
        facts["exit_code"] = quantity(completed.returncode, "exit code")
        facts["stderr"] = diagnostic(completed.stderr)
        facts["stdout"] = diagnostic(completed.stdout)
    return Conformance(facts=facts, version=None)


def _message_order(entry: object) -> tuple[str, int, int, str]:
    message = mapping(entry)
    location = mapping(next(iter(sequence(message.get("locations"))), None))
    return (
        text(location.get("path")) or "",
        integer(location.get("line")) or 0,
        integer(location.get("column")) or 0,
        text(message.get("ID")) or "",
    )


def _inventory_order(entry: object) -> tuple[str, str]:
    item = mapping(entry)
    return (text(item.get("fileName")) or "", text(item.get("id")) or "")


def _message(entry: object) -> dict[str, object]:
    message = mapping(entry)
    return {
        "additional_locations": reported(integer(message.get("additionalLocations")) or 0),
        "id": text(message.get("ID")),
        "locations": [_location(location) for location in sequence(message.get("locations"))],
        "message": text(message.get("message")),
        "severity": text(message.get("severity")),
        "suggestion": text(message.get("suggestion")),
    }


def _location(entry: object) -> dict[str, object]:
    location = mapping(entry)
    return {
        "column": _position(location.get("column")),
        "context": text(location.get("context")),
        "line": _position(location.get("line")),
        "path": text(location.get("path")),
    }


def _inventory_item(entry: object) -> dict[str, object]:
    item = mapping(entry)
    return {"id": text(item.get("id")), **_mapped_facts(item, INVENTORY_FACTS)}


def _mapped_facts(value: object, names: dict[str, str]) -> dict[str, object]:
    document = mapping(value)
    return {name: _fact(document.get(source)) for source, name in names.items()}


def _fact(value: object) -> object:
    if value is None or isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, list):
        return [_fact(item) for item in cast(list[object], value)]
    number = integer(value)
    return None if number is None else reported(number)


def _position(value: object) -> dict[str, object] | None:
    """Keep an EPUBCheck line or column only when it names a real position."""

    number = integer(value)
    return None if number is None or number < 0 else reported(number)

"""Render skill installation documents as concise terminal output, from the document alone.

These commands resolve no Workspace, so they do not share the Workspace header — but they do share
the envelope's outcome line and its structured refusal, which is why both come from
`galley.documents` rather than being restated here.
"""

from typing import cast

from galley.documents import CommandDocument, refusal_lines, validate_document
from galley.json_reading import mapping, sequence


def render_installation(document: CommandDocument) -> str:
    """Describe where the skills came from, where they went, and what happened to each."""

    validate_document(document)
    galley = mapping(document["galley"])
    source = mapping(document["source"])
    target = mapping(document["target"])
    lines = [
        f"{galley['command']}: {document['outcome']}",
        f"Source: {source['path']} (Galley {source['galley_version']})",
        f"Target: {target['path']} ({target['source']})",
        *_skill_lines(document),
    ]
    return "\n".join([*lines, *refusal_lines(document)]) + "\n"


def _skill_lines(document: CommandDocument) -> list[str]:
    """State each skill's action beside the state its destination was found in."""

    lines: list[str] = []
    for skill in _entries(document, "skills"):
        counted = _counted(cast(list[object], skill["files"]))
        lines.append(f"  {skill['name']}: {skill['action']} (was {skill['state']}){counted}")
        lines += _difference_lines(skill)
    return lines


def _difference_lines(skill: dict[str, object]) -> list[str]:
    """Name what stops a destination matching its manifest, whether or not the run refused.

    A forced run has to say which conflict it overruled, and a refused one has to say which files
    a person would be authorising a replacement of.
    """

    differences = [str(path) for path in sequence(skill.get("differences"))]
    return [f"    differs: {', '.join(differences)}"] if differences else []


def _counted(files: list[object]) -> str:
    dispositions = sorted({str(mapping(file)["action"]) for file in files})
    if not dispositions:
        return ""
    counts = ", ".join(
        f"{sum(1 for file in files if mapping(file)['action'] == disposition)} {disposition}"
        for disposition in dispositions
    )
    return f" — {counts}"


def _entries(document: CommandDocument, key: str) -> list[dict[str, object]]:
    return [mapping(value) for value in sequence(document.get(key))]

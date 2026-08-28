"""Render one localisation document as concise terminal output, from the document alone.

Human output is a second rendering of the record, never a second account of what happened: every
line here is read back out of the validated document, so a reader holding the JSON and a reader
holding the terminal are looking at the same facts.
"""

from typing import cast

from galley.documents import CommandDocument, refusal_lines, validate_document
from galley.json_reading import integer, mapping, sequence, text


def render_localisation(document: CommandDocument) -> str:
    """Describe what was read, what was retrieved from where, and where the Repair Set landed."""

    validate_document(document)
    galley = cast(dict[str, object], document["galley"])
    lines = [
        f"{galley['command']}: {document['outcome']}",
        *_profile_lines(document),
        *_source_lines(document),
        *_evidence_lines(document),
        *_reference_lines(document),
        *refusal_lines(document),
    ]
    return "\n".join(lines) + "\n"


def _profile_lines(document: CommandDocument) -> list[str]:
    profile = mapping(document.get("profile"))
    resolved = text(profile.get("id")) or text(profile.get("requested"))
    return [f"Profile: {resolved}{'' if profile.get('resolved') else ' (unresolved)'}"]


def _source_lines(document: CommandDocument) -> list[str]:
    source = mapping(document.get("source"))
    if not source:
        return []
    return [f"Source: {source['path']}"]


def _evidence_lines(document: CommandDocument) -> list[str]:
    evidence = mapping(document.get("evidence"))
    if not evidence:
        return []
    return [
        f"Repair Set: {evidence['directory']}",
        f"  prepare --inspection-report {evidence['inspection_report']}",
        f"          --canonical-document {evidence['canonical_document']}",
        f"          --preservation-baseline {evidence['preservation_baseline']}",
    ]


def _reference_lines(document: CommandDocument) -> list[str]:
    """One line per reference: where it came from, how it ended, and what arrived."""

    lines: list[str] = []
    for value in sequence(document.get("references")):
        reference = mapping(value)
        transport = mapping(reference.get("transport"))
        lines.append(
            f"{reference['identifier']}: {reference['locator']} "
            f"({_host(reference)}) — {transport['outcome']}{_arrived(reference)}"
        )
    return lines


def _host(reference: dict[str, object]) -> str:
    addresses = [text(address) or "" for address in sequence(reference.get("addresses"))]
    host = text(reference.get("host")) or "no host"
    return f"{host} → {', '.join(addresses)}" if addresses else host


def _arrived(reference: dict[str, object]) -> str:
    """State what was written, where anything was, and nothing at all where nothing was."""

    located = text(reference.get("path"))
    if located is None:
        return ""
    size = integer(reference.get("byte_size"))
    return f", {text(reference.get('media_type'))} {size} bytes → {located}"

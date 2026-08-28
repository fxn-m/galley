"""Render concise human output only from validated Workspace command documents.

The header every Workspace-aware document shares — which command ran, which Workspace it resolved
and which configuration — is rendered once here and reused by the commands whose own facts live
elsewhere, so a reader sees the same three lines whatever they ran. The structured refusal is
rendered by `galley.documents` instead, because it belongs to every document in the family
including the ones that resolve no Workspace at all.
"""

from typing import cast

from galley.json_reading import mapping, sequence
from galley.documents import CommandDocument, refusal_lines, validate_document

INBOX_CHECK_COMMAND = "inbox check"


def render_document(document: CommandDocument) -> str:
    """Render one validated command document as concise terminal output."""

    galley = cast(dict[str, object], document["galley"])
    lines = [
        *document_header(document),
        *_body(document, str(galley["command"])),
        *refusal_lines(document),
    ]
    return "\n".join(lines) + "\n"


def document_header(document: CommandDocument) -> list[str]:
    """Render the command, outcome and Workspace every document in this family carries."""

    validate_document(document)
    galley = cast(dict[str, object], document["galley"])
    workspace = cast(dict[str, object], document["workspace"])
    return [
        f"{galley['command']}: {document['outcome']}",
        f"Workspace: {workspace['path']} ({workspace['source']})",
        f"Configuration: {workspace['configuration_path']}{_version(document)}",
    ]


def _version(document: CommandDocument) -> str:
    configuration = document.get("configuration")
    if not isinstance(configuration, dict):
        return ""
    return f" (version {cast(dict[str, object], configuration)['version']})"


def _body(document: CommandDocument, command: str) -> list[str]:
    """Render the facts the command that produced this document owns, and no others."""

    if command == INBOX_CHECK_COMMAND:
        return _coverage_lines(document) + _candidate_lines(document) + _problem_lines(document)
    return _inbox_lines(document) + _location_lines(document) + _connection_lines(document)


def _inbox_lines(document: CommandDocument) -> list[str]:
    return [
        f"Inbox {inbox['name']}: {inbox['resolved_path']} "
        f"({_recursion(inbox)}, {inbox['path_resolution']}, {inbox['state']})"
        for inbox in _entries(document, "inboxes")
    ]


def _location_lines(document: CommandDocument) -> list[str]:
    locations = _entries(document, "locations")
    if not locations:
        return []
    stated = ", ".join(f"{location['role']} {location['state']}" for location in locations)
    return [f"Locations: {stated}"]


def _connection_lines(document: CommandDocument) -> list[str]:
    connection = document.get("connection")
    if not isinstance(connection, dict):
        return []
    settings = cast(dict[str, object], connection)
    host = cast(dict[str, object], settings["host"])
    destination = cast(dict[str, object], settings["destination"])
    return [
        f"CrossPoint: {host['value']} ({host['source']}) "
        f"-> {destination['value']} ({destination['source']})"
    ]


def _coverage_lines(document: CommandDocument) -> list[str]:
    """State what each Inbox saw and what stopped it, never one in place of the other.

    An Inbox that could not be listed in full still observed everything up to that point, and
    those counts are the partial statement — dropping them for the error would hide exactly the
    coverage a reader is trying to judge.
    """

    lines: list[str] = []
    for inbox in _entries(document, "coverage"):
        counted = f"{inbox['supported_count']} supported, {inbox['ignored_count']} ignored"
        error = f"; {inbox['error']}" if inbox["error"] else ""
        lines.append(
            f"Inbox {inbox['name']}: {inbox['status']} ({_recursion(inbox)}) — {counted}{error}"
        )
    return lines


def _candidate_lines(document: CommandDocument) -> list[str]:
    """List every candidate behind its own derived state, which is what a reader acts on."""

    candidates = _entries(document, "candidates")
    lines = [f"Candidates: {len(candidates)}"]
    for candidate in candidates:
        lines.append(
            f"  {candidate['state']} — {candidate['primary_inbox']}: "
            f"{candidate['resolved_path']} "
            f"({candidate['source_kind']}, {candidate['byte_size']} bytes, "
            f"sha256 {candidate['sha256']})"
        )
        lines += _attempt_lines(candidate)
    return lines


def _attempt_lines(candidate: dict[str, object]) -> list[str]:
    """State the latest refused attempt beneath its candidate, never in place of its state."""

    latest = mapping(candidate.get("latest_attempt"))
    if not latest:
        return []
    return [f"    latest attempt: {latest['boundary']} ({latest['stage']})"]


def _problem_lines(document: CommandDocument) -> list[str]:
    """Name every Ready Artifact or evidence bundle that is not what its Report says it is.

    A check repairs nothing and deletes nothing, so saying so is the whole of what it can do
    about damage — and staying silent would leave a reader acting on a state derived around it.
    """

    problems = _entries(document, "evidence_problems")
    if not problems:
        return []
    lines = [f"Evidence problems: {len(problems)}"]
    lines += [
        f"  {problem['problem']}: {problem['evidence_path']}"
        + (f" — {problem['artifact_path']}" if problem["artifact_path"] else "")
        for problem in problems
    ]
    return lines


def _recursion(entry: dict[str, object]) -> str:
    return "recursive" if entry["recursive"] else "direct children"


def _entries(document: CommandDocument, key: str) -> list[dict[str, object]]:
    return [mapping(value) for value in sequence(document.get(key))]

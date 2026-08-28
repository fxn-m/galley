"""Render device and Delivery documents as concise terminal output, from the documents alone.

Human output is a second rendering of the validated record, never a second account of what
happened: everything printed here is read back out of the document that was persisted, so a
reader who has the record and a reader who has the terminal are looking at the same facts.
"""

from typing import cast

from galley.json_reading import mapping
from galley.documents import CommandDocument, refusal_lines, validate_document
from galley.workspace.render import document_header


def render_device_status(document: CommandDocument) -> str:
    """Describe the target that was probed and the device that answered."""

    validate_document(document)
    lines = [*document_header(document), *_device_lines(document)]
    return "\n".join([*lines, *refusal_lines(document)]) + "\n"


def render_delivery_record(document: CommandDocument) -> str:
    """Describe one plan or attempt: the book, the target, and the action it settled on."""

    validate_document(document)
    lines = [
        *document_header(document),
        f"Record: {document['record_id']} ({document['mode']})",
        *_connection_lines(document),
        *_artifact_lines(document),
        *_device_lines(document),
        *_destination_lines(document),
        *_action_lines(document),
    ]
    return "\n".join([*lines, *refusal_lines(document)]) + "\n"


def _connection_lines(document: CommandDocument) -> list[str]:
    connection = mapping(document.get("connection"))
    if not connection:
        return []
    host = mapping(connection.get("host"))
    destination = mapping(connection.get("destination"))
    return [
        f"CrossPoint: {host['value']} ({host['source']}) "
        f"-> {destination['value']} ({destination['source']})"
    ]


def _artifact_lines(document: CommandDocument) -> list[str]:
    artifact = mapping(document.get("artifact"))
    if not artifact:
        return []
    profile = mapping(artifact.get("profile"))
    return [
        f"Artifact: {artifact['path']}",
        f"Bytes: {artifact['byte_size']}; sha256 {artifact['sha256']}",
        f"Prepared for {profile['id']} ({profile['profile_version']}); "
        f"Report {artifact['report_path']}",
    ]


def _device_lines(document: CommandDocument) -> list[str]:
    """State what was talked to, and then what it said, which are separate achievements."""

    device = mapping(document.get("device"))
    host = mapping(document.get("host"))
    if not device:
        return [f"Host: {host['value']} ({host['source']})"] if host else []
    addresses = ", ".join(str(value) for value in cast(list[object], device["addresses"]))
    lines = [f"Target: {device['host']} -> {addresses} ({device['timeout_seconds']}s timeout)"]
    if device["model"] is None:
        return lines
    mode = device["mode"] or "unreported mode"
    return [*lines, f"Device: {device['model']} firmware {device['firmware']} ({mode})"]


def _destination_lines(document: CommandDocument) -> list[str]:
    destination = mapping(document.get("destination"))
    if destination.get("path") is None:
        return []
    lines = [f"Destination: {destination['path']} -> {destination['remote_path']}"]
    lines += _listing_line("Before", mapping(destination.get("preflight")))
    lines += _listing_line("After", mapping(destination.get("postflight")))
    return lines


def _listing_line(label: str, listing: dict[str, object]) -> list[str]:
    if not listing:
        return []
    matching = mapping(listing.get("matching"))
    found = f"{matching['name']} at {matching['byte_size']} bytes" if matching else "not present"
    return [f"{label}: {listing['entry_count']} entries; {found}"]


def _action_lines(document: CommandDocument) -> list[str]:
    action = mapping(document.get("action"))
    planned = action.get("planned")
    if planned is None and not action.get("upload_began"):
        return []
    began = "upload began" if action.get("upload_began") else "no upload"
    status = action.get("transport_status")
    transport = f"; HTTP {status}" if status is not None else ""
    return [f"Action: {planned or 'none'} ({began}{transport})"]

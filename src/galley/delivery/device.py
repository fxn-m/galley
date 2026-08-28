"""Probe the configured X4 and report what answered, without touching a document byte.

`device status` is the smallest useful thing Galley can do with a device: resolve the configured
host, prove it is a local target, ask CrossPoint what it is, and report the whole answer. It
prepares nothing, lists nothing and writes nothing — not even a Delivery Record, because a probe
is neither a plan nor an attempt.
"""

from pathlib import Path

from galley.delivery.connection import resolve_host
from galley.delivery.probing import probe
from galley.delivery.refusals import DeliveryRefusal
from galley.report.envelope import ReportRun
from galley.documents import (
    DEVICE_STATUS_SCHEMA,
    CommandDocument,
    command_document,
    with_facts,
    with_refusal,
)
from galley.workspace.resolution import resolve_workspace

COMMAND = "device status"
DEFAULT_TIMEOUT_SECONDS = 3.0


def check_device(
    chosen: Path | None, host: str | None, timeout_seconds: float, *, run: ReportRun
) -> CommandDocument:
    """Resolve the configured device, probe it once, and report exactly what it said."""

    workspace = resolve_workspace(chosen)
    document = command_document(
        COMMAND,
        DEVICE_STATUS_SCHEMA,
        run,
        {
            "workspace": workspace.facts(),
            "configuration": None,
            "host": None,
            "device": None,
        },
    )
    choice = resolve_host(workspace, host)
    if isinstance(choice, DeliveryRefusal):
        return with_refusal(document, choice)
    document = with_facts(
        document, {"configuration": choice.configuration, "host": choice.host.facts()}
    )
    return probe(document, choice.host.value, timeout_seconds).document

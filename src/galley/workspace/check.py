"""Check every configured Inbox once, reconcile what they saw, and report exact coverage.

Inbox Check is one-shot and read-only: no watcher, no queue, no index, no work artifact, no
network request. It consumes the same validated Workspace Configuration `config validate`
reports, but it deliberately does not inherit that command's availability refusal — one missing
volume must not hide the reading material sitting in every other Inbox. An Inbox that could not
be fully listed is reported as `unavailable` instead, which is a fact a reader can act on and
can never be mistaken for a completed check.
"""

from dataclasses import dataclass
from pathlib import Path

from galley.workspace.configuration import (
    CONFIGURATION_SCHEMA,
    SUPPORTED_VERSION,
    ConfigurationRefusal,
    InboxDefinition,
    read_configuration,
)
from galley.documents import (
    INBOX_CHECK_SCHEMA,
    CommandDocument,
    command_document,
    with_facts,
    with_refusal,
)
from galley.report.envelope import ReportRun
from galley.workspace.evidence import ReadyEvidence, problem_facts, ready_evidence
from galley.workspace.inbox import Candidate, Inventory, inventory
from galley.workspace.ready import ReadyWorkspace
from galley.workspace.resolution import resolve_workspace

COMMAND = "inbox check"


@dataclass(frozen=True)
class Reconciliation:
    """The one candidate list a check reports, and the evidence damage deriving it ran into."""

    candidates: list[dict[str, object]]
    problems: list[dict[str, object]]


def check_inboxes(chosen: Path | None, *, run: ReportRun) -> CommandDocument:
    """Inventory every configured Inbox in order, without preparing or touching one source."""

    workspace = resolve_workspace(chosen)
    document = command_document(
        COMMAND,
        INBOX_CHECK_SCHEMA,
        run,
        {
            "workspace": workspace.facts(),
            "configuration": None,
            "coverage": [],
            "candidates": [],
            "evidence_problems": [],
        },
    )
    configuration = read_configuration(workspace)
    if isinstance(configuration, ConfigurationRefusal):
        return with_refusal(document, configuration)
    inventories = [inventory(inbox) for inbox in configuration.inboxes]
    scanned = ready_evidence(ReadyWorkspace(workspace))
    reconciliation = reconciled(configuration.inboxes, inventories, scanned)
    return with_facts(
        document,
        {
            "configuration": {"schema": CONFIGURATION_SCHEMA, "version": SUPPORTED_VERSION},
            "coverage": [stock.coverage.facts() for stock in inventories],
            "candidates": reconciliation.candidates,
            "evidence_problems": reconciliation.problems,
        },
    )


def reconciled(
    inboxes: tuple[InboxDefinition, ...],
    inventories: list[Inventory],
    scanned: ReadyEvidence,
) -> Reconciliation:
    """Deduplicate overlapping Inboxes by resolved path, in one deterministic order.

    A source two configured roots can both see is one candidate, not two: identity is the
    resolved path. The first configured Inbox keeps primary attribution and every other Inbox
    that can see the file is named beside it, so an overlap is visible rather than arbitrated
    silently. Ordering is configured Inbox order, then resolved path — never a display name.

    Each surviving candidate is then asked what state its own provenance is in, against the
    immutable Reports already published. State is derived here rather than in the walk because
    a source two Inboxes can see must be answered once, for the one candidate it becomes — and
    so must any damage found on the way, which is why the problems come back beside the list.
    """

    order = {inbox.name: position for position, inbox in enumerate(inboxes)}
    owners: dict[Path, Candidate] = {}
    matching: dict[Path, list[str]] = {}
    for stock in inventories:
        for candidate in stock.candidates:
            _ = owners.setdefault(candidate.path, candidate)
            names = matching.setdefault(candidate.path, [])
            if candidate.inbox not in names:
                names.append(candidate.inbox)
    ranked = sorted(owners.values(), key=lambda found: (order[found.inbox], str(found.path)))
    derived = [
        (candidate, scanned.derive(candidate.resolved_path, candidate.sha256))
        for candidate in ranked
    ]
    return Reconciliation(
        [candidate.facts(matching[candidate.path], found) for candidate, found in derived],
        problem_facts([*scanned.damaged, *(found.damage for _, found in derived if found.damage)]),
    )

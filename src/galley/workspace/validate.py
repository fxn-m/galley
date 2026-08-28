"""Validate one Workspace Configuration read-only, and report exactly what it resolved to.

This is the whole of the CLI's authority over configuration: it resolves, parses, validates and
reports. It writes nothing, inventories no Inbox, probes no device and touches no
source. What it does probe is availability — whether each configured Inbox is a readable
directory and whether an existing Galley-owned location has the type and access its role needs —
because a configuration naming a path that cannot serve its purpose is not valid configuration.
"""

from pathlib import Path

from galley.json_reading import mapping, sequence
from galley.report.envelope import ReportRun
from galley.workspace.configuration import (
    CONFIGURATION_SCHEMA,
    SUPPORTED_VERSION,
    ConfigurationRefusal,
    WorkspaceConfiguration,
    read_configuration,
)
from galley.documents import (
    CONFIG_VALIDATION_SCHEMA,
    CommandDocument,
    command_document,
    with_facts,
    with_refusal,
)
from galley.workspace.layout import (
    LAYOUT_STAGE,
    OwnedLocation,
    directory_state,
    owned_locations,
)
from galley.workspace.resolution import resolve_workspace

COMMAND = "config validate"
AVAILABILITY_STAGE = "inbox-availability"
WRONG_KIND = "not-a-directory"


def validate_workspace_configuration(chosen: Path | None, *, run: ReportRun) -> CommandDocument:
    """Resolve one Galley Workspace and report what its configuration says, or why it cannot."""

    workspace = resolve_workspace(chosen)
    locations = owned_locations(workspace.path)
    document = command_document(
        COMMAND,
        CONFIG_VALIDATION_SCHEMA,
        run,
        {
            "workspace": workspace.facts(),
            "configuration": None,
            "inboxes": [],
            "locations": [location.facts() for location in locations],
            "connection": None,
        },
    )
    configuration = read_configuration(workspace)
    if isinstance(configuration, ConfigurationRefusal):
        return with_refusal(document, configuration)
    document = _described(document, configuration)
    return _available(document, configuration, locations)


def _described(document: CommandDocument, configuration: WorkspaceConfiguration) -> CommandDocument:
    """Report every resolved Inbox and connection value before anything is probed."""

    return with_facts(
        document,
        {
            "configuration": {"schema": CONFIGURATION_SCHEMA, "version": SUPPORTED_VERSION},
            "inboxes": [
                {**inbox.facts(), "state": directory_state(inbox.path)}
                for inbox in configuration.inboxes
            ],
            "connection": configuration.connection.facts(),
        },
    )


def _available(
    document: CommandDocument,
    configuration: WorkspaceConfiguration,
    locations: tuple[OwnedLocation, ...],
) -> CommandDocument:
    """Refuse the first Inbox that cannot be read, and any owned location of the wrong kind.

    The configured order decides which one is named, so the same broken configuration always
    refuses at the same place. The two roles are held to different standards deliberately. An
    Inbox is the user's own configuration and must be a readable directory, which is what the
    criterion "unreadable external Inboxes refuse" asks for. A Galley-owned location is only
    refused when it is the wrong *kind* of path — absent is not a fault, because the CLI never
    creates one and the Setup Skill has not necessarily run; unreadable or unwritable is
    reported rather than refused, because validation was asked to report exactly that and a
    later write is where it genuinely matters.
    """

    for inbox, facts in zip(configuration.inboxes, _inboxes(document), strict=True):
        state = facts["state"]
        if state != "usable":
            return with_refusal(
                document,
                ConfigurationRefusal(
                    boundary="inbox-unavailable",
                    stage=AVAILABILITY_STAGE,
                    summary=f"configured Inbox {inbox.name} is not a readable directory: {state}",
                    fact={
                        "configured_path": inbox.configured_path,
                        "name": inbox.name,
                        "resolved_path": facts["resolved_path"],
                        "state": state,
                    },
                ),
            )
    for location in locations:
        if location.state == WRONG_KIND:
            return with_refusal(
                document,
                ConfigurationRefusal(
                    boundary="workspace-location-unusable",
                    stage=LAYOUT_STAGE,
                    summary=(
                        f"the Galley-owned {location.role} location cannot serve its role: "
                        f"{location.state}"
                    ),
                    fact=location.facts(),
                ),
            )
    return document


def _inboxes(document: CommandDocument) -> list[dict[str, object]]:
    return [mapping(value) for value in sequence(document["inboxes"])]

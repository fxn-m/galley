"""Resolve the host and destination one Delivery invocation uses, and say where each came from.

Workspace Configuration owns the user's device connection, and an option overrides it for that
invocation alone. Each value therefore carries its own provenance, so a default is never read
back as something the user chose.

Configuration is read only when it is still needed. Naming both values explicitly is a complete
statement of where to write, and refusing it because no `galley.toml` exists yet would add a way
to fail without adding a fact.
"""

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from galley.delivery.refusals import DeliveryRefusal
from galley.workspace.configuration import (
    CONFIGURATION_SCHEMA,
    SUPPORTED_VERSION,
    Connection,
    ConfigurationRefusal,
    read_configuration,
)
from galley.workspace.resolution import Workspace

CONNECTION_STAGE = "delivery-connection"

ValueSource = Literal["configured", "default", "option"]


@dataclass(frozen=True)
class Setting:
    """One resolved connection value, beside the authority that decided it."""

    value: str
    source: ValueSource

    def facts(self) -> dict[str, object]:
        """State the value and its provenance together, never one without the other."""

        return {"value": self.value, "source": self.source}


@dataclass(frozen=True)
class HostChoice:
    """The host one probe uses, and the configuration consulted to decide it."""

    host: Setting
    configuration: dict[str, object] | None


@dataclass(frozen=True)
class ResolvedConnection:
    """Where this invocation writes, and whether a Workspace Configuration was consulted."""

    host: Setting
    destination: Setting
    configuration: dict[str, object] | None

    def facts(self) -> dict[str, object]:
        """Report both settings the way every Workspace command reports a connection."""

        return {"host": self.host.facts(), "destination": self.destination.facts()}


def resolve_host(workspace: Workspace, host: str | None) -> HostChoice | DeliveryRefusal:
    """Decide the host one device probe uses, reading configuration only where it is needed."""

    if host is not None:
        return HostChoice(Setting(host, "option"), None)
    configured = _configured(workspace)
    if isinstance(configured, DeliveryRefusal):
        return configured
    settings, document = configured
    return HostChoice(Setting(settings.host, settings.host_source), document)


def resolve_connection(
    workspace: Workspace, host: str | None, destination: str | None
) -> ResolvedConnection | DeliveryRefusal:
    """Decide the host and destination, reading configuration only where one is still missing."""

    if host is not None and destination is not None:
        chosen = ResolvedConnection(Setting(host, "option"), Setting(destination, "option"), None)
    else:
        configured = _configured(workspace)
        if isinstance(configured, DeliveryRefusal):
            return configured
        settings, document = configured
        chosen = ResolvedConnection(
            Setting(host, "option")
            if host is not None
            else Setting(settings.host, settings.host_source),
            Setting(destination, "option")
            if destination is not None
            else Setting(settings.destination, settings.destination_source),
            document,
        )
    invalid = _invalid_destination(chosen.destination.value)
    return invalid if invalid is not None else chosen


def _configured(
    workspace: Workspace,
) -> tuple[Connection, dict[str, object]] | DeliveryRefusal:
    """Read the user's own connection settings, or carry the reason they could not be read."""

    configuration = read_configuration(workspace)
    if isinstance(configuration, ConfigurationRefusal):
        return refused(configuration)
    return configuration.connection, {
        "schema": CONFIGURATION_SCHEMA,
        "version": SUPPORTED_VERSION,
    }


def refused(configuration: ConfigurationRefusal) -> DeliveryRefusal:
    """Carry one configuration refusal into the record Delivery is going to emit."""

    return DeliveryRefusal(
        boundary=configuration.boundary,
        stage=configuration.stage,
        summary=configuration.summary,
        fact=configuration.fact,
    )


def _invalid_destination(destination: str) -> DeliveryRefusal | None:
    """Hold the destination to one absolute, already-normalised CrossPoint directory.

    Galley never invents a path on the device: the destination must be an existing folder the
    user named, spelled the way it will be sent. Refusing a path that needs normalising is what
    keeps the string in the Delivery Record identical to the string on the wire.
    """

    reason = _destination_fault(destination)
    if reason is None:
        return None
    return DeliveryRefusal(
        boundary="invalid-delivery-destination",
        stage=CONNECTION_STAGE,
        summary=f"destination must be an absolute normalised CrossPoint path: {reason}",
        fact={"destination": destination, "reason": reason},
    )


def _destination_fault(destination: str) -> str | None:
    if not destination.startswith("/") or destination.startswith("//"):
        return "it does not begin with a single /"
    if "\\" in destination or "\x00" in destination:
        return "it contains a backslash or a null byte"
    if any(part in {".", ".."} for part in destination.split("/")):
        return "it contains a . or .. component"
    if str(PurePosixPath(destination)) != destination:
        return f"it is not normalised ({PurePosixPath(destination)})"
    return None

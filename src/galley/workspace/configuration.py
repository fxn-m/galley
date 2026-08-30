"""Read the strict TOML Workspace Configuration, or say exactly why it cannot be read.

This module parses and validates; it never writes, and it never touches the directories the
configuration names. Configuration authorship belongs to the Setup Skill, so the CLI's
whole contribution here is a deterministic reading of what the user wrote — which means an
unknown key, an unsupported version and a duplicate name are refusals rather than repairs.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from galley.json_reading import integer, mapping, sequence, text
from galley.locations import display_path, resolved
from galley.workspace.resolution import Workspace

CONFIGURATION_SCHEMA = "galley/workspace-config/1"
SUPPORTED_VERSION = 1
VERSION_KEY = "version"
INBOX_KEY = "inbox"
CONNECTION_KEY = "x4-crosspoint"
COVER_ARTWORK_KEY = "cover-artwork"
TOP_LEVEL_KEYS = (VERSION_KEY, INBOX_KEY, CONNECTION_KEY, COVER_ARTWORK_KEY)
INBOX_KEYS = ("name", "path", "recursive")
CONNECTION_KEYS = ("host", "destination")
DEFAULT_HOST = "crosspoint.local"
DEFAULT_DESTINATION = "/"
DEFAULT_COVER_ARTWORK = False

PARSE_STAGE = "configuration-parse"
SCHEMA_STAGE = "configuration-schema"

PathResolution = Literal["relative", "home-relative", "absolute"]
ValueSource = Literal["configured", "default"]


@dataclass(frozen=True)
class InboxDefinition:
    """One configured Inbox, with the configured spelling and the path it resolved to."""

    name: str
    configured_path: str
    path_resolution: PathResolution
    path: Path
    recursive: bool

    def facts(self) -> dict[str, object]:
        """Report the configured spelling and the resolution beside each other, explicitly."""

        return {
            "name": self.name,
            "configured_path": self.configured_path,
            "path_resolution": self.path_resolution,
            "resolved_path": display_path(self.path),
            "recursive": self.recursive,
        }


@dataclass(frozen=True)
class Connection:
    """The user's CrossPoint host and destination, which are configuration, never evidence."""

    host: str = DEFAULT_HOST
    destination: str = DEFAULT_DESTINATION
    host_source: ValueSource = "default"
    destination_source: ValueSource = "default"

    def facts(self) -> dict[str, object]:
        """State each value with where it came from, so a default is never read as a fact."""

        return {
            "host": {"value": self.host, "source": self.host_source},
            "destination": {"value": self.destination, "source": self.destination_source},
        }


@dataclass(frozen=True)
class CoverArtworkSetting:
    """Whether the reader asked for custom covers, which is configuration, never a per-book ask."""

    enabled: bool = DEFAULT_COVER_ARTWORK
    source: ValueSource = "default"

    def facts(self) -> dict[str, object]:
        """State the setting with where it came from, so a default is never read as a choice."""

        return {"value": self.enabled, "source": self.source}


@dataclass(frozen=True)
class WorkspaceConfiguration:
    """One validated Workspace Configuration, resolved against its own Galley Workspace."""

    workspace: Workspace
    inboxes: tuple[InboxDefinition, ...]
    connection: Connection
    cover_artwork: CoverArtworkSetting = CoverArtworkSetting()


@dataclass(frozen=True)
class ConfigurationRefusal:
    """Why one Workspace Configuration could not be read, at the boundary that stopped it."""

    boundary: str
    stage: str
    summary: str
    fact: dict[str, object]


def read_configuration(workspace: Workspace) -> WorkspaceConfiguration | ConfigurationRefusal:
    """Parse and validate one Workspace Configuration without probing anything it names."""

    document = _parsed(workspace)
    if isinstance(document, ConfigurationRefusal):
        return document
    unknown = sorted(key for key in document if key not in TOP_LEVEL_KEYS)
    if unknown:
        return _unknown_keys(workspace, unknown, list(TOP_LEVEL_KEYS))
    if integer(document.get(VERSION_KEY)) != SUPPORTED_VERSION:
        return _unsupported_version(workspace, document.get(VERSION_KEY))
    inboxes = _inboxes(workspace, document.get(INBOX_KEY))
    if isinstance(inboxes, ConfigurationRefusal):
        return inboxes
    connection = _connection(workspace, document.get(CONNECTION_KEY))
    if isinstance(connection, ConfigurationRefusal):
        return connection
    cover_artwork = _cover_artwork(workspace, document)
    if isinstance(cover_artwork, ConfigurationRefusal):
        return cover_artwork
    return WorkspaceConfiguration(workspace, inboxes, connection, cover_artwork)


def _parsed(workspace: Workspace) -> dict[str, object] | ConfigurationRefusal:
    path = workspace.configuration
    display = display_path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return ConfigurationRefusal(
            boundary="workspace-configuration-missing",
            stage=PARSE_STAGE,
            summary=f"no Workspace Configuration at {display}",
            fact={"path": display, "workspace": display_path(workspace.path)},
        )
    except OSError as error:
        return ConfigurationRefusal(
            boundary="unreadable-workspace-configuration",
            stage=PARSE_STAGE,
            summary=f"cannot read Workspace Configuration: {display}",
            fact={"detail": str(error), "path": display, "reason": type(error).__name__},
        )
    try:
        return mapping(cast(object, tomllib.loads(raw.decode("utf-8"))))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return _invalid(workspace, "the file is not valid TOML", detail=str(error))


def _inboxes(
    workspace: Workspace, value: object
) -> tuple[InboxDefinition, ...] | ConfigurationRefusal:
    entries = sequence(value)
    if not isinstance(value, list) or not entries:
        return _invalid(workspace, f"`{INBOX_KEY}` must be a non-empty array of tables")
    definitions: list[InboxDefinition] = []
    seen: dict[str, int] = {}
    for position, stated in enumerate(entries):
        if not isinstance(stated, dict):
            return _invalid(workspace, f"`{INBOX_KEY}` entry {position} is not a table")
        entry = mapping(cast(object, stated))
        unknown = sorted(key for key in entry if key not in INBOX_KEYS)
        if unknown:
            return _unknown_keys(workspace, unknown, list(INBOX_KEYS), inside=INBOX_KEY)
        name = _required_text(entry, "name")
        path = _required_text(entry, "path")
        recursive = entry.get("recursive")
        if name is None or path is None or not isinstance(recursive, bool):
            return _invalid(
                workspace,
                f"`{INBOX_KEY}` entry {position} needs a non-empty `name` and `path` "
                "and a boolean `recursive`",
            )
        if name in seen:
            return ConfigurationRefusal(
                boundary="duplicate-inbox-name",
                stage=SCHEMA_STAGE,
                summary=f"two Inboxes are named {name}",
                fact={"name": name, "positions": [seen[name], position]},
            )
        seen[name] = position
        definitions.append(_definition(workspace, name, path, recursive=recursive))
    return tuple(definitions)


def _definition(
    workspace: Workspace, name: str, configured: str, *, recursive: bool
) -> InboxDefinition:
    """Resolve one configured path against the boundary its own spelling selects."""

    written = Path(configured)
    if configured.startswith("~"):
        resolution: PathResolution = "home-relative"
        located = written.expanduser()
    elif written.is_absolute():
        resolution = "absolute"
        located = written
    else:
        resolution = "relative"
        located = workspace.path / written
    return InboxDefinition(name, configured, resolution, resolved(located), recursive)


def _connection(workspace: Workspace, value: object) -> Connection | ConfigurationRefusal:
    if value is None:
        return Connection()
    if not isinstance(value, dict):
        return _invalid(workspace, f"`{CONNECTION_KEY}` must be a table")
    stated = mapping(cast(object, value))
    unknown = sorted(key for key in stated if key not in CONNECTION_KEYS)
    if unknown:
        return _unknown_keys(workspace, unknown, list(CONNECTION_KEYS), inside=CONNECTION_KEY)
    settings: dict[str, tuple[str, ValueSource]] = {}
    for key, fallback in (("host", DEFAULT_HOST), ("destination", DEFAULT_DESTINATION)):
        if key not in stated:
            settings[key] = (fallback, "default")
            continue
        configured = _required_text(stated, key)
        if configured is None:
            return _invalid(workspace, f"`{CONNECTION_KEY}.{key}` must be a non-empty string")
        settings[key] = (configured, "configured")
    return Connection(
        host=settings["host"][0],
        destination=settings["destination"][0],
        host_source=settings["host"][1],
        destination_source=settings["destination"][1],
    )


def _cover_artwork(
    workspace: Workspace, document: dict[str, object]
) -> CoverArtworkSetting | ConfigurationRefusal:
    """Read the optional Cover Artwork choice, or the off default when the key is absent."""

    if COVER_ARTWORK_KEY not in document:
        return CoverArtworkSetting()
    value = document[COVER_ARTWORK_KEY]
    if not isinstance(value, bool):
        return _invalid(workspace, f"`{COVER_ARTWORK_KEY}` must be a boolean")
    return CoverArtworkSetting(enabled=value, source="configured")


def _required_text(entry: dict[str, object], key: str) -> str | None:
    value = text(entry.get(key))
    return value if value and value.strip() else None


def _unknown_keys(
    workspace: Workspace, unknown: list[str], accepted: list[str], *, inside: str = ""
) -> ConfigurationRefusal:
    where = f"`{inside}`" if inside else "the Workspace Configuration"
    return ConfigurationRefusal(
        boundary="unknown-configuration-key",
        stage=SCHEMA_STAGE,
        summary=f"{where} states keys {CONFIGURATION_SCHEMA} does not define: {', '.join(unknown)}",
        fact={
            "accepted": accepted,
            "path": display_path(workspace.configuration),
            "table": inside or "",
            "unknown": unknown,
        },
    )


def _unsupported_version(workspace: Workspace, stated: object) -> ConfigurationRefusal:
    return ConfigurationRefusal(
        boundary="unsupported-configuration-version",
        stage=SCHEMA_STAGE,
        summary=f"unsupported Workspace Configuration version: {stated!r}",
        fact={
            "path": display_path(workspace.configuration),
            "stated": stated
            if isinstance(stated, int | str) and not isinstance(stated, bool)
            else None,
            "supported": [SUPPORTED_VERSION],
        },
    )


def _invalid(workspace: Workspace, summary: str, *, detail: str = "") -> ConfigurationRefusal:
    display = display_path(workspace.configuration)
    return ConfigurationRefusal(
        boundary="invalid-workspace-configuration",
        stage=PARSE_STAGE if detail else SCHEMA_STAGE,
        summary=f"invalid Workspace Configuration: {summary}",
        fact={"detail": detail, "path": display, "reason": summary},
    )

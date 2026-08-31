"""Workspace choices and their provenance, independent of parsing or interpretation."""

from dataclasses import dataclass
from typing import Literal

DEFAULT_HOST = "crosspoint.local"
DEFAULT_DESTINATION = "/"
DEFAULT_COVER_ARTWORK = False
ValueSource = Literal["configured", "default"]


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
class Customisation:
    """User-authored instructions for the agent; the CLI carries their text without acting on it."""

    instructions: str = ""
    source: ValueSource = "default"

    def facts(self) -> dict[str, object]:
        """Expose the complete text, including whitespace, and whether the user configured it."""

        return {"instructions": self.instructions, "source": self.source}

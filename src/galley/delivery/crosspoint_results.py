"""Semantic CrossPoint results and bounded exchange evidence returned by the deep client."""

from dataclasses import dataclass
from typing import Generic, TypeVar

from galley.delivery.refusals import DeliveryRefusal
from galley.json_reading import integer, mapping, text

DETAIL_LIMIT = 1_000
ResultValue = TypeVar("ResultValue")


@dataclass(frozen=True)
class Exchange:
    stage: str
    address: str
    transport: str
    status: int | None = None
    request_began: bool = False
    outcome: str = "failed"
    detail: str = ""

    def facts(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "address": self.address,
            "transport": self.transport,
            "request_began": self.request_began,
            "status": self.status,
            "outcome": self.outcome,
            "detail": self.detail[:DETAIL_LIMIT],
        }


@dataclass(frozen=True)
class ClientResult(Generic[ResultValue]):
    value: ResultValue | DeliveryRefusal
    exchanges: tuple[Exchange, ...] = ()


@dataclass(frozen=True)
class Transfer:
    status: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class DeviceStatus:
    """What one CrossPoint device said it is, with its whole answer retained."""

    model: str
    firmware: str
    mode: str | None
    status: dict[str, object]

    def facts(self) -> dict[str, object]:
        return {
            "model": self.model,
            "firmware": self.firmware,
            "mode": self.mode,
            "status": self.status,
        }


@dataclass(frozen=True)
class RemoteEntry:
    name: str
    byte_size: int | None

    def facts(self) -> dict[str, object]:
        return {"name": self.name, "byte_size": self.byte_size}


@dataclass(frozen=True)
class Listing:
    entries: tuple[RemoteEntry, ...]

    def matching(self, filename: str) -> RemoteEntry | None:
        return next((entry for entry in self.entries if entry.name == filename), None)

    def facts(self, filename: str) -> dict[str, object]:
        found = self.matching(filename)
        return {
            "entry_count": len(self.entries),
            "matching": None if found is None else found.facts(),
        }


def remote_entry(value: object) -> RemoteEntry | None:
    item = mapping(value)
    name = text(item.get("name"))
    if not name or item.get("isDirectory") is True:
        return None
    return RemoteEntry(name, integer(item.get("size")))

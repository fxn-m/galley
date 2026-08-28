"""The one structured refusal every Delivery boundary raises.

Delivery refuses in several unrelated places — a host that is not a local target, a device that
is not an X4, a book that is not a Ready Artifact — and each of them has to end up in the same
field of the same immutable record. Sharing one carrier is what keeps that true without every
boundary restating the envelope's shape.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeliveryRefusal:
    """Why one Delivery command stopped, at the boundary that stopped it."""

    boundary: str
    stage: str
    summary: str
    fact: dict[str, object] = field(default_factory=dict[str, object])

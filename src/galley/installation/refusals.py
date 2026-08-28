"""The one structured refusal every skill-lifecycle boundary raises.

Installation refuses about files it did not create: a destination holding another product's skill,
a managed installation somebody has edited, a target that cannot be written. Each of those has to
reach the same field of the same document, and each has to name what it found rather than what to
do about it.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InstallationRefusal:
    """Why one skill lifecycle command stopped, at the boundary that stopped it."""

    boundary: str
    stage: str
    summary: str
    fact: dict[str, object] = field(default_factory=dict[str, object])

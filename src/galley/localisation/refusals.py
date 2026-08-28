"""The one carrier a localisation states a stopped run with, wherever in the run it stopped.

Every step of a localisation can refuse — the source kind, the evidence directory, the source
read, the selection, a retrieval, the write — and all of them end in the same place: one
`galley/localisation/1` document with one structured refusal. So there is one type rather than
one per step, and nothing in this package has to translate a refusal from one shape into another
on its way out.

It satisfies the `Refusal` protocol `galley.documents` accepts, which is what makes the hand-off
to the envelope a pass rather than a copy.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalisationRefusal:
    """Why one localisation stopped, in the shape every command document states a refusal."""

    boundary: str
    stage: str
    summary: str
    fact: dict[str, object]

"""The shared Reading Quality Observation Registry."""

from collections.abc import Sequence
from typing import Literal, cast

Evidence = Literal["computable", "flaggable", "device-judged"]
Consequence = Literal[
    "content-loss",
    "semantic-inversion",
    "structure-loss",
    "legibility",
    "navigation",
    "contamination",
]

OBSERVATION_REGISTRY: dict[str, tuple[Evidence, Consequence]] = {
    "ordered-list-numbering-loss": ("computable", "content-loss"),
    "page-break-content-destruction": ("computable", "content-loss"),
    "unrenderable-images": ("computable", "content-loss"),
    "alt-text-fallback-absence": ("computable", "content-loss"),
    "colour-meaning-collapse": ("flaggable", "content-loss"),
    "strikethrough-inversion": ("computable", "semantic-inversion"),
    "table-relationship-loss": ("computable", "semantic-inversion"),
    "code-block-reflow": ("computable", "structure-loss"),
    "nested-list-flattening": ("computable", "structure-loss"),
    "caption-indistinction": ("computable", "structure-loss"),
    "alignment-meaning-flattening": ("flaggable", "structure-loss"),
    "boundary-chrome-presence": ("flaggable", "contamination"),
    "unrenderable-glyphs": ("computable", "legibility"),
    "diagram-text-legibility": ("flaggable", "legibility"),
    "footnote-target-reliability": ("computable", "navigation"),
    "link-footnote-dilution": ("flaggable", "navigation"),
    "pagination-granularity": ("device-judged", "navigation"),
    "ingress-conversion-acceptance": ("device-judged", "content-loss"),
    "library-title-presentation": ("device-judged", "semantic-inversion"),
    "library-author-presentation": ("device-judged", "semantic-inversion"),
    "library-cover-presentation": ("device-judged", "content-loss"),
    "navigation-usability": ("device-judged", "navigation"),
    "typography-preservation": ("device-judged", "legibility"),
    "colour-image-presentation": ("device-judged", "content-loss"),
    "footnote-usability": ("device-judged", "navigation"),
    "theme-adaptation": ("device-judged", "legibility"),
    "large-text-adaptation": ("device-judged", "legibility"),
}

OBSERVATION_NAMES = tuple(OBSERVATION_REGISTRY)

# The names measurement modules join against, spelled once here rather than in each of them.
ALT_TEXT_FALLBACK = "alt-text-fallback-absence"
BOUNDARY_CHROME = "boundary-chrome-presence"
CODE_BLOCK_REFLOW = "code-block-reflow"
COLOUR_MEANING = "colour-meaning-collapse"
DIAGRAM_TEXT = "diagram-text-legibility"
LINK_FOOTNOTE_DILUTION = "link-footnote-dilution"
FOOTNOTE_TARGET_RELIABILITY = "footnote-target-reliability"
ORDERED_LIST_NUMBERING = "ordered-list-numbering-loss"
PAGE_BREAK_DESTRUCTION = "page-break-content-destruction"
STRIKETHROUGH_INVERSION = "strikethrough-inversion"
TABLE_RELATIONSHIP_LOSS = "table-relationship-loss"
UNRENDERABLE_GLYPHS = "unrenderable-glyphs"
UNRENDERABLE_IMAGES = "unrenderable-images"


def enabled_observations(profile: dict[str, object]) -> list[str]:
    """Return the observation names one Device Profile activates, in registry order."""

    entries = profile.get("observations")
    if not isinstance(entries, list):
        return []
    activated: set[str] = set()
    for entry in cast(list[object], entries):
        if not isinstance(entry, dict):
            continue
        activation = cast(dict[str, object], entry)
        if activation.get("enabled") is not False:
            activated.add(str(activation.get("name")))
    return [name for name in OBSERVATION_NAMES if name in activated]


def merged_observations(
    profile: dict[str, object], *layers: Sequence[dict[str, object]]
) -> list[dict[str, object]]:
    """Join several layers' observations into one registry-ordered list, the last layer winning.

    `prepare` reaches some observations from two sides: the parsed source offers one it cannot
    settle, and the built artifact measures it. The measured entry replaces the projected one, so
    a Report never carries a name twice and never states a projection where it holds a
    measurement. Every other activated observation survives rather than disappearing because the
    later layer had no instrument for it. Omitting an observation would hide that a judgement is
    outstanding.
    """

    reached: dict[str, dict[str, object]] = {}
    for layer in layers:
        for entry in layer:
            reached[str(entry["name"])] = entry
    for name in enabled_observations(profile):
        evidence, _ = OBSERVATION_REGISTRY[name]
        if name not in reached and evidence == "device-judged":
            reached[name] = observation(
                name,
                applicability=None,
                fired=None,
                note=_profile_note(profile, name),
            )
    return [reached[name] for name in enabled_observations(profile) if name in reached]


def _profile_note(profile: dict[str, object], name: str) -> str:
    """Read one observation's own note without importing the profile-loading cycle."""

    entries = profile.get("observations")
    if not isinstance(entries, list):
        return ""
    for item in cast(list[object], entries):
        if isinstance(item, dict):
            entry = cast(dict[str, object], item)
            if entry.get("name") == name:
                note = entry.get("note")
                return " ".join(note.split()) if isinstance(note, str) else ""
    return ""


def observation(
    name: str,
    *,
    applicability: bool | None,
    fired: bool | None,
    measurement: dict[str, object] | None = None,
    locations: Sequence[object] | None = None,
    note: str = "",
) -> dict[str, object]:
    """Build one Report observation entry from the registry's stable definition.

    Only a computable observation may carry a judgement. Flaggable observations belong to the
    agent and device-judged ones to a human, so the CLI must not author their verdicts.
    """

    evidence, consequence = OBSERVATION_REGISTRY[name]
    if evidence != "computable" and fired is not None:
        raise ValueError(f"{name} is {evidence}; the CLI may not decide whether it fired")
    return {
        "name": name,
        "evidence": evidence,
        "consequence": consequence,
        "applicability": applicability,
        "fired": fired,
        "measurement": measurement,
        "locations": list(locations or []),
        "note": note,
    }

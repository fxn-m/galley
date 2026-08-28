"""The shared link vocabulary: what one link is to the Device Profile, wherever it is met.

Source projection, AST link stripping and artifact measurement all classify links, and the Report
pairs their numbers by requirement name. This module is the single home for that vocabulary —
the five Link Kinds, the counting rule the profile states, the scheme test, and the requirement
and activation identifiers — so a projection and a measurement can only ever disagree about a
document, never about what the words mean.
"""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from galley.json_reading import sequence
from galley.profile.loading import counting_rule as stated_counting_rule

RECORDED_LINKS_PER_BLOCK = "recorded-links-per-block"
FOOTNOTE_HREF_LENGTH = "footnote-href-length"
ANCHORS_PER_CHAPTER = "anchors-per-chapter"
STRIP_ACTIVATION = "strip_non_apparatus_hrefs"

LinkKind = Literal[
    "web-link", "footnote-reference", "footnote-back-link", "dead-link", "cross-reference"
]
Marker = Literal["", "noteref", "backlink"]
KINDS: tuple[LinkKind, ...] = (
    "cross-reference",
    "dead-link",
    "footnote-back-link",
    "footnote-reference",
    "web-link",
)


@dataclass(frozen=True)
class CountingRule:
    """The profile's own statement of which links the device records."""

    excluded_schemes: frozenset[str]
    requires_visible_text: bool


def profile_counting_rule(profile: dict[str, object], requirement_id: str) -> CountingRule:
    """Take the whole counting rule from profile data rather than restating it in code."""

    stated = stated_counting_rule(profile, requirement_id)
    return CountingRule(
        excluded_schemes=frozenset(
            str(scheme).lower() for scheme in sequence(stated.get("excluded_schemes"))
        ),
        requires_visible_text=stated.get("requires_visible_text") is not False,
    )


def is_external(href: str, rule: CountingRule) -> bool:
    """Apply the profile's counting rule exactly: only its named schemes are outside the book.

    The firmware's `isInternalEpubLink()` is a scheme test alone, so Galley adds no rule of its
    own here. Over-counting is the safe direction for a crash-class instrument.
    """

    return urlsplit(href.strip()).scheme.lower() in rule.excluded_schemes


def link_kind(*, external: bool, resolves: bool, marked: Marker = "") -> LinkKind:
    """Decide what the Device Profile does with one link, not what the markup calls it."""

    if external:
        return "web-link"
    if not resolves:
        return "dead-link"
    if marked == "noteref":
        return "footnote-reference"
    if marked == "backlink":
        return "footnote-back-link"
    return "cross-reference"

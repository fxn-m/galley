"""Shape Canonical Document evidence into projections and source-side observations.

`inspect` has no artifact, so every artifact-dependent quantity here is a projection carrying its
relation to the value `prepare` and `audit` will measure. Requirement ids are the ones the Device
Profile names, so a projection and a later measurement pair in the same Report.
"""

from collections import Counter

from galley.document.ast_reading import ReadingRule, SourceMeasurement, measure_source
from galley.document.baseline import glyph_occurrences
from galley.document.constructors import constructor_locations
from galley.profile.compatibility import INDETERMINATE, LOWER_BOUND, Instrument
from galley.document.link_kinds import (
    ANCHORS_PER_CHAPTER,
    FOOTNOTE_HREF_LENGTH,
    RECORDED_LINKS_PER_BLOCK,
    STRIP_ACTIVATION,
    profile_counting_rule,
)
from galley.observations import (
    ALT_TEXT_FALLBACK,
    BOUNDARY_CHROME,
    CODE_BLOCK_REFLOW,
    COLOUR_MEANING,
    DIAGRAM_TEXT,
    FOOTNOTE_TARGET_RELIABILITY,
    LINK_FOOTNOTE_DILUTION,
    ORDERED_LIST_NUMBERING,
    PAGE_BREAK_DESTRUCTION,
    STRIKETHROUGH_INVERSION,
    TABLE_RELATIONSHIP_LOSS,
    UNRENDERABLE_GLYPHS,
    UNRENDERABLE_IMAGES,
    enabled_observations,
    merged_observations,
    observation,
)
from galley.profile.loading import activation, observation_note, observation_tuning
from galley.report.quantities import projected, quantity

BLOCK_DEFINITION = (
    "the greatest number of in-book links carrying visible text in any one leaf block of the "
    "parsed source, counting a note's own blocks separately"
)
BOUND_NOTE = (
    "A lower bound: Pandoc's writer adds note references the AST does not carry, and this "
    "document has nothing the profile would strip — no Footnote Apparatus to trigger "
    "cross-reference removal, and no recorded link whose target this document does not already "
    "carry. A projection already above the limit proves it is broken; one below proves nothing."
)
UNBOUND_NOTE = (
    "No bound holds. Preparation strips dead links unconditionally and cross-references wherever a "
    "Footnote Apparatus exists, so this document's built artifact may carry fewer recorded links "
    "per block than its source does. Only a measurement on the built EPUB settles the requirement."
)
HREF_DEFINITION = "the longest in-book link target in UTF-8 bytes, measured on the parsed source"
HREF_NOTE = (
    "No bound holds. This profile strips hrefs outside the Footnote Apparatus and renames the "
    "rest as one file per note, so the artifact's longest href may be shorter or longer than "
    "this one. Only a measurement on the built EPUB settles the requirement."
)
ANCHOR_DEFINITION = (
    "the number of elements carrying an id attribute in the parsed source, counted across the "
    "whole document"
)
ANCHOR_NOTE = (
    "No bound holds. The requirement counts anchors per chapter, and this profile splits one "
    "source into several chapters — one file per note — so a whole-document total is neither a "
    "floor nor a ceiling on any one chapter. Galley also reads the profile's anchor limit as a "
    "count of link targets; the firmware constant's exact unit is not established by a Galley "
    "measurement."
)
GLYPH_NOTE = (
    "The profile's codepoint list is explicitly not exhaustive, so a zero count is not evidence "
    "that every glyph renders."
)
PENDING_TARGETS = (
    "No note targets exist before preparation. This is measured on the built EPUB, where a "
    "reference whose target does not resolve lands the reader somewhere other than its note."
)
PENDING_IMAGES = (
    "Image bytes are measured when preparation resolves each reference. Inspect has read the "
    "references, not the resources."
)
PENDING_ALT = (
    "Blank alt text alone is a fact, not a firing: this observation fires only where an "
    "unrenderable image also has blank alt, and renderability is measured on the artifact."
)
# The three constructs CrossPoint destroys wherever they appear, each with the Pandoc
# constructor that names it and the unit its count is stated in. Nothing here is a threshold:
# probes A3, A4 and A5 recorded unconditional destruction, so occurrence is the whole rule and
# the device behaviour behind each one stays in profile data.
DESTROYED_CONSTRUCTS = {
    STRIKETHROUGH_INVERSION: ("Strikeout", "strikeouts"),
    TABLE_RELATIONSHIP_LOSS: ("Table", "tables"),
    CODE_BLOCK_REFLOW: ("CodeBlock", "code blocks"),
}
DILUTION_NOTE = (
    "The counted primitive is recorded in-book links per block. Before preparation every such "
    "this is the same projection the block ceiling uses. Per-screen slot pressure remains "
    "uncomputable, so the CLI does not judge."
)


def source_reading(profile: dict[str, object], ast: dict[str, object]) -> SourceMeasurement:
    """Measure one Canonical Document under the Device Profile's own reading rules."""

    counting = profile_counting_rule(profile, RECORDED_LINKS_PER_BLOCK)
    return measure_source(
        ast,
        ReadingRule(
            excluded_schemes=counting.excluded_schemes,
            requires_visible_text=counting.requires_visible_text,
            page_break_markers=frozenset(
                marker.lower()
                for marker in observation_tuning(profile, PAGE_BREAK_DESTRUCTION, "markers")
            ),
            page_break_attributes=frozenset(
                name.lower()
                for name in observation_tuning(profile, PAGE_BREAK_DESTRUCTION, "attributes")
            ),
        ),
    )


def reading_facts(reading: SourceMeasurement) -> dict[str, object]:
    """Describe what the parsed source carries, independently of any Device Profile."""

    return {
        "blocks": quantity(reading.blocks, "blocks"),
        # By level rather than as a total. Extraction can demote a page's own headings, and a
        # count alone cannot show it.
        "heading_levels": {
            str(level): quantity(count, "headings")
            for level, count in sorted(Counter(reading.heading_levels).items())
        },
        "identifiers": quantity(len(reading.identifiers), "identifiers"),
        "images": quantity(reading.images, "images"),
        "images_without_alt_text": quantity(reading.images_without_alt, "images"),
        "links": quantity(len(reading.links), "links"),
        "notes": quantity(reading.notes, "notes"),
        "ordered_lists": quantity(reading.ordered_lists, "lists"),
    }


def source_instruments(
    profile: dict[str, object], reading: SourceMeasurement
) -> dict[str, Instrument]:
    """Offer the projections the navigation requirements can be evaluated against."""

    recorded = bool(reading.recorded)
    bounded = _survives_stripping(profile, reading)
    return {
        RECORDED_LINKS_PER_BLOCK: Instrument(
            value=reading.max_recorded_per_block,
            unit="recorded links",
            definition=BLOCK_DEFINITION,
            applicable=recorded,
            relation=LOWER_BOUND if bounded else INDETERMINATE,
            note=BOUND_NOTE if bounded else UNBOUND_NOTE,
        ),
        FOOTNOTE_HREF_LENGTH: Instrument(
            value=reading.max_recorded_href_bytes,
            unit="bytes",
            definition=HREF_DEFINITION,
            applicable=recorded,
            relation=INDETERMINATE,
            note=HREF_NOTE,
        ),
        ANCHORS_PER_CHAPTER: Instrument(
            value=len(reading.identifiers),
            unit="anchors",
            definition=ANCHOR_DEFINITION,
            applicable=bool(reading.identifiers),
            relation=INDETERMINATE,
            note=ANCHOR_NOTE,
        ),
    }


def _survives_stripping(profile: dict[str, object], reading: SourceMeasurement) -> bool:
    """Say whether every recorded link this source carries will still be in the built artifact.

    The interlock fires on counted zeros, not on a threshold: dead links go unconditionally, and
    cross-references go only where a Footnote Apparatus exists. Where the
    profile strips nothing, or this document offers nothing to strip, the source count is a
    genuine floor under the artifact's.
    """

    if activation(profile, STRIP_ACTIVATION) is not True:
        return True
    return reading.notes == 0 and not reading.unresolved_recorded


def source_observations(
    profile: dict[str, object], ast: dict[str, object], reading: SourceMeasurement
) -> list[dict[str, object]]:
    """Emit every observation this Device Profile activates, in registry order."""

    enabled = enabled_observations(profile)
    glyphs = glyph_occurrences(ast, observation_tuning(profile, UNRENDERABLE_GLYPHS, "codepoints"))
    located = constructor_locations(ast)
    built: dict[str, dict[str, object]] = {
        ORDERED_LIST_NUMBERING: observation(
            ORDERED_LIST_NUMBERING,
            applicability=reading.ordered_lists > 0,
            fired=bool(reading.renumbered_lists),
            measurement=quantity(len(reading.renumbered_lists), "lists"),
            locations=reading.renumbered_lists,
            note="An ordered list that restarts or is not decimal carries numbering of its own.",
        ),
        PAGE_BREAK_DESTRUCTION: observation(
            PAGE_BREAK_DESTRUCTION,
            applicability=True,
            fired=bool(reading.page_breaks),
            measurement=quantity(len(reading.page_breaks), "elements"),
            locations=reading.page_breaks,
            note=observation_note(profile, PAGE_BREAK_DESTRUCTION),
        ),
        UNRENDERABLE_GLYPHS: observation(
            UNRENDERABLE_GLYPHS,
            applicability=True,
            fired=bool(glyphs),
            measurement=quantity(sum(glyphs.values()), "codepoints"),
            locations=sorted(glyphs),
            note=GLYPH_NOTE,
        ),
        UNRENDERABLE_IMAGES: _pending(UNRENDERABLE_IMAGES, reading.images > 0, PENDING_IMAGES),
        ALT_TEXT_FALLBACK: observation(
            ALT_TEXT_FALLBACK,
            applicability=reading.images > 0,
            fired=None,
            measurement=quantity(reading.images_without_alt, "images"),
            note=PENDING_ALT,
        ),
        FOOTNOTE_TARGET_RELIABILITY: _pending(
            FOOTNOTE_TARGET_RELIABILITY, reading.notes > 0, PENDING_TARGETS
        ),
        COLOUR_MEANING: _pending(COLOUR_MEANING, reading.images > 0, PENDING_IMAGES),
        DIAGRAM_TEXT: _pending(DIAGRAM_TEXT, reading.images > 0, PENDING_IMAGES),
        LINK_FOOTNOTE_DILUTION: observation(
            LINK_FOOTNOTE_DILUTION,
            applicability=bool(reading.recorded),
            fired=None,
            measurement=projected(reading.max_recorded_per_block, "recorded links", LOWER_BOUND),
            note=DILUTION_NOTE,
        ),
        BOUNDARY_CHROME: _pending(
            BOUNDARY_CHROME, True, observation_note(profile, BOUNDARY_CHROME)
        ),
        **{name: _destroyed(profile, name, located) for name in DESTROYED_CONSTRUCTS},
    }
    return merged_observations(profile, [built[name] for name in enabled if name in built])


def _destroyed(
    profile: dict[str, object], name: str, located: dict[str, list[str]]
) -> dict[str, object]:
    """Report one construct the device destroys wherever the document happens to carry it.

    Applicability is the device's rather than the document's, as it is for a page break: the
    panel would destroy these whatever this document holds, so a document carrying none has been
    measured at zero rather than left outside the observation's scope. The note is the profile's
    own record of the probe behind the behaviour, so no device fact is restated here.
    """

    constructor, unit = DESTROYED_CONSTRUCTS[name]
    locations = located.get(constructor, [])
    return observation(
        name,
        applicability=True,
        fired=bool(locations),
        measurement=quantity(len(locations), unit),
        locations=locations,
        note=observation_note(profile, name),
    )


def _pending(name: str, applicable: bool, note: str) -> dict[str, object]:
    """Record an observation whose owner has not acted, without claiming it did not fire."""

    return observation(name, applicability=applicable, fired=None, note=note)

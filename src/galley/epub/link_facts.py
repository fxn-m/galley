"""Shape measured link evidence into Report facts, instruments, and observations."""

from galley.profile.compatibility import Instrument
from galley.document.link_kinds import (
    ANCHORS_PER_CHAPTER,
    FOOTNOTE_HREF_LENGTH,
    KINDS,
    RECORDED_LINKS_PER_BLOCK,
)
from galley.epub.links import Link, Measurement
from galley.observations import (
    FOOTNOTE_TARGET_RELIABILITY,
    LINK_FOOTNOTE_DILUTION,
    enabled_observations,
    observation,
)
from galley.report.quantities import quantity


BLOCK_DEFINITION = (
    "the greatest number of in-book links carrying visible text in any one innermost reading "
    "block, counting excluded schemes and empty anchors as unrecorded"
)
HREF_DEFINITION = (
    "the longest Recorded Link href in UTF-8 bytes, measured after XML entity decoding and "
    "before URL re-encoding"
)
ANCHOR_DEFINITION = (
    "the greatest number of elements carrying an id attribute in any one content document"
)
ANCHOR_NOTE = (
    "Galley reads the profile's anchor limit as a count of link targets. The firmware constant "
    "is recorded but its exact unit is not established by a Galley measurement."
)
TARGET_NOTE = (
    "A footnote reference whose target does not resolve lands the reader somewhere other than "
    "its note. Counted from measured references and measured identifiers."
)
DILUTION_NOTE = (
    "Counted primitive: recorded in-book links per block that are not part of a "
    "Footnote Apparatus. Per-screen slot pressure remains uncomputable, so the CLI does not judge."
)


def link_facts(measurement: Measurement) -> dict[str, object]:
    """Describe every link the artifact carries and how its targets resolved."""

    recorded = measurement.recorded
    note_references = [link for link in measurement.links if link.marked == "noteref"]
    return {
        "anchors": {
            "documents": [
                {"count": quantity(count, "anchors"), "path": path}
                for path, count in sorted(measurement.anchors.items())
            ],
            "maximum_per_document": quantity(measurement.max_anchors, "anchors"),
        },
        "blocks": quantity(len(measurement.blocks), "blocks"),
        "dead": [
            {"document": link.document, "href": link.href, "text": link.text}
            for link in sorted(measurement.links, key=_order)
            if link.kind == "dead-link"
        ],
        "complete": measurement.complete,
        "footnote_references": {
            "target_documents": quantity(_target_documents(measurement), "documents"),
            "total": quantity(len(note_references), "links"),
            "unresolved": quantity(_unresolved(measurement), "links"),
        },
        "kinds": {kind: quantity(_count(measurement, kind), "links") for kind in KINDS},
        "maximum_recorded_href_bytes": quantity(measurement.max_href_bytes, "bytes"),
        "maximum_recorded_per_block": quantity(measurement.max_recorded_per_block, "links"),
        "recorded": quantity(len(recorded), "links"),
        "total": quantity(len(measurement.links), "links"),
    }


def link_instruments(measurement: Measurement, *, chapters: int) -> dict[str, Instrument]:
    """Offer the measured quantities the navigation requirements are evaluated against."""

    recorded = bool(measurement.recorded)
    return {
        RECORDED_LINKS_PER_BLOCK: Instrument(
            value=measurement.max_recorded_per_block,
            unit="recorded links",
            definition=BLOCK_DEFINITION,
            applicable=recorded,
            reliable=measurement.complete,
        ),
        FOOTNOTE_HREF_LENGTH: Instrument(
            value=measurement.max_href_bytes,
            unit="bytes",
            definition=HREF_DEFINITION,
            applicable=recorded,
            reliable=measurement.complete,
        ),
        ANCHORS_PER_CHAPTER: Instrument(
            value=measurement.max_anchors,
            unit="anchors",
            definition=ANCHOR_DEFINITION,
            applicable=chapters > 0,
            reliable=measurement.complete,
            note=ANCHOR_NOTE,
        ),
    }


def navigation_observations(
    profile: dict[str, object], measurement: Measurement
) -> list[dict[str, object]]:
    """Emit the navigation observations this Device Profile activates."""

    enabled = enabled_observations(profile)
    results: list[dict[str, object]] = []
    if FOOTNOTE_TARGET_RELIABILITY in enabled:
        references = [link for link in measurement.links if link.marked == "noteref"]
        unresolved = _unresolved(measurement)
        results.append(
            observation(
                FOOTNOTE_TARGET_RELIABILITY,
                applicability=bool(references),
                fired=unresolved > 0 if measurement.complete else None,
                measurement=quantity(unresolved, "links") if measurement.complete else None,
                locations=sorted({link.document for link in references if not link.resolves}),
                note=TARGET_NOTE,
            )
        )
    if LINK_FOOTNOTE_DILUTION in enabled:
        in_book = [link for link in measurement.links if link.kind != "web-link"]
        results.append(
            observation(
                LINK_FOOTNOTE_DILUTION,
                applicability=bool(in_book),
                fired=None,
                measurement=quantity(
                    measurement.max_non_footnote_recorded_per_block, "recorded links"
                )
                if measurement.complete
                else None,
                locations=_locations(measurement),
                note=DILUTION_NOTE,
            )
        )
    return results


def _target_documents(measurement: Measurement) -> int:
    """Count the distinct content documents this book's note references land in.

    One file per note means as many target documents as references. A book whose references all
    land in one document carries the same-file notes section measured as misdirecting.
    """

    return len(
        {
            link.target_document
            for link in measurement.links
            if link.marked == "noteref" and link.target_document is not None
        }
    )


def _unresolved(measurement: Measurement) -> int:
    return sum(1 for link in measurement.links if link.marked == "noteref" and not link.resolves)


def _locations(measurement: Measurement) -> list[object]:
    return list(sorted({block.document for block in measurement.blocks}))


def _count(measurement: Measurement, kind: str) -> int:
    return sum(1 for link in measurement.links if link.kind == kind)


def _order(link: Link) -> tuple[str, str]:
    return (link.document, link.href)

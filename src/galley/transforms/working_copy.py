"""Build the private working copy preparation hands to the writer, and record what it did.

The fixed order runs strip links, then convert notes, then prepare images and cover, all on a
working copy. The persisted Canonical Document stays as parsed, so
every transform here rebuilds rather than edits, and each returns the Report record that says
whether it fired and why.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from galley.document.ast_reading import SourceMeasurement
from galley.images.facts import image_transform
from galley.json_reading import integer
from galley.report.quantities import amount, group
from galley.images.preparation import ImagePreparation, prepare_images
from galley.images.resources import ResourceOrigin
from galley.images.records import image_dependencies, image_records
from galley.document.link_kinds import (
    FOOTNOTE_HREF_LENGTH,
    RECORDED_LINKS_PER_BLOCK,
    STRIP_ACTIVATION,
    profile_counting_rule,
)
from galley.transforms.attributes import attribute_transform, namespace_attributes
from galley.transforms.callouts import callout_transform, emphasise_callout_titles
from galley.transforms.figures import caption_transform, suppress_derived_captions
from galley.transforms.identifiers import bound_identifiers, identifier_transform
from galley.transforms.raw_html import balance_raw_html, raw_html_transform
from galley.transforms.links import link_transform, strip_links
from galley.transforms.notes import (
    FOOTNOTE_BACKLINKS,
    ONE_FILE_PER_NOTE,
    convert_notes,
    note_transform,
)
from galley.tools.packaging import (
    IDENTIFIER_SCHEME,
    SOURCE_DATE_EPOCH,
    Packaging,
    artifact_identifier,
    ast_digest,
)
from galley.profile.loading import activation, enforced_limit
from galley.report.envelope import ReportAssembly
from galley.report.quantities import quantity
from galley.document.canonical import DocumentLanguage
from galley.transforms.metadata import TOC_DEPTH, metadata_transforms, navigation_transform


@dataclass(frozen=True)
class WorkingCopy:
    """One private copy of a Canonical Document and the record of every transform applied to it."""

    ast: dict[str, object]
    transforms: list[dict[str, object]]
    notes: int
    """The number of Notes the conversion converted, which the artifact must then agree with."""
    converted: bool
    """Whether this profile asked for one file per note at all, and so whether that check applies."""
    images: ImagePreparation
    """Every image reference this copy resolved, and every one it could not."""


def working_copy(
    profile: dict[str, object],
    document: dict[str, object],
    reading: SourceMeasurement,
    *,
    origin: ResourceOrigin,
    workspace: Path,
    title: str,
    author: str | None,
) -> WorkingCopy:
    """Apply every Device Profile transform to a copy of the retained Canonical Document.

    Stripping must come first: once the notes are converted, every reference is a cross-file
    in-book link indistinguishable from a
    cross-reference, so a stripping pass running afterwards would eat exactly the links the
    conversion just created.

    The measurement the reading already took supplies both counted zeros the interlock turns on —
    the document's own identifiers and its recognised notes — so nothing walks this
    AST a second time to reach them.

    Images come last because the references a note conversion moves into their own documents are
    references this pass must still resolve.
    Raw-HTML balancing and identifier bounding run immediately before them, once every node the
    book will carry exists: the note conversion creates the documents an href reaches, so bounding
    earlier would leave the identifiers it creates unmeasured, and balancing earlier would judge a
    document the writer is not going to be given.

    Caption suppression runs first, before anything measures or rewrites the document, so that no
    later pass counts a link or an identifier inside a caption this book is not going to print,
    and so that the equality it tests is read on the document exactly as parsed — the same
    document the Preservation Baseline is rendered from, rather than one four passes have already
    rewritten. Callout emphasis runs beside it and for the same reason: it matches an exact
    nesting of divs the extractor emits, and every pass after it is one that could have moved a
    node out of that shape.
    """

    captions = suppress_derived_captions(cast(dict[str, object], document["pandoc"]))
    callouts = emphasise_callout_titles(captions.ast)
    ast = callouts.ast
    stripping = strip_links(
        ast,
        rule=profile_counting_rule(profile, RECORDED_LINKS_PER_BLOCK),
        identifiers=reading.identifiers,
        notes=reading.notes,
        activated=activation(profile, STRIP_ACTIVATION) is True,
    )
    conversion = convert_notes(
        stripping.ast,
        activated=activation(profile, ONE_FILE_PER_NOTE) is True,
        backlinks=activation(profile, FOOTNOTE_BACKLINKS) is True,
    )
    balance = balance_raw_html(conversion.ast)
    bounding = bound_identifiers(
        balance.ast,
        limit=enforced_limit(profile, FOOTNOTE_HREF_LENGTH),
        title=title,
    )
    images = prepare_images(
        bounding.ast,
        profile=profile,
        origin=origin,
        workspace=workspace,
        title=title,
        author=author,
    )
    # Last, so that nothing applied before it can put an attribute back on an element the output
    # format will not take one on.
    namespacing = namespace_attributes(images.ast)
    return WorkingCopy(
        ast=namespacing.ast,
        transforms=[
            caption_transform(captions),
            callout_transform(callouts),
            link_transform(profile, stripping),
            note_transform(profile, conversion),
            raw_html_transform(balance),
            identifier_transform(bounding),
            image_transform(profile, images),
            attribute_transform(namespacing),
        ],
        notes=conversion.notes,
        converted=conversion.activated,
        images=images,
    )


def note_mismatch(
    facts: dict[str, object], copy: WorkingCopy, source_notes: int
) -> dict[str, object] | None:
    """Say where a built book disagrees with the note representation preparation asked for.

    The counts are reached by three different paths: the Canonical Document reading, the
    conversion's own walk, and the measurement `audit` takes on the built EPUB. A book where
    *some* references resolve and one does not is a silent failure, so a disagreement refuses
    rather than publishing a book that passes casual testing.

    The artifact counts are read as floors, not as equalities. A source may carry its own marked
    note reference that the link interlock retained because it could not be classified, and that
    is a link this book was always going to keep — not evidence that a converted note went
    missing. What must not happen is fewer references than notes, a reference that lands nowhere,
    or references sharing a document, which is the unsupported same-file notes-section layout.
    """

    if not copy.converted:
        return None
    references = group(group(facts, "links"), "footnote_references")
    counts = {
        "converted_notes": copy.notes,
        "note_documents": amount(references, "target_documents"),
        "references": amount(references, "total"),
        "source_notes": source_notes,
        "unresolved_references": amount(references, "unresolved"),
    }
    disagreements = [
        reason
        for reason, wrong in (
            ("source-count-disagreement", source_notes != copy.notes),
            ("missing-references", cast(int, counts["references"]) < copy.notes),
            ("unresolved-references", counts["unresolved_references"] != 0),
            ("shared-note-documents", cast(int, counts["note_documents"]) < copy.notes),
        )
        if wrong
    ]
    if not disagreements:
        return None
    return {
        **{name: quantity(cast(int, value), _unit(name)) for name, value in counts.items()},
        "disagreements": disagreements,
    }


def _unit(name: str) -> str:
    return "documents" if name == "note_documents" else "notes" if "notes" in name else "links"


def toc_depth(profile: dict[str, object]) -> int | None:
    """Take the navigation depth from the Device Profile, or nothing where it states none.

    Device facts live in profile data, so there is no default here to fall back on. A profile that
    activates no navigation depth leaves Pandoc's own to stand, and the transform
    records that it did not fire rather than reporting an invented depth as profile-sourced.
    """

    return integer(activation(profile, TOC_DEPTH))


def preparation_facts(
    report: ReportAssembly,
    document: dict[str, object],
    packaging: Packaging,
    profile: dict[str, object],
    depth: int | None,
    copy: WorkingCopy,
    language: DocumentLanguage,
) -> ReportAssembly:
    """Record what preparation did to the Canonical Document, and what packaged it."""

    canonical = cast(dict[str, object], report["canonical_document"])
    retained = ast_digest(cast(dict[str, object], document["pandoc"]))
    return image_dependencies(report, copy.images).add_facts(
        "preparation",
        {
            "canonical_document": {
                "packaged_ast_sha256": packaging.ast_sha256,
                "retained_ast_sha256": retained,
                "sha256": canonical["sha256"],
                "transformed": packaging.ast_sha256 != retained,
            },
            "artifact_identity": {
                "identifier": artifact_identifier(cast(str, canonical["sha256"])),
                "scheme": IDENTIFIER_SCHEME,
                "source_date_epoch": SOURCE_DATE_EPOCH,
            },
            "images": image_records(copy.images, None),
            "packaging": packaging.facts,
            "transforms": [
                *metadata_transforms(document, canonical, language),
                *copy.transforms,
                navigation_transform(profile, depth),
            ],
        },
    )


def published_images(
    report: ReportAssembly,
    copy: WorkingCopy,
    facts: dict[str, object],
    previews: dict[str, dict[str, str]],
) -> ReportAssembly:
    """Join each prepared image to the resource the measured book actually carries.

    Preparation states what it packaged and `audit` states what the archive holds; neither is
    asked to take the other's word for it. Recording both sides of the join is what makes the
    Image Preservation claim checkable rather than asserted.
    """

    preparation = cast(dict[str, object], report["preparation"])
    joined = image_records(copy.images, facts, previews)
    return report.add_facts("preparation", {**preparation, "images": joined})

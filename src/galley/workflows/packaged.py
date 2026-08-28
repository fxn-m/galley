"""The one pipeline every prepared book goes down, whatever produced its Canonical Document.

Markdown, an extracted Article-Like Page and an agent-repaired document differ only in how the
Canonical Document was obtained. From here they are the same run: transform, package, audit the
candidate, measure preservation, enforce every refusal boundary and stage the artifact. Keeping
that as one function is what makes "the repaired form passes through the same pipeline" a fact
about the code rather than a claim about it.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from galley.document.ast_reading import SourceMeasurement
from galley.document.facts import source_observations
from galley.document.preservation import compare_text
from galley.images.cover import cover_template
from galley.images.normalisation import image_rule
from galley.images.previews import (
    Preview,
    preview_files,
    preview_observations,
    preview_payloads,
    previews,
)
from galley.images.records import image_mismatch
from galley.images.resources import ResourceOrigin
from galley.locations import display_path
from galley.observations import merged_observations
from galley.output.publication import Collision, Destination, stage
from galley.report.envelope import with_facts
from galley.document.canonical import canonical_digest
from galley.tools.packaging import BookMetadata, artifact_identifier, package_epub3
from galley.transforms.raw_html import malformed_documents
from galley.transforms.working_copy import (
    note_mismatch,
    preparation_facts,
    published_images,
    toc_depth,
    working_copy,
)
from galley.workflows.audit import ArtifactAssessment, Unreadable, assess_artifact, with_assessment
from galley.workflows.parsed import Inspection
from galley.workflows.refusals import (
    Preparation,
    artifact_collided,
    candidate_unreadable,
    compatibility_refused,
    content_malformed,
    images_unpreserved,
    images_unprepared,
    notes_mismatched,
    packaging_refused,
    text_unpreserved,
)

RESOURCES = "resources"


def packaged(
    profile: dict[str, object],
    inspection: Inspection,
    destination: Destination,
    origin: ResourceOrigin,
    expected_missing: dict[str, int],
) -> Preparation:
    """Take one Canonical Document through the whole contract, then stage the book it produced.

    The destination is asked for its path once the candidate exists, because a Ready Artifact's
    name can depend on its own bytes. Everything before that point is identical whatever mode
    published it, which is what keeps "the full preparation, Compatibility, preservation and
    audit contract completes before Ready publication" a fact about this function.
    """

    document = cast(dict[str, object], inspection.document)
    reading = cast(SourceMeasurement, inspection.reading)
    ast = cast(dict[str, object], document["pandoc"])
    depth = toc_depth(profile)
    with TemporaryDirectory() as workspace:
        copy = working_copy(
            profile,
            document,
            reading,
            origin=origin,
            workspace=Path(workspace) / RESOURCES,
            title=cast(str, document["title"]),
        )
        if copy.images.failures:
            return images_unprepared(inspection, copy)
        packaging = package_epub3(
            copy.ast,
            workspace=Path(workspace),
            metadata=BookMetadata(
                title=cast(str, document["title"]),
                author=cast(str | None, document["author"]),
                identifier=artifact_identifier(canonical_digest(document)),
                language=inspection.language.value,
                translations=inspection.language.translations,
            ),
            resources=Path(workspace) / RESOURCES,
            toc_depth=depth,
            cover=copy.cover,
            cover_template=cover_template,
        )
        report = preparation_facts(
            inspection.report, document, packaging, profile, depth, copy, inspection.language
        )
        if packaging.artifact is None:
            return packaging_refused(report, inspection, packaging)
        publication = destination.publication_for(packaging.artifact, cast(str, document["title"]))
        if isinstance(publication, Collision):
            return artifact_collided(report, inspection, publication)
        assessed = assess_artifact(
            profile, packaging.artifact, display=display_path(publication.output)
        )
        if isinstance(assessed, Unreadable):
            return candidate_unreadable(report, inspection, publication, assessed)
        rendered = previews(copy.images, image_rule(profile))
        evidence = preview_payloads(rendered)
        report = published_images(report, copy, assessed.facts, preview_files(rendered))
        report = with_assessment(
            report,
            assessed,
            observations=_observations(profile, ast, reading, assessed, rendered),
        )
        artifact = cast(dict[str, object], report["artifact"])
        preservation = compare_text(
            cast(str, inspection.baseline),
            assessed.text_segments,
            expected_missing,
            discarded=inspection.discards,
        )
        report = with_facts(
            report,
            "artifact",
            {**artifact, "text_preservation": preservation.facts},
        )
        malformed = malformed_documents(artifact)
        if malformed:
            return content_malformed(report, inspection, malformed, evidence)
        incompatible = compatibility_refused(report, inspection, evidence)
        if incompatible is not None:
            return incompatible
        if preservation.unexpected_missing:
            return text_unpreserved(report, inspection, preservation, evidence)
        mismatch = note_mismatch(assessed.facts, copy, reading.notes)
        if mismatch is not None:
            return notes_mismatched(report, inspection, mismatch, evidence)
        lost = image_mismatch(assessed.facts, copy.images)
        if lost["unmapped"]:
            return images_unpreserved(report, inspection, lost, evidence)
        staged = stage(publication, packaging.artifact)
    return Preparation(
        report,
        document,
        inspection.baseline,
        inspection.extraction,
        staged,
        retains_evidence=True,
        previews=evidence,
    )


def _observations(
    profile: dict[str, object],
    ast: dict[str, object],
    reading: SourceMeasurement,
    assessed: ArtifactAssessment,
    rendered: list[Preview],
) -> list[dict[str, object]]:
    """Keep every activated observation, letting the built artifact settle the ones it measured.

    The source layer sees what no EPUB reading can recover — an ordered list that carried its own
    numbering, a page break, a codepoint the panel does not render — and the artifact layer
    settles the ones only a real book answers. Dropping either layer would silently retire a
    judgement rather than reporting that it is outstanding. The previews come last because they
    are the only layer that can offer the agent evidence for its two image observations, and
    offering it replaces the artifact layer's entry rather than joining it.
    """

    return merged_observations(
        profile,
        source_observations(profile, ast, reading),
        assessed.observations,
        preview_observations(profile, rendered),
    )

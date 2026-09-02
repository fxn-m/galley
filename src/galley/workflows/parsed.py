"""Assemble everything a Pandoc parse establishes, whatever produced the bytes it read.

Markdown and an extracted Article-Like Page reach the Canonical Document by different routes and
converge here. Both need the same envelope, the same Preservation Baseline, the same reading and
the same facts about them, so this is one function rather than two that drift: only the title,
author and source URL each route establishes for itself are handed in.
"""

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Self, cast

from galley.document.ast_reading import SourceMeasurement
from galley.document.baseline import preservation_baseline
from galley.document.canonical import (
    CANONICAL_SCHEMA_ID,
    DEFAULT_LANGUAGE_SOURCE,
    UNDETERMINED,
    DocumentLanguage,
    TitleSource,
    canonical_digest,
    canonical_document,
    document_language,
)
from galley.document.constructors import constructor_facts
from galley.document.discards import Discard, reader_discards
from galley.document.facts import (
    reading_facts,
    source_instruments,
    source_observations,
    source_reading,
)
from galley.json_reading import sequence
from galley.release_data import pinned_pandoc_version
from galley.profile.compatibility import evaluate_requirements
from galley.report.envelope import ReportAssembly
from galley.report.quantities import quantity
from galley.tools.pandoc import DEFAULT_COMMAND, Parse, api_version

ENCODING = "utf-8"
PARSE_STAGE = "source-parse"
WARNING_EVENT = "pandoc-message"


@dataclass(frozen=True)
class Inspection:
    """One inspection: its Report, the evidence a later command may be handed, and its reading."""

    report: ReportAssembly
    document: dict[str, object] | None = None
    baseline: str | None = None
    reading: SourceMeasurement | None = None
    """What the parsed source carries under the profile's reading rules, measured once.

    Both commands need it — `inspect` to project, `prepare` to observe what no artifact
    measurement can settle — and neither should walk the same AST a second time to get it.
    """
    extraction: str | None = None
    """The extractor's own cleaned HTML, where a source had an extraction stage at all."""
    discards: list[Discard] = field(default_factory=list[Discard])
    """What the reader that produced this document said it dropped while reading the source."""
    language: DocumentLanguage = DocumentLanguage(UNDETERMINED, DEFAULT_LANGUAGE_SOURCE)
    """The language the artifact will declare, and which of the four places decided it."""

    def complete(self) -> Self:
        """Validate the final Report when this inspection crosses its workflow seam."""

        self.report.complete()
        return self


def parsed_inspection(
    report: ReportAssembly,
    profile: dict[str, object],
    parse: Parse,
    *,
    title: str,
    title_source: TitleSource,
    author: str | None,
    source_url: str | None,
    language: str | None = None,
) -> Inspection:
    """Wrap one parsed AST in the Canonical Document, its baseline, its reading and its facts."""

    ast = parse.ast or {}
    document = canonical_document(
        ast, title=title, author=author, source_url=source_url, warnings=parse_warnings(parse)
    )
    baseline, segments = preservation_baseline(ast)
    return document_inspection(
        report,
        profile,
        document,
        title_source=title_source,
        baseline=baseline,
        segments=segments,
        language=language,
    )


def document_inspection(
    report: ReportAssembly,
    profile: dict[str, object],
    document: dict[str, object],
    *,
    title_source: TitleSource,
    baseline: str,
    segments: int,
    language: str | None = None,
) -> Inspection:
    """Describe one Canonical Document and the baseline retained beside it, whoever built it.

    A parsed document and an agent-repaired one arrive here identically, which is the point: the
    reading, the facts and the warnings are properties of the document, not of what produced it.
    The baseline is handed in rather than derived, because a repair's baseline is the retained
    pre-repair text and deriving one from the repaired AST would compare it against itself.
    """

    ast = cast(dict[str, object], document["pandoc"])
    reading = source_reading(profile, ast)
    warnings = cast(list[dict[str, object]], document["warnings"])
    # Read from the document's own warnings rather than from a parse, so an agent-repaired
    # document carries what the reader that first read its source discarded. `localise` is where
    # that matters: its parse is the one that ran, and `prepare` never sees it.
    # Carried on the Inspection rather than reported here. `canonical_document` is a pure function
    # of the AST, and a discard is exactly what that AST cannot show; `source` on a
    # repaired run states nothing this run measured. It is reported where the claim it qualifies
    # is made, in `artifact.text_preservation`, and that claim only exists once a book is built.
    discards = reader_discards([str(warning.get("detail")) for warning in warnings])
    declared = document_language(ast, stated=language)
    report.add_facts(
        "canonical_document",
        {
            **canonical_facts(document, ast, title_source, baseline, segments),
            "reading": reading_facts(reading),
        },
    )
    report.add_warnings(warnings)
    return Inspection(
        report,
        document,
        baseline,
        reading,
        discards=discards,
        language=declared,
    )


def parser_facts(parse: Parse) -> dict[str, object]:
    """Name the exact tool, reader and version that produced this AST.

    The pinned version is stated beside the observed one rather than enforced: a different Pandoc
    still parses, and the Report says which one did instead of implying the pinned one ran.
    """

    return {
        "matches_pinned_version": parse.matches_pinned_version,
        "pinned_version": pinned_pandoc_version(),
        "reader": parse.reader,
        "tool": DEFAULT_COMMAND,
        "version": parse.version,
    }


def canonical_facts(
    document: dict[str, object],
    ast: dict[str, object],
    title_source: TitleSource,
    baseline: str,
    segments: int,
) -> dict[str, object]:
    """Describe the Canonical Document a parse produced and the baseline retained beside it."""

    encoded = baseline.encode(ENCODING)
    return {
        **constructor_facts(ast),
        "author": document["author"],
        "blocks": quantity(len(sequence(ast.get("blocks"))), "blocks"),
        "pandoc_api_version": api_version(ast),
        "preservation_baseline": {
            "byte_size": quantity(len(encoded), "bytes"),
            "encoding": ENCODING,
            "segments": quantity(segments, "segments"),
            "sha256": sha256(encoded).hexdigest(),
        },
        "schema": CANONICAL_SCHEMA_ID,
        "sha256": canonical_digest(document),
        "source_url": document["source_url"],
        "title": document["title"],
        "title_source": title_source,
    }


def parse_warnings(parse: Parse) -> list[dict[str, object]]:
    """Keep Pandoc's own construction messages, which leave no trace in the finished AST."""

    return [
        {"stage": PARSE_STAGE, "event": WARNING_EVENT, "detail": message, "recomputable": False}
        for message in parse.messages
    ]


def projected(profile: dict[str, object], inspection: Inspection) -> Inspection:
    """Join the profile's projected Requirement Verdicts and observations onto one inspection.

    Both source routes project the same way, because the projection reads the Canonical Document
    rather than whatever produced it.
    """

    if inspection.document is None or inspection.reading is None:
        return inspection
    ast = cast(dict[str, object], inspection.document["pandoc"])
    reading = inspection.reading
    inspection.report.add_evaluation(
        compatibility=evaluate_requirements(profile, source_instruments(profile, reading)),
        observations=source_observations(profile, ast, reading),
    )
    return Inspection(
        inspection.report,
        inspection.document,
        inspection.baseline,
        reading,
        inspection.extraction,
    )

"""Turn one accepted repair into the inspection every other source produces, plus its lineage.

The agent is the repair layer, and a Bespoke Repair stays with that agent permanently, so
`prepare` must consume a document Galley did not produce. Acceptance is
`repair_inputs`' job; this module's job is what an accepted repair becomes. What this run did not
do it inherits and marks `reported`; what it did do it measures. The chain it records is what
lets a reader walk from the built book back to the bytes that were inspected.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from galley.document.canonical import TitleSource, canonical_digest
from galley.json_reading import integer, mapping, text
from galley.locations import display_path
from galley.report.envelope import ReportAssembly
from galley.report.quantities import amount, reported
from galley.sources import MARKDOWN
from galley.workflows.parsed import Inspection, document_inspection
from galley.workflows.repair_inputs import (
    MISMATCH,
    REPAIR_STAGE,
    RepairInputs,
    accepted_title_source,
    file_digest,
    mismatch_reason,
    read_inputs,
    source_digest,
    text_digest,
)


@dataclass(frozen=True)
class Repair:
    """One accepted repair: the document to prepare, the retained baseline, and the chain."""

    document: dict[str, object]
    baseline: str
    segments: int
    title_source: TitleSource
    source: dict[str, object]
    extraction: dict[str, object] | None
    lineage: dict[str, object]


def accepted_repair(
    report: ReportAssembly,
    inputs: RepairInputs,
    *,
    profile: dict[str, object],
    source: str,
    kind: str,
) -> Repair | ReportAssembly:
    """Validate all three Repair Inputs and tie them to this preparation, or refuse saying why.

    Every check happens before the document reaches any transform, because a repair that does not
    belong to this source must never contribute a single fact to the Report that follows it.
    """

    read = read_inputs(report, inputs)
    if isinstance(read, tuple):
        inspection, document, baseline = read
    else:
        return read
    observed = source_digest(Path(source)) if kind == MARKDOWN else None
    mismatch = mismatch_reason(
        inspection,
        document,
        baseline,
        profile=profile,
        source=source,
        kind=kind,
        observed=observed,
    )
    if mismatch is not None:
        return report.refuse(
            boundary=MISMATCH,
            stage=REPAIR_STAGE,
            summary=f"the repair inputs do not describe this preparation: {mismatch['detail']}",
            fact=mismatch,
        )
    title_source = accepted_title_source(report, inputs, inspection)
    if not isinstance(title_source, str):
        return title_source
    canonical = mapping(inspection.get("canonical_document"))
    return Repair(
        document=document,
        baseline=baseline,
        segments=_segments(canonical, baseline),
        title_source=title_source,
        source=inherited(mapping(inspection.get("source"))),
        extraction=(
            None
            if inspection.get("extraction") is None
            else inherited(mapping(inspection.get("extraction")))
        ),
        lineage=_lineage(inputs, inspection, document, baseline, canonical, observed),
    )


def _segments(canonical: dict[str, object], baseline: str) -> int:
    """Take the segment count the inspection measured over these exact bytes.

    Recounting the text cannot recover it: a line block is one segment carrying its own newlines,
    so counting lines would report a different number for a baseline proven byte-identical. The
    hash check has already established that these are the bytes that count was taken over.
    """

    stated = integer(amount(mapping(canonical.get("preservation_baseline")), "segments"))
    return stated if stated is not None else len(baseline.splitlines())


def inherited(facts: dict[str, object]) -> dict[str, object]:
    """Restate facts this run did not establish, so no quantity claims an instrument it lacked.

    Every number carries its basis. A repaired preparation ran no extractor and reparsed no
    source, so what it takes from the inspection Report is dependency-`reported`
    however that Report obtained it. A projection loses its relation along with its basis, because
    a stated relation to a measurable value is a claim only the command that projected it made.
    """

    return cast(dict[str, object], _restated(facts))


def _restated(value: object) -> object:
    if isinstance(value, dict):
        node = cast(dict[str, object], value)
        if "basis" in node and "value" in node:
            return reported(cast(int, node["value"]), text(node.get("unit")))
        return {key: _restated(item) for key, item in node.items()}
    if isinstance(value, list):
        return [_restated(item) for item in cast(list[object], value)]
    return value


def _lineage(
    inputs: RepairInputs,
    inspection: dict[str, object],
    document: dict[str, object],
    baseline: str,
    canonical: dict[str, object],
    observed: str | None,
) -> dict[str, object]:
    """Record the chain from the inspected source to the form this preparation will package.

    This is a `source` fact because `source` describes what was handed in, and what was handed in
    is three files. It cannot be a `canonical_document` fact: that category is a pure function of
    the AST and the Modelled Set, and a file path, a run id and a source digest are none of those.

    Four links are named here and the fifth is the artifact, whose digest stays in the `artifact`
    category where `audit` also reads it: copying a hash into two places only creates somewhere
    for the two copies to disagree. Both Canonical Document digests are of the canonical
    serialisation rather than of the files, so the original and the repaired form are comparable.
    """

    stated = mapping(inspection.get("source"))
    repaired = canonical_digest(document)
    return {
        "changed": repaired != canonical.get("sha256"),
        "inspection_report": {
            "command": mapping(inspection.get("galley")).get("command"),
            "path": display_path(inputs.report),
            "run_id": mapping(inspection.get("galley")).get("run_id"),
            "sha256": file_digest(inputs.report),
        },
        "original_canonical_document": {"sha256": canonical.get("sha256")},
        "preservation_baseline": {
            "path": display_path(inputs.baseline),
            "sha256": text_digest(baseline),
        },
        "repaired_canonical_document": {
            "path": display_path(inputs.document),
            "sha256": repaired,
        },
        "source": {
            "kind": stated.get("kind"),
            "path": stated.get("path"),
            "sha256": observed if observed is not None else stated.get("sha256"),
            "url": stated.get("url"),
        },
    }


def repaired_inspection(
    report: ReportAssembly, profile: dict[str, object], repair: Repair
) -> Inspection:
    """Describe one accepted repair the way every other source is described, plus its lineage.

    What this run did not do it inherits and marks `reported`; what it did do — reading the
    repaired document under the profile's rules, and describing the baseline it was handed — it
    measures here. The lineage joins the `source` facts, which is the category that describes what
    was handed in, and it lands before any transform runs so every later refusal carries it too.
    """

    carried = report.add_facts("source", {**repair.source, "repair": repair.lineage})
    if repair.extraction is not None:
        carried.add_facts("extraction", repair.extraction)
    return document_inspection(
        carried,
        profile,
        repair.document,
        title_source=repair.title_source,
        baseline=repair.baseline,
        segments=repair.segments,
    )

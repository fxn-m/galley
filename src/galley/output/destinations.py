"""Protect every path a preparation owns before it does the work that would fill them.

Both destinations are checked together and before any parse, packaging run or audit, because a
run that cannot publish should not pay for the book it would then discard. Input protection is
asked first, so naming an input as the output is refused as exactly that rather than as an
occupied path.

A Ready publication owns fewer paths this early than an explicit output does: its artifact's
name can depend on bytes that do not exist yet, so only its evidence bundle can be protected
here. The artifact's own name is settled and checked at the moment the candidate exists.
"""

from collections.abc import Sequence
from pathlib import Path

from galley.output.evidence import evidence_destinations
from galley.locations import display_path
from galley.output.publication import ARTIFACT_STAGE, candidate_path, occupied_fact
from galley.output.policy import input_collision, output_is_input_report
from galley.report.envelope import ReportAssembly

EVIDENCE_SUFFIX = ".galley"


def evidence_directory(output: Path, chosen: Path | None) -> Path:
    """Name the companion evidence directory: the EPUB output's stem plus `.galley`."""

    return chosen if chosen is not None else output.with_suffix(EVIDENCE_SUFFIX)


def artifact_destinations(output: Path | None) -> list[Path]:
    """Name every path publishing one named EPUB would write, so each can be protected."""

    return [] if output is None else [output, candidate_path(output)]


def destination_refusal(
    report: ReportAssembly,
    source: Path | None,
    artifact: Sequence[Path],
    evidence: Path | None,
    *,
    overwrite: bool,
    additional_inputs: Sequence[Path] = (),
) -> ReportAssembly | None:
    """Refuse an unusable artifact or evidence destination before any expensive work.

    Input protection is asked first, so naming an input as the output is refused as exactly
    that rather than as an occupied path. Both destinations are then checked together, so a run
    that would refuse on its evidence directory never pays for a parse and a packaging run.

    A Ready publication passes neither: its artifact's name depends on bytes that do not exist
    yet, and its evidence bundle is keyed by a source provenance the Report has not established.
    Both are settled and checked when they are known, and the refusal is the same one.
    """

    owned = [*artifact, *([] if evidence is None else evidence_destinations(evidence))]
    inputs = [*additional_inputs]
    if source is not None:
        inputs.insert(0, source)
    collision = input_collision(inputs, owned)
    if collision is not None:
        return output_is_input_report(report, collision, ARTIFACT_STAGE)
    if overwrite:
        return None
    taken = next((path for path in owned if path.exists()), None)
    if taken is None:
        return None
    return report.refuse(
        boundary="output-exists",
        stage=ARTIFACT_STAGE,
        summary=f"prepared output already exists: {display_path(taken)}",
        fact=occupied_fact(taken),
    )

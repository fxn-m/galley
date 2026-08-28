"""Apply input protection and deterministic report-output policy."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from galley.output.evidence import STAGE, EvidenceBundle, EvidenceRefusal, write_evidence
from galley.locations import display_path
from galley.outcomes import ExitCode
from galley.report.envelope import (
    Report,
    ReportRun,
    finish_report,
    replace_refusal,
    report_json,
    validate_report,
)

REPORT_STAGE = "report-output"


@dataclass(frozen=True)
class ReportEmission:
    """A canonical Report paired with its public process outcome."""

    report: Report
    exit_code: ExitCode


def apply_report_output_policy(
    report: Report,
    *,
    source: Path | None,
    additional_inputs: Sequence[Path] = (),
    output: Path | None,
    overwrite: bool,
    run: ReportRun,
    evidence: EvidenceBundle | None = None,
    protected: Sequence[tuple[Path, str]] = (),
) -> ReportEmission:
    """Protect the input, write retained evidence before the Report, and allocate the exit.

    Retained evidence is written before the Report so a directory never gains a `report.json`
    describing evidence it does not hold, and the same finalized Report reaches stdout, any
    `--report-out` file, and the evidence directory. `protected` names destinations another
    owned side effect will write after this one, so input protection covers them first.
    """

    validate_report(report)
    outcome = cast(str, report["outcome"])
    default_exit = ExitCode.COMPLETED if outcome == "completed" else ExitCode.REFUSED
    owned = _owned(output, evidence) + list(protected)
    inputs = [*additional_inputs]
    if source is not None:
        inputs.insert(0, source)
    protection = _input_protection(report, inputs, owned, run)
    if protection is not None:
        return protection
    if evidence is not None:
        refused = write_evidence(evidence, overwrite=overwrite)
        if refused is not None:
            return ReportEmission(finish_report(_refused(report, refused), run), refused.exit_code)

    finalized = finish_report(report, run)
    destinations = [(output, REPORT_STAGE, overwrite)]
    if evidence is not None:
        destinations.append((evidence.report, STAGE, overwrite or evidence.replaceable))
    for destination, stage, replacing in destinations:
        if destination is None:
            continue
        try:
            _write_report(finalized, destination, overwrite=replacing)
        except FileExistsError:
            refusal = _output_exists_report(finalized, destination, stage)
            return ReportEmission(finish_report(refusal, run), ExitCode.REFUSED)
        except OSError as error:
            refusal = internal_error_report(
                finalized, destination, error, operation="write-report", stage=stage
            )
            return ReportEmission(finish_report(refusal, run), ExitCode.INTERNAL_ERROR)
    return ReportEmission(finalized, default_exit)


def _owned(output: Path | None, evidence: EvidenceBundle | None) -> list[tuple[Path, str]]:
    """Name every file this command would write, with the stage that owns it."""

    owned = [] if output is None else [(output, REPORT_STAGE)]
    owned += [] if evidence is None else [(path, STAGE) for path in evidence.destinations]
    return owned


def _input_protection(
    report: Report,
    inputs: Sequence[Path],
    owned: list[tuple[Path, str]],
    run: ReportRun,
) -> ReportEmission | None:
    """Refuse before writing anything if any output would replace a workflow input.

    Every destination is checked, not just `--report-out`: an evidence directory holding a file
    named like an input is the case that would otherwise overwrite the very thing being read.
    """

    for workflow_input in inputs:
        for destination, stage in owned:
            try:
                targets_input = _output_targets_input(workflow_input, destination)
            except OSError as error:
                refusal = internal_error_report(
                    report, destination, error, operation="identify-report-output", stage=stage
                )
                return ReportEmission(finish_report(refusal, run), ExitCode.INTERNAL_ERROR)
            if targets_input:
                refusal = output_is_input_report(report, destination, stage)
                return ReportEmission(finish_report(refusal, run), ExitCode.REFUSED)
    return None


def input_collision(inputs: Sequence[Path], destinations: Sequence[Path]) -> Path | None:
    """Name the first destination that is one of the workflow inputs.

    A command that writes several outputs checks this before doing expensive work, so the
    refusal names the collision rather than whatever else that path happens to be. Paths this
    cannot resolve are left to the authoritative check above, which reports them as errors.
    """

    for workflow_input in inputs:
        for destination in destinations:
            try:
                if _output_targets_input(workflow_input, destination):
                    return destination
            except OSError:
                continue
    return None


def _refused(report: Report, refusal: EvidenceRefusal) -> Report:
    return replace_refusal(
        report,
        boundary=refusal.boundary,
        stage=STAGE,
        summary=refusal.summary,
        fact=refusal.fact,
    )


def _output_exists_report(report: Report, path: Path, stage: str) -> Report:
    display = display_path(path)
    return replace_refusal(
        report,
        boundary="output-exists",
        stage=stage,
        summary=f"report output already exists: {display}",
        fact={"path": display},
    )


def output_is_input_report(report: Report, path: Path, stage: str = REPORT_STAGE) -> Report:
    """Refuse before writing, because one destination is the very file being read."""

    display = display_path(path)
    return replace_refusal(
        report,
        boundary="output-is-input",
        stage=stage,
        summary=f"report output is the workflow input: {display}",
        fact={"path": display},
    )


def internal_error_report(
    report: Report,
    path: Path,
    error: OSError,
    *,
    operation: Literal[
        "identify-report-output", "write-report", "publish-artifact", "publish-evidence"
    ],
    stage: str = REPORT_STAGE,
) -> Report:
    error_type = type(error).__name__
    display = display_path(path)
    action = {
        "identify-report-output": "checking Report output",
        "write-report": "writing Report",
        "publish-artifact": "publishing the prepared EPUB",
        "publish-evidence": "publishing the evidence bundle",
    }[operation]
    return replace_refusal(
        report,
        boundary="internal-error",
        stage=stage,
        summary=f"internal error while {action}: {error_type}",
        fact={"operation": operation, "path": display, "error_type": error_type},
    )


def _write_report(report: Report, path: Path, *, overwrite: bool) -> None:
    mode = "w" if overwrite else "x"
    with path.open(mode, encoding="utf-8") as output:
        _ = output.write(f"{report_json(report)}\n")


def _output_targets_input(source: Path, output: Path) -> bool:
    if source.resolve() == output.resolve():
        return True
    try:
        return source.samefile(output)
    except FileNotFoundError:
        return False

"""Read the three Repair Inputs, hold each to its schema, and tie them to this preparation.

Everything here happens before a repaired document contributes a single fact. A repair Galley
cannot read, cannot validate, or cannot prove belongs to this source and this Device Profile is
refused whole: half-trusting one is how a document that was inspected somewhere else ends up
measured against a baseline that was never its own.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast, get_args

from jsonschema.exceptions import ValidationError

from galley.document.canonical import TitleSource, validate_canonical_document
from galley.json_reading import mapping, text
from galley.locations import display_path
from galley.report.envelope import ReportAssembly, validate_report
from galley.sources import MARKDOWN
from galley.tools.pandoc import api_version

REPAIR_STAGE = "repair-input"
UNREADABLE = "unreadable-repair-input"
INVALID = "invalid-repair-input"
MISMATCH = "repair-lineage-mismatch"
ENCODING = "utf-8"
# An inspection Report is what `inspect` writes, what a refused `prepare` retains beside the
# Canonical Document it declined to package — which is the evidence a repair usually starts from
# — and what `localise` writes beside the document whose images it retrieved. All three read a
# source. An audit Report describes a stranger's artifact and carries no source document at all.
INSPECTING_COMMANDS = frozenset({"inspect", "prepare", "localise"})
INPUT_NAMES = ("inspection Report", "Canonical Document", "Preservation Baseline")
# The closed vocabulary Galley itself writes. A Report is schema-valid without being one
# Galley wrote, so the value is checked rather than carried into a Report fact unread.
TITLE_SOURCES = frozenset(get_args(TitleSource))


class IncompleteRepair(ValueError):
    """Fewer than three Repair Inputs were named, which cannot describe a repair."""


@dataclass(frozen=True)
class RepairInputs:
    """The three files an agent-assisted preparation is handed, as named on the command line."""

    report: Path
    document: Path
    baseline: Path

    @property
    def paths(self) -> tuple[Path, Path, Path]:
        """Name all three, so each can be protected from this command's own outputs."""

        return (self.report, self.document, self.baseline)


def repair_inputs(
    inspection_report: Path | None,
    canonical_document: Path | None,
    preservation_baseline: Path | None,
) -> RepairInputs | None:
    """Accept the three Repair Inputs together or not at all, before any workflow exists.

    A partial set is an invalid option combination rather than a refusal: two of the three cannot
    describe a repair, and nothing has been read yet to report facts about.
    """

    named = (inspection_report, canonical_document, preservation_baseline)
    if all(path is None for path in named):
        return None
    if any(path is None for path in named):
        raise IncompleteRepair(
            "--inspection-report, --canonical-document and --preservation-baseline are "
            "supplied together or not at all"
        )
    return RepairInputs(*cast(tuple[Path, Path, Path], named))


def command_inputs(
    expected_missing_tokens: Path | None, repair: RepairInputs | None
) -> Sequence[Path]:
    """Name every file `prepare` reads besides the source, so none can become its own output."""

    declarations = () if expected_missing_tokens is None else (expected_missing_tokens,)
    return (*declarations, *(() if repair is None else repair.paths))


@dataclass(frozen=True)
class Refusal:
    """One refusal on its way out of a helper that otherwise returns a parsed JSON object."""

    report: ReportAssembly


def read_inputs(
    report: ReportAssembly, inputs: RepairInputs
) -> tuple[dict[str, object], dict[str, object], str] | ReportAssembly:
    """Read and schema-validate all three inputs before any of them is used for anything."""

    texts: list[str] = []
    for path, name in zip(inputs.paths, INPUT_NAMES, strict=True):
        try:
            texts.append(path.read_text(encoding=ENCODING))
        except FileNotFoundError:
            return _unreadable(report, path, name, "missing", "the file does not exist")
        except UnicodeDecodeError:
            return _unreadable(report, path, name, "not-utf8", "the file is not UTF-8")
        except OSError as error:
            return _unreadable(report, path, name, "unreadable", str(error))
    inspection = _document(report, inputs.report, INPUT_NAMES[0], texts[0], validate_report)
    if isinstance(inspection, Refusal):
        return inspection.report
    document = _document(
        report, inputs.document, INPUT_NAMES[1], texts[1], validate_canonical_document
    )
    if isinstance(document, Refusal):
        return document.report
    return inspection, document, texts[2]


def _document(
    report: ReportAssembly,
    path: Path,
    name: str,
    payload: str,
    validate: Callable[[dict[str, object]], None],
) -> dict[str, object] | Refusal:
    """Parse one input as JSON and hold it to its own schema before anything reads a field."""

    try:
        parsed = cast(object, json.loads(payload))
    except json.JSONDecodeError as error:
        return Refusal(_invalid(report, path, name, "malformed-json", str(error)))
    if not isinstance(parsed, dict):
        return Refusal(_invalid(report, path, name, "invalid-shape", "expected a JSON object"))
    document = cast(dict[str, object], parsed)
    try:
        validate(document)
    except ValidationError as error:
        return Refusal(_invalid(report, path, name, "schema-invalid", error.message))
    return document


def mismatch_reason(
    inspection: dict[str, object],
    document: dict[str, object],
    baseline: str,
    *,
    profile: dict[str, object],
    source: str,
    kind: str,
    observed: str | None,
) -> dict[str, object] | None:
    """Name the first way these inputs fail to describe this preparation, or nothing.

    The checks run in the order a reader would ask them: is this an inspection at all, is it this
    Device Profile's, is it this source's, are those still the source's bytes, is the baseline the
    one it retained, and is the AST the repair returns the vocabulary that inspection parsed.

    A local source is re-hashed rather than taken on trust. The chain is only worth recording if
    it still reaches the bytes that were inspected, and a Markdown source is also the directory
    every relative image reference will resolve against.
    """

    reported = mapping(inspection.get("profile"))
    canonical = mapping(inspection.get("canonical_document"))
    stated = mapping(inspection.get("source"))
    baseline_digest = text_digest(baseline)
    located = text(stated.get("path")) if kind == MARKDOWN else text(stated.get("url"))
    requested = display_path(Path(source)) if kind == MARKDOWN else source
    for reason, detail, holds in (
        (
            "not-an-inspection",
            "the Report was not produced by a command that reads a source",
            text(mapping(inspection.get("galley")).get("command")) in INSPECTING_COMMANDS,
        ),
        (
            "no-canonical-document",
            "the Report records no Canonical Document to repair",
            bool(canonical),
        ),
        (
            "profile-mismatch",
            f"the Report resolved {reported.get('id')!r}, not {profile['id']!r}",
            bool(reported.get("resolved")) and reported.get("id") == profile["id"],
        ),
        (
            "source-kind-mismatch",
            f"the Report describes a {stated.get('kind')} source, not {kind}",
            stated.get("kind") == kind,
        ),
        (
            "source-mismatch",
            f"the Report describes {located!r}, not {requested!r}",
            located == requested,
        ),
        (
            "source-unreadable",
            f"the source named by the Report can no longer be read: {requested}",
            kind != MARKDOWN or observed is not None,
        ),
        (
            "source-changed",
            "the source has changed since it was inspected",
            kind != MARKDOWN or observed == stated.get("sha256"),
        ),
        (
            "baseline-mismatch",
            "the baseline is not the one this inspection retained",
            baseline_digest == mapping(canonical.get("preservation_baseline")).get("sha256"),
        ),
        (
            "pandoc-api-version-mismatch",
            "the repaired document states a different Pandoc API version",
            api_version(cast(dict[str, object], document["pandoc"]))
            == canonical.get("pandoc_api_version"),
        ),
    ):
        if not holds:
            return {"detail": detail, "reason": reason}
    return None


def accepted_title_source(
    report: ReportAssembly, inputs: RepairInputs, inspection: dict[str, object]
) -> TitleSource | ReportAssembly:
    """Take the inspection's title source, or refuse a value Galley would never have written.

    Nothing downstream reads it, which is exactly why it needs checking here: an unread string
    copied out of a supplied file and into a canonical Report fact is how a closed vocabulary
    stops being closed.
    """

    stated = text(mapping(inspection.get("canonical_document")).get("title_source"))
    if stated not in TITLE_SOURCES:
        return _invalid(
            report,
            inputs.report,
            INPUT_NAMES[0],
            "unknown-title-source",
            f"title_source is not one Galley writes: {stated!r}",
        )
    return cast(TitleSource, stated)


def text_digest(payload: str) -> str:
    """Hash one UTF-8 text input the one way every Report names it."""

    return sha256(payload.encode(ENCODING)).hexdigest()


def source_digest(source: Path) -> str | None:
    """Hash the source as it stands now, or say nothing where it can no longer be read."""

    try:
        return file_digest(source)
    except OSError:
        return None


def file_digest(path: Path) -> str:
    """Hash one file's exact bytes."""

    return sha256(path.read_bytes()).hexdigest()


def _unreadable(
    report: ReportAssembly, path: Path, name: str, reason: str, detail: str
) -> ReportAssembly:
    return _refused(report, UNREADABLE, path, name, reason, detail, "cannot read")


def _invalid(
    report: ReportAssembly, path: Path, name: str, reason: str, detail: str
) -> ReportAssembly:
    return _refused(report, INVALID, path, name, reason, detail, "cannot use")


def _refused(
    report: ReportAssembly,
    boundary: str,
    path: Path,
    name: str,
    reason: str,
    detail: str,
    verb: str,
) -> ReportAssembly:
    return report.refuse(
        boundary=boundary,
        stage=REPAIR_STAGE,
        summary=f"{verb} the supplied {name}: {detail}",
        fact={"detail": detail, "input": name, "path": display_path(path), "reason": reason},
    )

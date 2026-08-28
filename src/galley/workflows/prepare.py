"""Choose how one preparation obtains its Canonical Document, and refuse before it pays for one.

Three routes lead in — a Markdown file, a live Article-Like Page, and a document an agent
repaired — and each of them only decides how the Canonical Document is obtained. Everything from
there is `packaged` in a fixed order: transform, package, measure,
audit, enforce, publish. Source kind and destinations are settled here first because both are
free, so a run that cannot publish never pays for a parse, a packaging run and an audit.

Where the book lands is a fourth thing, orthogonal to all three routes: an explicit output the
user named, or Ready publication into a resolved Galley Workspace. That choice arrives as a
`Destination`, so no route knows which mode it is running in.
"""

from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

from galley.document.preservation import read_expected_missing
from galley.images.resources import ResourceOrigin
from galley.locations import display_path
from galley.output.destinations import destination_refusal
from galley.output.publication import Destination
from galley.report.envelope import Report, ReportRun, completed_report, replace_refusal, with_facts
from galley.sources import ARTICLE_URL, MARKDOWN, SourceKind, local_path
from galley.workflows.article import read_article
from galley.workflows.inspect import ACQUISITION_STAGE, read_markdown, source_digest
from galley.workflows.packaged import packaged
from galley.workflows.refusals import Preparation
from galley.workflows.repair_inputs import RepairInputs, command_inputs
from galley.workflows.repaired import Repair, accepted_repair, repaired_inspection
from galley.workflows.routes import routed_source

REFUSED = "refused"


def prepare_source(
    profile: dict[str, object],
    source: str,
    *,
    destination: Destination,
    protected: Sequence[Path],
    evidence: Path | None,
    overwrite: bool,
    expected_missing_tokens: Path | None,
    expected_source_hash: str | None = None,
    repair: RepairInputs | None = None,
    run: ReportRun,
) -> Preparation:
    """Refuse the source kind and every destination before any expensive work begins.

    Classification comes first because it is free and decides whether there is a workflow at
    all; the destinations are checked next, so a run that cannot publish never pays for a parse,
    a packaging run and an audit before saying so. `protected` names the paths this mode already
    knows it will write — an explicit output names its EPUB, a Ready publication cannot yet.
    """

    routed = routed_source(profile, source, run=run, command="prepare")
    if not isinstance(routed, SourceKind):
        return Preparation(routed)
    report = completed_report("prepare", profile, run=run)
    refusal = destination_refusal(
        report,
        local_path(source),
        protected,
        evidence,
        overwrite=overwrite,
        additional_inputs=command_inputs(expected_missing_tokens, repair),
    )
    if refusal is not None:
        return Preparation(refusal)
    expected = read_expected_missing(expected_missing_tokens)
    if expected.tokens is None:
        return Preparation(
            replace_refusal(
                report,
                boundary="invalid-text-preservation-input",
                stage="text-preservation",
                summary=f"cannot read expected missing tokens: {expected.detail}",
                fact={
                    "detail": expected.detail,
                    "path": str(expected_missing_tokens),
                    "reason": expected.reason,
                },
            )
        )
    if expected_source_hash is not None and routed.id != MARKDOWN:
        return Preparation(_no_source_bytes(report, source, routed, expected_source_hash))
    if repair is not None:
        return prepare_repaired(
            profile,
            source,
            repair,
            kind=routed.id,
            destination=destination,
            expected_missing=expected.tokens,
            run=run,
        )
    if routed.id == ARTICLE_URL:
        return prepare_article(
            profile, source, destination=destination, expected_missing=expected.tokens, run=run
        )
    return prepare_markdown(
        profile,
        Path(source),
        destination=destination,
        expected_missing=expected.tokens,
        expected_source_hash=expected_source_hash,
        run=run,
    )


def prepare_repaired(
    profile: dict[str, object],
    source: str,
    repair: RepairInputs,
    *,
    kind: str,
    destination: Destination,
    expected_missing: dict[str, int],
    run: ReportRun,
) -> Preparation:
    """Take an agent-repaired Canonical Document down the pipeline its source would have gone.

    The repair replaces source handling and nothing else: no source is parsed and no page is
    fetched, because the document to package already exists. Everything downstream is the shared
    `_packaged`, so a repaired book is prepared, measured, preserved and audited by exactly the
    code an unrepaired one is.

    The image origin is the *source's*, not the repair's. Where a document's references resolve
    from is a fact about where the document came from, and the accepted repair has already been
    made to prove it came from this source — so this route has nothing of its own to decide.
    """

    report = completed_report("prepare", profile, run=run)
    accepted = accepted_repair(report, repair, profile=profile, source=source, kind=kind)
    if not isinstance(accepted, Repair):
        return Preparation(accepted)
    inspection = repaired_inspection(report, profile, accepted)
    return packaged(profile, inspection, destination, source_origin(kind, source), expected_missing)


def source_origin(kind: str, source: str) -> ResourceOrigin:
    """State where one source's image references resolve from, once for all three routes.

    A Markdown source resolves relative references against its own directory and retrieves
    nothing; an Article-Like Page has no directory and retrieves from the page it came from. A
    repaired document uses its source's rule, because where references resolve from is a fact
    about where the document came from rather than about who last edited it.
    """

    if kind == ARTICLE_URL:
        return ResourceOrigin(retrieves=True)
    return ResourceOrigin(Path(source).parent)


def prepare_article(
    profile: dict[str, object],
    url: str,
    *,
    destination: Destination,
    expected_missing: dict[str, int],
    run: ReportRun,
) -> Preparation:
    """Extract one Article-Like Page and take it down the pipeline Markdown goes down.

    Everything past the Canonical Document is shared, deliberately: the two routes differ in how
    the document was obtained and in nothing else, so link stripping, note conversion, image
    preparation, preservation and audit cannot behave differently for an article than for a file.
    """

    inspection = read_article(profile, url, run=run, command="prepare")
    if inspection.document is None or inspection.report["outcome"] == REFUSED:
        # Unlike Markdown, an article route can refuse *with* a Canonical Document: Extraction
        # Failure judges a document it successfully parsed. Packaging it anyway would build the
        # book the inference just declined, so the refusal is honoured here and its evidence kept.
        return Preparation(
            inspection.report,
            inspection.document,
            inspection.baseline,
            inspection.extraction,
            retains_evidence=inspection.document is not None,
        )
    return packaged(
        profile, inspection, destination, source_origin(ARTICLE_URL, url), expected_missing
    )


def prepare_markdown(
    profile: dict[str, object],
    source: Path,
    *,
    destination: Destination,
    expected_missing: dict[str, int],
    expected_source_hash: str | None = None,
    run: ReportRun,
) -> Preparation:
    """Read one Markdown source, package it, audit the candidate and stage it for publication.

    The source is hashed twice around the read Galley pays for. The first hash answers the
    agent's expectation — an Inbox Check saw these bytes, and a source that no longer matches
    must not be published under that check's evidence. The second answers a race the agent
    cannot see: bytes that changed while they were being read would otherwise produce a book
    attributed to a revision that never existed.
    """

    stated = _expected(profile, source, expected_source_hash, run=run)
    if stated is not None:
        return Preparation(stated)
    inspection = read_markdown(profile, source, run=run, command="prepare")
    if inspection.document is None:
        return Preparation(inspection.report, retains_evidence=True)
    acquired = source_digest(inspection.report)
    current = _digest(source)
    if current != acquired:
        return Preparation(
            _changed(inspection.report, source, acquired, current), retains_evidence=True
        )
    return packaged(
        profile, inspection, destination, source_origin(MARKDOWN, str(source)), expected_missing
    )


def _expected(
    profile: dict[str, object], source: Path, expected: str | None, *, run: ReportRun
) -> Report | None:
    """Refuse before reading when the source no longer holds the bytes the agent observed.

    A source that cannot be hashed at all is passed through rather than refused here. It has no
    current bytes to disagree with the expectation, and `read_markdown` is about to refuse it as
    `unreadable-source`, which is the true boundary: a file that cannot be opened has not
    changed, it is missing or shut.
    """

    if expected is None:
        return None
    observed = _digest(source)
    if observed is None or observed == expected:
        return None
    display = display_path(source)
    report = with_facts(
        completed_report("prepare", profile, run=run),
        "source",
        {"kind": MARKDOWN, "path": display, "sha256": observed},
    )
    return replace_refusal(
        report,
        boundary="source-hash-mismatch",
        stage=ACQUISITION_STAGE,
        summary=f"source no longer matches the observed hash: {display}",
        fact={"expected_sha256": expected, "observed_sha256": observed, "path": display},
    )


def _changed(report: Report, source: Path, acquired: str | None, current: str | None) -> Report:
    """Refuse a source whose bytes changed while Galley was reading them."""

    display = display_path(source)
    return replace_refusal(
        report,
        boundary="source-changed-during-read",
        stage=ACQUISITION_STAGE,
        summary=f"source bytes changed while they were being read: {display}",
        fact={
            "acquired_sha256": acquired,
            "current_sha256": current,
            "path": display,
        },
    )


def _no_source_bytes(report: Report, source: str, kind: SourceKind, expected: str | None) -> Report:
    """Refuse an expected source hash for a source that has no local bytes to compare."""

    return replace_refusal(
        report,
        boundary="expected-hash-unavailable",
        stage=ACQUISITION_STAGE,
        summary=f"an expected source hash needs local source bytes: {kind.statement}",
        fact={"expected_sha256": expected, "kind": kind.id, "source": source},
    )


def _digest(source: Path) -> str | None:
    try:
        return sha256(source.read_bytes()).hexdigest()
    except OSError:
        return None

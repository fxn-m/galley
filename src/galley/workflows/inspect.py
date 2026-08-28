"""Inspect a source into the Report, Canonical Document, and baseline a repair depends on."""

from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

from galley.document.canonical import document_author, document_title
from galley.locations import display_path
from galley.report.envelope import (
    Report,
    ReportCommand,
    ReportRun,
    completed_report,
    replace_refusal,
    with_dependency,
    with_facts,
)
from galley.report.quantities import quantity
from galley.sources import ARTICLE_URL, MARKDOWN, SourceKind
from galley.tools.pandoc import MARKDOWN_READER, parse_source
from galley.workflows.article import inspect_article
from galley.workflows.parsed import (
    ENCODING,
    PARSE_STAGE,
    Inspection,
    parsed_inspection,
    parser_facts,
    projected,
)
from galley.workflows.routes import routed_source

ACQUISITION_STAGE = "source-acquisition"

UnreadableReason = Literal["not-found", "not-a-regular-file", "not-utf8", "unreadable"]


def inspect_source(profile: dict[str, object], source: str, *, run: ReportRun) -> Inspection:
    """Inspect one named source by its route, refusing the routes this release has not built."""

    routed = routed_source(profile, source, run=run, command="inspect")
    if not isinstance(routed, SourceKind):
        return Inspection(routed)
    if routed.id == ARTICLE_URL:
        return inspect_article(profile, source, run=run)
    return inspect_markdown(profile, Path(source), run=run)


def inspect_markdown(profile: dict[str, object], source: Path, *, run: ReportRun) -> Inspection:
    """Read one Markdown source and project what its artifact would carry."""

    return projected(profile, read_markdown(profile, source, run=run, command="inspect"))


def read_markdown(
    profile: dict[str, object], source: Path, *, run: ReportRun, command: ReportCommand
) -> Inspection:
    """Parse one Markdown source and retain everything the parse established.

    Both commands that read Markdown reach the Canonical Document the same way, so the fixed
    preparation order's "source handling" and "Canonical Document and baseline retention" steps
    are this one function rather than a second reading of the same bytes.
    """

    display = display_path(source)
    facts: dict[str, object] = {"kind": MARKDOWN, "path": display}
    report = with_facts(completed_report(command, profile, run=run), "source", facts)
    try:
        raw = source.read_bytes()
    except OSError as error:
        return Inspection(_unreadable(report, display, _reason(error), str(error)))
    facts = {
        **facts,
        "byte_size": quantity(len(raw), "bytes"),
        "sha256": sha256(raw).hexdigest(),
    }
    report = with_facts(report, "source", facts)
    try:
        _ = raw.decode(ENCODING)
    except UnicodeDecodeError as error:
        return Inspection(_unreadable(report, display, "not-utf8", str(error)))
    return _parsed(report, facts, source, display, profile)


def _parsed(
    report: Report, facts: dict[str, object], source: Path, display: str, profile: dict[str, object]
) -> Inspection:
    parse = parse_source(source, reader=MARKDOWN_READER)
    if parse.version is not None:
        report = with_dependency(report, "pandoc", parse.version)
    if parse.ast is None:
        return Inspection(
            replace_refusal(
                report,
                boundary="dependency-unavailable",
                stage=PARSE_STAGE,
                summary=f"cannot parse source with Pandoc: {display}",
                fact=parse.facts,
            )
        )
    title, title_source = document_title(parse.ast, fallback=source.stem)
    parsed = {**facts, "encoding": ENCODING, "parser": parser_facts(parse)}
    report = with_facts(report, "source", parsed)
    return parsed_inspection(
        report,
        profile,
        parse,
        title=title,
        title_source=title_source,
        author=document_author(parse.ast),
        source_url=None,
    )


def source_digest(report: Report) -> str | None:
    """Read the digest of the source bytes a Report already recorded when it acquired them."""

    facts = report["source"]
    if not isinstance(facts, dict):
        return None
    stated = cast(dict[str, object], facts).get("sha256")
    return stated if isinstance(stated, str) else None


def _unreadable(report: Report, path: str, reason: UnreadableReason, detail: str) -> Report:
    return replace_refusal(
        report,
        boundary="unreadable-source",
        stage=ACQUISITION_STAGE,
        summary=f"cannot read source: {path}",
        fact={"detail": detail, "path": path, "reason": reason},
    )


def _reason(error: OSError) -> UnreadableReason:
    if isinstance(error, FileNotFoundError):
        return "not-found"
    if isinstance(error, IsADirectoryError):
        return "not-a-regular-file"
    return "unreadable"

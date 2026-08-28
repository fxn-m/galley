"""Read one live Article-Like Page through pinned Defuddle into the Canonical Document.

The locator is the source: Defuddle retrieves it and extracts the primary work, and Pandoc's
HTML reader parses the cleaned content Defuddle produced. Everything after that parse is the
Markdown path's own, because the Canonical Document is where the two routes converge.
"""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from galley.document.authorship import author_occurrence
from galley.document.canonical import EXTRACTION_TITLE
from galley.document.extraction import assess_extraction
from galley.document.preservation import count_words
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
from galley.sources import ARTICLE_URL
from galley.tools.defuddle import Extraction, extract_url
from galley.tools.pandoc import HTML_READER, Parse, parse_source
from galley.transforms.apparatus import Recovery, recover_apparatus
from galley.transforms.recovery import settled_recovery
from galley.workflows.parsed import (
    ENCODING,
    PARSE_STAGE,
    Inspection,
    parsed_inspection,
    parser_facts,
    projected,
)

EXTRACTION_STAGE = "article-extraction"
UNAVAILABLE = "dependency-unavailable"
TOOL_FAILURE = "extraction-tool-failure"
# The two ways the pinned extractor is not there at all, as opposed to there and failing.
ABSENT_REASONS = frozenset({"not-found", "not-executable"})
ASSESSMENT_STAGE = "extraction-assessment"
CONTENT = "content.html"
UNTITLED = "Untitled Article-Like Page"


def inspect_article(profile: dict[str, object], url: str, *, run: ReportRun) -> Inspection:
    """Extract one Article-Like Page and project what its artifact would carry."""

    return projected(profile, read_article(profile, url, run=run, command="inspect"))


def read_article(
    profile: dict[str, object], url: str, *, run: ReportRun, command: ReportCommand
) -> Inspection:
    """Retrieve, extract and parse one Article-Like Page, retaining what each stage established.

    Both commands that read an article reach the Canonical Document through this one function,
    so retrieval and extraction happen exactly once per run.
    """

    report = with_facts(
        completed_report(command, profile, run=run), "source", {"kind": ARTICLE_URL, "url": url}
    )
    with TemporaryDirectory() as workspace:
        extraction = extract_url(url, Path(workspace))
        report = _with_extractor_version(report, extraction)
        if extraction.document is None:
            return Inspection(_unextractable(report, extraction))
        recovery = recover_apparatus(extraction.content)
        recovery, parse = _settled(recovery, extraction.content, Path(workspace))
        report = with_facts(report, "extraction", _extraction_facts(extraction, recovery))
        return _parsed(report, profile, extraction, recovery, parse)


def _settled(recovery: Recovery, original: str, workspace: Path) -> tuple[Recovery, Parse]:
    """Parse the relabelled content, and read the document again unrelabelled if a note is empty.

    Recovery is refused entirely where any note would come out empty, and only the parse can say
    whether one did: markup that plainly carries text can still parse to nothing. The second parse
    is paid for only by a document that is about to have its recovery undone.
    """

    parse = _parse_content(recovery.content, workspace)
    if parse.ast is None:
        return recovery, parse
    undone = settled_recovery(recovery, original, parse.ast)
    if undone is None:
        return recovery, parse
    return undone, _parse_content(undone.content, workspace)


def _extraction_facts(
    extraction: Extraction,
    recovery: Recovery,
    words: int | None = None,
    baseline: str | None = None,
) -> dict[str, object]:
    """Describe extraction once, so a parse that fails and a parse that succeeds agree.

    The measured word count joins only once the parse has produced a document to count, which is
    why it is absent rather than zero on the failing path. The author occurrence needs the same
    baseline and is absent for the same reason.
    """

    facts: dict[str, object] = {**extraction.facts, "footnote_recovery": recovery.facts}
    if words is not None:
        facts["words"] = quantity(words, "words")
    occurrence = author_occurrence(extraction.author, baseline or "")
    if occurrence is not None:
        facts["author_occurrence"] = occurrence
    return facts


def _parsed(
    report: Report,
    profile: dict[str, object],
    extraction: Extraction,
    recovery: Recovery,
    parse: Parse,
) -> Inspection:
    """Wrap the parse of the recovered content HTML, which is the only HTML reader 0.1.0 has.

    Recovery has already run and already been settled against its own result, so the notes in
    this AST are the notes the book will carry — which is what the link interlock and Text
    Preservation both read.
    """

    if parse.version is not None:
        report = with_dependency(report, "pandoc", parse.version)
    if parse.ast is None:
        return Inspection(
            replace_refusal(
                report,
                boundary=UNAVAILABLE,
                stage=PARSE_STAGE,
                summary=f"cannot parse extracted content with Pandoc: {extraction.url}",
                fact=parse.facts,
            ),
            extraction=extraction.content,
        )
    source: dict[str, object] = {
        "kind": ARTICLE_URL,
        "url": extraction.url,
        "parser": parser_facts(parse),
    }
    inspection = parsed_inspection(
        with_facts(report, "source", source),
        profile,
        parse,
        title=extraction.title or UNTITLED,
        title_source=EXTRACTION_TITLE,
        author=extraction.author,
        source_url=extraction.url,
        language=extraction.language,
    )
    return _assessed(inspection, extraction, recovery)


def _assessed(inspection: Inspection, extraction: Extraction, recovery: Recovery) -> Inspection:
    """Recount the parsed document's reader-visible words, record them, and judge the extraction.

    The stated author is located in that same baseline and never judged against it. See
    `galley.document.authorship` for why: every rule that would discard the observed wrong author
    also discards correct ones.

    Defuddle's own count is retained beside Galley's. The two are measured over different things
    — its cleaned HTML against Galley's parsed Preservation Baseline — so recording one as the
    other would attribute a number to whoever did not produce it. Only the measured one is
    judged, because every verified refusal candidate returned a healthy status over a stub.

    A refused run keeps every fact it had already established: an agent asked to rescue the page
    needs the same evidence a completed run carries.
    """

    words = count_words(inspection.baseline or "")
    report = with_facts(
        inspection.report,
        "extraction",
        _extraction_facts(extraction, recovery, words, inspection.baseline),
    )
    failure = assess_extraction(words, cast(str, extraction.extractor["status"]))
    if failure.inferred:
        report = replace_refusal(
            report,
            boundary="extraction-failure",
            stage=ASSESSMENT_STAGE,
            summary=f"{failure.summary}: {extraction.url}",
            fact=failure.fact,
            basis=failure.basis,
        )
    # `replace`, not a positional rebuild: this function changes the Report and nothing else, and
    # naming four of the Inspection's fields silently dropped every one it did not name — which is
    # how the article route lost both its reader discards and its language.
    return replace(inspection, report=report, extraction=extraction.content)


def _parse_content(content: str, workspace: Path) -> Parse:
    """Hand Defuddle's cleaned HTML to Pandoc as a file, never as Markdown or through a pipe."""

    destination = workspace / CONTENT
    _ = destination.write_text(content, encoding=ENCODING)
    return parse_source(destination, reader=HTML_READER)


def _with_extractor_version(report: Report, extraction: Extraction) -> Report:
    if extraction.version is None:
        return report
    return with_dependency(report, "defuddle", extraction.version)


def _unextractable(report: Report, extraction: Extraction) -> Report:
    """Refuse a retrieval or process failure as the kind of tool failure it actually is.

    These two boundaries answer different questions. A dependency that is absent or not runnable
    is the machine's problem and the same for every page; a tool
    that ran and could not produce a usable extraction is this run's problem, and a page that
    timed out or answered 404 is neither a missing dependency nor evidence about the work.

    Nothing on either boundary is evidence about the page. A page that held no work exits Defuddle
    differently and reaches the parse as an empty extraction, so neither boundary absorbs it.
    """

    return replace_refusal(
        report,
        boundary=_boundary(extraction),
        stage=EXTRACTION_STAGE,
        summary=f"cannot extract Article-Like Page with Defuddle: {extraction.url}",
        fact=extraction.failure,
    )


def _boundary(extraction: Extraction) -> str:
    """Separate a dependency that never ran from an extraction that ran and failed."""

    return UNAVAILABLE if extraction.reason in ABSENT_REASONS else TOOL_FAILURE

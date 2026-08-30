"""Render concise human output only from validated canonical Reports."""

from typing import cast

from galley.reader_software import render_observed_software
from galley.report.artifact import artifact_lines
from galley.report.quantities import amount, group
from galley.report.transforms import transform_lines
from galley.report.envelope import Report, validate_report

VERDICT_ORDER = ("true", "false", "unknown", "unevaluable", "not_applicable")


def render_report(report: Report) -> str:
    """Render one validated Report as concise terminal output."""

    validate_report(report)
    galley = cast(dict[str, object], report["galley"])
    header = f"{galley['command']}: {report['outcome']}\n{_profile_line(report)}\n"
    if report["outcome"] == "refused":
        return header + _refusal_lines(report)
    return header + _completed_lines(report)


def _profile_line(report: Report) -> str:
    profile = cast(dict[str, object], report["profile"])
    if not profile["resolved"]:
        return f"Profile: {profile['requested']} (unresolved)"
    software = cast(dict[str, object], profile["observed_software"])
    identity = render_observed_software(software)
    return f"Profile: {profile['id']} {profile['profile_version']} ({identity})"


def _refusal_lines(report: Report) -> str:
    refusal = cast(dict[str, object], report["refusal"])
    lines = [
        f"Boundary: {refusal['boundary']}",
        f"Artifact written: {'yes' if refusal['artifact_written'] else 'no'}",
        *_measured_before_refusal(report),
        str(refusal["summary"]),
    ]
    return "\n".join(lines) + "\n"


def _measured_before_refusal(report: Report) -> list[str]:
    for category in ("source", "artifact"):
        facts = _facts(report, category)
        if "byte_size" in facts and "sha256" in facts:
            return [f"Bytes: {amount(facts, 'byte_size')}; sha256 {facts['sha256']}"]
    return []


def _facts(report: Report, category: str) -> dict[str, object]:
    """Read one fact category, which is null for every stage a command never reached."""

    facts = report[category]
    return cast(dict[str, object], facts) if isinstance(facts, dict) else {}


def _completed_lines(report: Report) -> str:
    return (
        f"{_source_lines(report)}"
        f"{_extraction_lines(report)}"
        f"{_canonical_lines(report)}"
        f"{_preparation_lines(report)}"
        f"{artifact_lines(_facts(report, 'artifact'))}"
        f"{_compatibility_lines(report)}"
        f"{_observation_line(report)}"
    )


def _source_lines(report: Report) -> str:
    """Name the source a command read, which is a path for a file and a locator for a page."""

    facts = _facts(report, "source")
    if "url" in facts:
        return f"Source: {facts['url']} ({facts['kind']})\n{_repair_line(facts)}"
    if "byte_size" not in facts:
        return ""
    return (
        f"Source: {facts['path']} ({facts['kind']}, {facts['encoding']})\n"
        f"Bytes: {amount(facts, 'byte_size')}; sha256 {facts['sha256']}\n"
        f"{_repair_line(facts)}"
    )


def _repair_line(facts: dict[str, object]) -> str:
    """Name the repaired form and the one it replaced, so the chain is visible without JSON."""

    repair = group(facts, "repair")
    if not repair:
        return ""
    state = "changed" if repair["changed"] else "unchanged"
    original = group(repair, "original_canonical_document")
    return (
        f"Repaired Canonical Document: {state}; "
        f"original sha256 {original['sha256']}\n"
        f"Inherited from: {group(repair, 'inspection_report')['path']}\n"
    )


def _extraction_lines(report: Report) -> str:
    """State who extracted the work and how much of it Galley then measured for itself."""

    facts = _facts(report, "extraction")
    if not facts:
        return ""
    extractor = group(facts, "extractor")
    reported_words = amount(facts, "word_count")
    return (
        f"Extraction: {extractor['tool']} {extractor['version']} ({extractor['status']})\n"
        f"Words: {amount(facts, 'words')} measured; {reported_words} reported\n"
    )


def _canonical_lines(report: Report) -> str:
    facts = _facts(report, "canonical_document")
    if not facts:
        return ""
    author = facts["author"]
    attribution = "" if author is None else f" by {author}"
    baseline = cast(dict[str, object], facts["preservation_baseline"])
    constructors = cast(dict[str, object], facts["constructors"])
    return (
        f'Canonical Document: "{facts["title"]}"{attribution}\n'
        f"Pandoc AST {facts['pandoc_api_version']}; blocks: {amount(facts, 'blocks')}; "
        f"constructor kinds: {len(constructors)}\n"
        f"{_unsupported_line(facts)}"
        f"Preservation Baseline: segments {amount(baseline, 'segments')}; "
        f"bytes {amount(baseline, 'byte_size')}; sha256 {baseline['sha256']}\n"
    )


def _unsupported_line(facts: dict[str, object]) -> str:
    """Name Unsupported Content even when there is none, so silence is never ambiguous."""

    records = cast(list[dict[str, object]], facts["unsupported"])
    if not records:
        return f"Unsupported Content: none ({facts['modelled_set']})\n"
    tally = ", ".join(f"{record['constructor']} {amount(record, 'count')}" for record in records)
    return f"Unsupported Content: carried through; {tally}\n"


def _preparation_lines(report: Report) -> str:
    """Name every transform preparation ran and whether it fired, never only the ones that did."""

    facts = _facts(report, "preparation")
    if not facts:
        return ""
    transforms = cast(list[dict[str, object]], facts["transforms"])
    fired = sum(1 for entry in transforms if entry["fired"] is True)
    canonical = group(facts, "canonical_document")
    state = "transformed" if canonical["transformed"] else "unchanged"
    named = "".join(transform_lines(entry) for entry in transforms)
    return (
        f"Preparation: {len(transforms)} transforms, {fired} fired; "
        f"Canonical Document {state}\n"
        f"{named}"
        f"{_cover_line(group(facts, 'images'))}"
        f"{_figure_line(group(group(facts, 'images'), 'reduction'))}"
        f"{_packaging_line(group(facts, 'packaging'))}"
    )


def _cover_line(images: dict[str, object]) -> str:
    """Name whether the packaged cover is a Default Cover or a source cover-image."""

    cover = group(images, "cover")
    origin = cover.get("origin")
    if origin == "default-cover":
        author = cover.get("author")
        attribution = "" if author is None else f" by {author}"
        return f'Cover: Default Cover, "{cover["title"]}"{attribution}\n'
    if origin == "source-cover-image":
        return "Cover: source cover-image\n"
    return ""


def _figure_line(reduction: dict[str, object]) -> str:
    """Name how far the book's figures were reduced, so a person can check what an agent said.

    Absent where the document carries no figure, which the images transform line directly above
    has already stated as zero references. Nothing here is a judgement: no reduction number can
    predict whether a figure remains legible.
    """

    scale = group(reduction, "scale")
    if not scale:
        return ""
    spread = "/".join(str(amount(scale, key)) for key in ("minimum", "median", "maximum"))
    return (
        f"Figures: {amount(reduction, 'images')} carried, "
        f"{amount(reduction, 'reduced')} reduced to fit; scale {spread} percent\n"
    )


def _packaging_line(packaging: dict[str, object]) -> str:
    if not packaging:
        return ""
    version = packaging["version"] or "version unknown"
    status = amount(packaging, "exit_status")
    outcome = "did not run" if status is None else f"exit {status}"
    return f"Packaging: {packaging['tool']} {version} to {packaging['writer']} ({outcome})\n"


def _compatibility_lines(report: Report) -> str:
    results = cast(list[dict[str, object]], report["compatibility"])
    if not results:
        return ""
    tally = ", ".join(
        f"{verdict} {sum(1 for result in results if result['verdict'] == verdict)}"
        for verdict in VERDICT_ORDER
    )
    failed = [
        f"{result['requirement_id']} ({result['failure_mode']})"
        for result in results
        if result["verdict"] == "false"
    ]
    lines = f"Compatibility: {tally}\n"
    if failed:
        lines += f"Requirements not met: {'; '.join(failed)}\n"
    return lines + _projection_line(results)


def _projection_line(results: list[dict[str, object]]) -> str:
    """Name every requirement answered from a projection, so none reads as a measurement."""

    projections = [
        f"{result['requirement_id']} {measured['value']} {measured['unit']} "
        f"({measured['relation']})"
        for result in results
        if (measured := group(result, "measurement")).get("basis") == "projected"
    ]
    if not projections:
        return ""
    return f"Projected, not measured: {'; '.join(projections)}\n"


def _observation_line(report: Report) -> str:
    observations = cast(list[dict[str, object]], report["observations"])
    if not observations:
        return ""
    applicable = sum(1 for entry in observations if entry["applicability"] is True)
    fired = sum(1 for entry in observations if entry["fired"] is True)
    outstanding = sum(1 for entry in observations if entry["fired"] is None)
    return (
        f"Observations: {len(observations)} recorded; {applicable} applicable; {fired} fired; "
        f"{outstanding} awaiting agent or human judgement\n"
    )

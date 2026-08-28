"""Render the measured EPUB half of a validated Report as concise terminal output.

`audit` and `prepare` reach the same artifact facts through the same workflow, so both render
them here rather than each describing a book its own way.
"""

from typing import cast

from galley.json_reading import integer
from galley.report.quantities import amount, group, nested_amount


# EPUBCheck message severities, most severe first: the rendering order for conformance
# tallies. Stated here because rendering is the one place the order matters.
SEVERITIES = ("fatal", "error", "warning", "usage")


def artifact_lines(facts: dict[str, object]) -> str:
    """Describe one measured EPUB, or nothing where the command never packaged or opened one."""

    if not facts:
        return ""
    return (
        f"Artifact: {facts['path']}\n"
        f"Bytes: {amount(facts, 'byte_size')}; sha256 {facts['sha256']}\n"
        f"Package: {_package_line(facts)}\n"
        f"Manifest items: {nested_amount(facts, 'manifest', 'item_count')}; "
        f"spine items: {nested_amount(facts, 'spine', 'item_count')}; "
        f"navigation: {_navigation_line(facts)}\n"
        f"Content documents: {_length(facts, 'content_documents')}; "
        f"resources: {_length(facts, 'resources')}\n"
        f"References: {nested_amount(facts, 'references', 'document_count')}; "
        f"broken: {nested_amount(facts, 'references', 'broken_count')}\n"
        f"Problems: {_problem_line(facts)}\n"
        f"{_link_line(facts)}"
        f"{_image_line(facts)}"
        f"{_text_preservation_line(facts)}"
        f"{_conformance_lines(facts)}"
    )


def _link_line(facts: dict[str, object]) -> str:
    measured = group(facts, "links")
    if not measured:
        return ""
    scope = "complete" if measured["complete"] else "incomplete"
    return (
        f"Links: {amount(measured, 'total')} total; "
        f"{amount(measured, 'recorded')} recorded; "
        f"max {amount(measured, 'maximum_recorded_per_block')} per block; "
        f"longest href {amount(measured, 'maximum_recorded_href_bytes')} bytes ({scope})\n"
    )


def _image_line(facts: dict[str, object]) -> str:
    measured = group(facts, "images")
    if not measured:
        return ""
    resources = cast(list[dict[str, object]], measured["resources"])
    unresolved = len(cast(list[object], measured["unresolved_references"]))
    return (
        f"Images: {len(resources)} measured; "
        f"{amount(measured, 'not_device_verified')} not device-verified; "
        f"{unresolved} unresolved references\n"
    )


def _text_preservation_line(facts: dict[str, object]) -> str:
    """Say whether a claim was made before saying what was measured.

    The concise renderer dropping the qualification while the JSON carries it would be the same
    defect one surface over: a reader of the terminal would take the measurement for the claim.
    """

    preservation = group(facts, "text_preservation")
    if not preservation:
        return ""
    claim = (
        "claimed" if preservation["claimed"] is True else f"not claimed ({preservation['detail']})"
    )
    if "tokens" not in preservation:
        return f"Text Preservation: {claim}\n"
    tokens = group(preservation, "tokens")
    return (
        f"Text Preservation: {claim}; {amount(tokens, 'baseline')} baseline tokens; "
        f"{amount(tokens, 'artifact')} artifact tokens; "
        f"expected missing {_missing_total(tokens, 'expected_missing')}; "
        f"unexpected missing {_missing_total(tokens, 'unexpected_missing')}\n"
    )


def _missing_total(tokens: dict[str, object], key: str) -> int:
    entries = cast(list[dict[str, object]], tokens[key])
    return sum(integer(amount(entry, "count")) or 0 for entry in entries)


def _conformance_lines(facts: dict[str, object]) -> str:
    result = group(facts, "conformance")
    if not result:
        return ""
    if not result["checked"]:
        summary = f"unavailable ({result['tool']} {result['reason']})"
    else:
        counts = cast(dict[str, object], result["counts"])
        tallies = ", ".join(f"{amount(counts, name)} {name}" for name in SEVERITIES)
        summary = f"EPUBCheck {result['version']}; {tallies}"
    return f"Conformance: {summary}\n{_non_requirement_lines(result)}"


def _non_requirement_lines(conformance: dict[str, object]) -> str:
    entries = cast(list[dict[str, object]], conformance.get("non_requirements") or [])
    return "".join(f"Non-requirement: {entry['statement']} ({entry['id']})\n" for entry in entries)


def _package_line(facts: dict[str, object]) -> str:
    package = cast(dict[str, object], facts["package"])
    if not package["present"]:
        return "unavailable"
    version = package["version"]
    edition = "version unknown" if version is None else f"EPUB {version}"
    return f"{package['path']} ({edition})"


def _navigation_line(facts: dict[str, object]) -> str:
    navigation = cast(dict[str, object], facts["navigation"])
    if not navigation["present"]:
        return "none"
    return f"{navigation['path']} ({navigation['kind']})"


def _problem_line(facts: dict[str, object]) -> str:
    problems = cast(list[dict[str, object]], facts["problems"])
    if not problems:
        return "0"
    kinds = sorted({str(problem["kind"]) for problem in problems})
    return f"{len(problems)} ({', '.join(kinds)})"


def _length(facts: dict[str, object], key: str) -> int:
    return len(cast(list[object], facts[key]))

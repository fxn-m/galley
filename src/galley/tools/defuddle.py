"""Run pinned Defuddle and retain the extraction it reports.

Defuddle owns URL retrieval and primary-content extraction; Galley owns process supervision,
output validation and version recording. The command is asked for JSON written to an explicit
file rather than stdout, because an article's cleaned HTML is far larger than a pipe a caller
might truncate, and because a file either holds a complete document or does not exist.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from galley.json_reading import integer, mapping, sequence, text
from galley.report.quantities import reported
from galley.tools.dependencies import diagnostic, run_dependency, selected_command, version_probe

COMMAND_VARIABLE = "GALLEY_DEFUDDLE"
DEFAULT_COMMAND = "defuddle"
PINNED_VERSION = "0.19.1"
PARSE = "parse"
OK = "ok"
# Defuddle's own wording when a page held no extractable work. Verified refusal candidates
# returned a stub rather than this exit, so the condition is documented and
# rare — but it is a statement about the page, not about the tool, and is kept apart from every
# other nonzero exit for exactly that reason.
NO_CONTENT_MESSAGE = "No content could be extracted from"

UnavailableReason = Literal[
    "not-found", "not-executable", "timeout", "failed", "no-output", "malformed-output"
]


@dataclass(frozen=True)
class Extraction:
    """One Defuddle invocation: what it extracted, its version, and what it said."""

    document: dict[str, object] | None
    version: str | None
    command: str
    url: str
    no_content: bool = False
    reason: UnavailableReason | None = None
    detail: str = ""

    @property
    def content(self) -> str:
        """Return the cleaned content HTML Pandoc reads, which is empty on a no-content exit."""

        return text(mapping(self.document).get("content")) or ""

    @property
    def language(self) -> str | None:
        """Return the language Defuddle read from the page, which a stub page may not carry."""

        return text(mapping(self.document).get("language")) or None

    @property
    def title(self) -> str | None:
        """Return the title Defuddle read from the page, which a stub page may not carry."""

        return text(mapping(self.document).get("title")) or None

    @property
    def author(self) -> str | None:
        """Return the author Defuddle read from the page, which most pages do not state."""

        return text(mapping(self.document).get("author")) or None

    @property
    def matches_pinned_version(self) -> bool:
        """Say whether the Defuddle that ran is the one Galley's reading of its output was cut to."""

        return self.version == PINNED_VERSION

    @property
    def extractor(self) -> dict[str, object]:
        """Name the exact tool, version and status that produced this extraction."""

        return {
            "matches_pinned_version": self.matches_pinned_version,
            "pinned_version": PINNED_VERSION,
            "status": OK if self.document is not None else self.reason,
            "tool": DEFAULT_COMMAND,
            "version": self.version,
        }

    @property
    def facts(self) -> dict[str, object]:
        """Describe what Defuddle reported, every value carrying the basis Galley had for it.

        Nothing here is remeasured, so every quantity is `reported`. The word count Galley takes
        responsibility for is recomputed after Pandoc parsing and recorded separately.
        """

        document = mapping(self.document)
        return {
            "author": text(document.get("author")) or None,
            "described_as": text(document.get("description")) or None,
            "domain": text(document.get("domain")) or None,
            "extractor": self.extractor,
            "extractor_type": text(document.get("extractorType")) or None,
            "no_content": self.no_content,
            "parse_time": reported(integer(document.get("parseTime")) or 0, "milliseconds"),
            "published": text(document.get("published")) or None,
            "site": text(document.get("site")) or None,
            "source_url": self.url,
            "title": text(document.get("title")) or None,
            "content_bytes": reported(len(self.content.encode("utf-8")), "bytes"),
            "meta_tags": reported(len(sequence(document.get("metaTags"))), "tags"),
            "word_count": reported(integer(document.get("wordCount")) or 0, "words"),
        }

    @property
    def failure(self) -> dict[str, object]:
        """Describe an invocation that produced no usable extraction."""

        return {
            "detail": self.detail,
            "pinned_version": PINNED_VERSION,
            "reason": self.reason,
            "tool": self.command,
            "url": self.url,
        }


def extract_url(url: str, workspace: Path) -> Extraction:
    """Extract one Article-Like Page URL with pinned Defuddle through its JSON file surface."""

    command = selected_command(COMMAND_VARIABLE, DEFAULT_COMMAND)
    version = installed_version(command)
    destination = workspace / "defuddle.json"
    arguments = [PARSE, url, "--json", "--output", str(destination)]
    execution = run_dependency(command, arguments)
    completed = execution.completed
    if completed is None:
        return _unusable(command, version, url, execution.reason, execution.detail)
    if completed.returncode != 0:
        return _exited(command, version, url, completed.stderr, completed.returncode)
    document = _read_document(destination)
    if document is None:
        reason, detail = _unusable_output(destination.is_file())
        return _unusable(command, version, url, reason, detail)
    return Extraction(document, version, command, url)


@version_probe
def installed_version(command: str) -> str | None:
    """Name the Defuddle that is actually on PATH, or nothing where none answered."""

    completed = run_dependency(command, ["--version"]).completed
    if completed is None or completed.returncode != 0:
        return None
    first = completed.stdout.split()
    return first[0] if first else None


def _exited(
    command: str, version: str | None, url: str, captured: str, returncode: int
) -> Extraction:
    """Separate Defuddle's documented no-content exit from every other way it can exit nonzero.

    A page holding no extractable work is a fact about the page and is carried forward as an
    empty extraction, so the same inference judges it as judges a stub. Anything else is the
    tool failing, and a tool failure is never evidence about the page.
    """

    detail = diagnostic(captured) or f"Defuddle exited {returncode}"
    if NO_CONTENT_MESSAGE in captured:
        return Extraction({}, version, command, url, no_content=True, detail=detail)
    return Extraction(None, version, command, url, reason="failed", detail=detail)


def _unusable(
    command: str, version: str | None, url: str, reason: UnavailableReason | None, detail: str
) -> Extraction:
    return Extraction(None, version, command, url, reason=reason, detail=detail)


def _unusable_output(written: bool) -> tuple[UnavailableReason, str]:
    if not written:
        return "no-output", "Defuddle wrote no JSON document"
    return "malformed-output", "Defuddle wrote no JSON document carrying extracted content"


def _read_document(destination: Path) -> dict[str, object] | None:
    """Accept Defuddle's document only when it carries the content Galley came for."""

    try:
        raw: object = json.loads(destination.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    document = cast(dict[str, object], raw)
    return document if isinstance(document.get("content"), str) else None

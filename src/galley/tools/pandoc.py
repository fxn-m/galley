"""Run pinned Pandoc and retain the native JSON AST it produces."""

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast

from galley.tools.dependencies import Execution, diagnostic, run_dependency, selected_command
from galley.json_reading import sequence
from galley.release_data import pinned_pandoc_version

COMMAND_VARIABLE = "GALLEY_PANDOC"
DEFAULT_COMMAND = "pandoc"
MARKDOWN_READER = "markdown"
HTML_READER = "html"
API_VERSION_KEY = "pandoc-api-version"

UnavailableReason = Literal[
    "not-found", "not-executable", "timeout", "failed", "no-output", "malformed-output"
]


@dataclass(frozen=True)
class Parse:
    """One Pandoc invocation: the AST it produced, its version, and what it said."""

    ast: dict[str, object] | None
    version: str | None
    command: str
    reader: str
    messages: tuple[str, ...]
    reason: UnavailableReason | None = None
    detail: str = ""

    @property
    def matches_pinned_version(self) -> bool:
        """Say whether the Pandoc that ran is the one Galley's AST data was validated against."""

        return self.version == pinned_pandoc_version()

    @property
    def facts(self) -> dict[str, object]:
        """Describe an invocation that produced no usable AST."""

        return {
            "detail": self.detail,
            "pinned_version": pinned_pandoc_version(),
            "reason": self.reason,
            "tool": self.command,
        }


def parse_source(source: Path, *, reader: str = MARKDOWN_READER) -> Parse:
    """Parse one source file with pinned Pandoc through its native JSON writer."""

    command = selected_command(COMMAND_VARIABLE, DEFAULT_COMMAND)
    version = installed_version(command)
    with TemporaryDirectory() as workspace:
        destination = Path(workspace) / "document.json"
        arguments = ["--from", reader, "--to", "json", "--output", str(destination), str(source)]
        execution = run_dependency(command, arguments)
        completed = execution.completed
        if completed is None:
            return _unusable(execution, version, reader, (), execution.reason)
        messages = _messages(completed.stderr)
        written = destination.is_file()
        ast = _read_ast(destination) if written else None
    if completed.returncode != 0:
        detail = diagnostic(completed.stderr) or f"Pandoc exited {completed.returncode}"
        return Parse(None, version, command, reader, messages, reason="failed", detail=detail)
    if ast is None:
        reason, detail = _unusable_output(written)
        return Parse(None, version, command, reader, messages, reason=reason, detail=detail)
    return Parse(ast, version, command, reader, messages)


def api_version(ast: dict[str, object]) -> str:
    """Render the AST's own API version as the dotted string Reports carry."""

    return ".".join(str(part) for part in sequence(ast.get(API_VERSION_KEY)))


def _unusable(
    execution: Execution,
    version: str | None,
    reader: str,
    messages: tuple[str, ...],
    reason: UnavailableReason | None,
) -> Parse:
    return Parse(
        None, version, execution.command, reader, messages, reason=reason, detail=execution.detail
    )


def _unusable_output(written: bool) -> tuple[UnavailableReason, str]:
    if not written:
        return "no-output", "Pandoc wrote no JSON document"
    return "malformed-output", "Pandoc wrote no native JSON AST"


def _read_ast(destination: Path) -> dict[str, object] | None:
    """Accept Pandoc's document only when it carries the three native AST keys."""

    try:
        raw = cast(object, json.loads(destination.read_text(encoding="utf-8")))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    document = cast(dict[str, object], raw)
    if not isinstance(document.get(API_VERSION_KEY), list):
        return None
    if not isinstance(document.get("blocks"), list) or not isinstance(document.get("meta"), dict):
        return None
    return document


def installed_version(command: str) -> str | None:
    """Name the Pandoc that is actually on PATH, or nothing where none answered."""

    completed = run_dependency(command, ["--version"]).completed
    if completed is None or completed.returncode != 0:
        return None
    first = completed.stdout.splitlines()[0].split() if completed.stdout else []
    return first[1] if len(first) >= 2 and first[0] == DEFAULT_COMMAND else None


def _messages(captured: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in captured.splitlines() if line.strip())

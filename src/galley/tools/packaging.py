"""Package one Canonical Document as an EPUB3 through Pandoc's own JSON reader and writer.

Galley keeps Pandoc's native surface rather than reconstructing its documents, so the bytes handed
to the writer are the retained AST serialized once. Nothing here decides device policy:
the navigation depth and the document's own title arrive as arguments the Device Profile and the
Canonical Document already settled.
"""

import json
from dataclasses import dataclass
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from galley.tools.dependencies import diagnostic, run_dependency, selected_command
from galley.tools.pandoc import (
    COMMAND_VARIABLE,
    DEFAULT_COMMAND,
    UnavailableReason,
    installed_version,
)
from galley.release_data import pinned_pandoc_version
from galley.report.quantities import quantity

JSON_READER = "json"
EPUB3_WRITER = "epub3"
AST_NAME = "document.json"
TEMPLATE_NAME = "epub3.template"
ARTIFACT_NAME = "candidate.epub"
PACKAGING_STAGE = "artifact-packaging"
IDENTIFIER_SCHEME = "urn:sha256:"
SOURCE_DATE_EPOCH = "0"
DETERMINISTIC_ENVIRONMENT = {"SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH}


@dataclass(frozen=True)
class Packaging:
    """One packaging attempt: the EPUB it produced, its digest of the AST, and what it said."""

    facts: dict[str, object]
    ast_sha256: str
    artifact: Path | None = None
    reason: UnavailableReason | None = None
    detail: str = ""


def ast_bytes(ast: dict[str, object]) -> bytes:
    """Serialize one native AST as the exact bytes a packaging run hands to Pandoc."""

    return f"{json.dumps(ast, indent=2, sort_keys=True)}\n".encode()


def ast_digest(ast: dict[str, object]) -> str:
    """Hash one native AST as the bytes packaging would hand to Pandoc."""

    return sha256(ast_bytes(ast)).hexdigest()


def artifact_identifier(canonical_sha256: str) -> str:
    """Name one book by the Canonical Document it was built from.

    Identity follows the document. The digest is already in the Report and the exact bytes it
    hashes are already in the evidence bundle, so anyone holding the bundle can
    recompute it. Two sources that parse to the same Canonical Document therefore share an
    identifier, which is correct — they are the same book to everything downstream — and it
    means the identifier is not a source identity. The source pair lives in the Ready evidence.
    """

    return f"{IDENTIFIER_SCHEME}{canonical_sha256}"


@dataclass(frozen=True)
class BookMetadata:
    """What preparation tells the writer this book *is*, as against how to lay it out.

    Four values that never travel apart, and every one of them is stated rather than left to
    Pandoc: it emits no `dc:title` for a document carrying none, stamps a fresh identifier and
    the current time on every run, and fills `dc:language` from the packaging machine's locale.
    """

    title: str
    author: str | None
    identifier: str
    language: str
    translations: str
    """Which language's strings Pandoc should look up, empty where Galley names no language.

    Not the same field as `language`, and they differ in exactly one case. `dc:language` says what
    the book is in and `und` is a true answer there; `lang` picks translation strings, and asking
    for `und`'s makes the writer report that it could not find them and that a term it never used
    has no translation. Empty asks for nothing and says nothing.
    """


def package_epub3(
    ast: dict[str, object],
    *,
    workspace: Path,
    metadata: BookMetadata,
    resources: Path,
    toc_depth: int | None,
    cover: Path | None = None,
    cover_template: Callable[[str, Path], Path | None] | None = None,
) -> Packaging:
    """Write one EPUB3 candidate into temporary space from the retained native AST.

    Image targets are the bare names preparation packaged them under, and `resources` is where
    those files are: putting their absolute paths in the AST made the digest of what this hands
    the writer different on every run, while the artifact stayed identical.

    Two levers make the bytes reproducible, and both are needed: without them Pandoc stamps a
    fresh `dc:identifier` UUID and the current time on every run, so two runs over identical
    source bytes produce different artifact hashes. `SOURCE_DATE_EPOCH` settles the times and
    the supplied identifier settles the identity. Under that epoch Pandoc writes a
    `1970-01-01T00:00:00Z` `dc:date`: the reproducible-builds marker for "no date is claimed",
    kept deliberately, because the alternative is rewriting the OPF of a finished artifact and
    this pipeline never mutates one.
    """

    document = workspace / AST_NAME
    payload = ast_bytes(ast)
    _ = document.write_bytes(payload)
    digest = sha256(payload).hexdigest()
    artifact = workspace / ARTIFACT_NAME
    command = selected_command(COMMAND_VARIABLE, DEFAULT_COMMAND)
    version = installed_version(command)
    template = (
        None if cover is None or cover_template is None else cover_template(command, workspace)
    )
    execution = run_dependency(
        command,
        _arguments(
            document,
            artifact,
            resources=resources,
            metadata=metadata,
            toc_depth=toc_depth,
            cover=cover,
            template=template,
        ),
        environment=DETERMINISTIC_ENVIRONMENT,
    )
    completed = execution.completed
    if completed is None:
        facts = _facts(command, version, None, ())
        return Packaging(facts, digest, reason=execution.reason, detail=execution.detail)
    messages = tuple(line.strip() for line in completed.stderr.splitlines() if line.strip())
    facts = _facts(command, version, completed.returncode, messages)
    if completed.returncode != 0:
        detail = diagnostic(completed.stderr) or f"Pandoc exited {completed.returncode}"
        return Packaging(facts, digest, reason="failed", detail=detail)
    if not artifact.is_file():
        return Packaging(facts, digest, reason="no-output", detail="Pandoc wrote no EPUB")
    return Packaging(facts, digest, artifact=artifact)


def _arguments(
    document: Path,
    artifact: Path,
    *,
    resources: Path,
    metadata: BookMetadata,
    toc_depth: int | None,
    cover: Path | None,
    template: Path | None,
) -> list[str]:
    """Name only what preparation actually decided, leaving Pandoc's own default where it did not.

    The language is always named. Pandoc's own default for it is the packaging machine's locale,
    which is not a default this project can leave standing: it made one source build two different
    books, and built an invalid one wherever no locale was configured.
    """

    decided = [
        "--metadata",
        f"title={metadata.title}",
        "--metadata",
        f"identifier={metadata.identifier}",
        # Both keys, and they do different jobs: Pandoc's EPUB3 writer fills `dc:language` from
        # `language`, while `lang` selects its translation strings. Both are stated because
        # stating only the first left a source's own `lang` in play — a document saying
        # `lang: "not a tag!"` had the writer report loading translations for `not`, which
        # contradicted the configured language.
        "--metadata",
        f"language={metadata.language}",
        "--metadata",
        f"lang={metadata.translations}",
    ]
    if metadata.author is not None:
        decided += ["--metadata", f"author={metadata.author}"]
    if toc_depth is not None:
        decided += ["--toc-depth", str(toc_depth)]
    if cover is not None:
        decided += ["--epub-cover-image", str(cover)]
    if template is not None:
        decided += ["--template", str(template)]
    return [
        # Every image target is a bare packaged name, so the writer is told where to find them.
        # The alternative — absolute paths in the AST — is what made the packaged digest unstable.
        "--resource-path",
        str(resources),
        "--from",
        JSON_READER,
        "--to",
        EPUB3_WRITER,
        *decided,
        "--output",
        str(artifact),
        str(document),
    ]


def _facts(
    command: str, version: str | None, exit_status: int | None, messages: tuple[str, ...]
) -> dict[str, object]:
    """Name the exact tool, reader, writer and version that packaged this candidate."""

    facts: dict[str, object] = {
        "matches_pinned_version": version == pinned_pandoc_version(),
        "messages": list(messages),
        "pinned_version": pinned_pandoc_version(),
        "reader": JSON_READER,
        "tool": command,
        "version": version,
        "writer": EPUB3_WRITER,
    }
    if exit_status is not None:
        facts["exit_status"] = quantity(exit_status, "status")
    return facts

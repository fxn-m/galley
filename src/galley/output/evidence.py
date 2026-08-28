"""Persist the evidence an inspection retains beside its Report."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from shutil import rmtree
from typing import Literal

from galley.document.canonical import canonical_bytes
from galley.locations import display_path
from galley.outcomes import ExitCode

REPORT_NAME = "report.json"
CANONICAL_NAME = "canonical-document.json"
BASELINE_NAME = "preservation-baseline.txt"
EXTRACTION_NAME = "extraction.html"
PREVIEWS_NAME = "previews"
STAGE = "evidence-output"

EVIDENCE_NAMES = (REPORT_NAME, CANONICAL_NAME, BASELINE_NAME, EXTRACTION_NAME, PREVIEWS_NAME)

Boundary = Literal["output-exists", "internal-error"]


def evidence_destinations(directory: Path) -> list[Path]:
    """Name every file an evidence directory can hold, whatever this run turned out to retain.

    A command checking its destinations before expensive work does not yet know which evidence
    it will produce, so it protects all of them: a directory holding only a stale Canonical
    Document must refuse before a parse and a packaging run, not after. The previews are named as
    one directory because how many of them there will be is not known this early either.
    """

    return [directory / name for name in EVIDENCE_NAMES]


@dataclass(frozen=True)
class EvidenceBundle:
    """One evidence directory and the retained evidence this run would write into it."""

    directory: Path
    document: dict[str, object] | None = None
    baseline: str | None = None
    extraction: str | None = None
    """The cleaned HTML the extractor produced, retained so extraction is inspectable.

    Only an extracted source has one. It is the extractor's own output rather than the relabelled
    copy Pandoc read, because the question it answers is what the extractor did; what recovery
    then changed is fully described by the recovery facts beside it.
    """
    previews: dict[str, bytes] = field(default_factory=dict[str, bytes])
    """Image preview files, written into the bundle's own previews directory."""
    staged: Path | None = None
    """A hidden sibling this bundle is written into, so it becomes visible in one rename.

    Immutable evidence is published, not accumulated: a reader must never see a bundle that is
    still being written. Where the bundle can simply be built in place — an explicit output's
    companion directory, or Galley-owned work storage — this stays None.
    """
    replaceable: bool = False
    """Whether this location holds the latest attempt rather than an immutable record.

    Galley-owned work storage is the only such location. A retry must be able to replace the
    evidence of the attempt before it; nothing published as Ready ever is.
    """

    @property
    def report(self) -> Path:
        """Name the Report file this directory owns."""

        return self.written / REPORT_NAME

    @property
    def written(self) -> Path:
        """Name the directory this run actually writes into, staged or final."""

        return self.staged if self.staged is not None else self.directory

    @property
    def destinations(self) -> list[Path]:
        """Name every file this run would write, so each can be protected before any is."""

        planned = [self.directory / REPORT_NAME]
        if self.document is not None:
            planned.append(self.directory / CANONICAL_NAME)
        if self.baseline is not None:
            planned.append(self.directory / BASELINE_NAME)
        if self.extraction is not None:
            planned.append(self.directory / EXTRACTION_NAME)
        planned.extend(self.directory / PREVIEWS_NAME / name for name in self.previews)
        return planned


@dataclass(frozen=True)
class EvidenceRefusal:
    """Why one evidence directory could not receive this run's evidence."""

    boundary: Boundary
    summary: str
    fact: dict[str, object]
    exit_code: ExitCode


def write_evidence(bundle: EvidenceBundle, *, overwrite: bool) -> EvidenceRefusal | None:
    """Write the Canonical Document and Preservation Baseline, or say why they were not.

    Every destination this run owns is checked before anything is written, so a directory that
    already holds evidence is refused whole rather than half-replaced. Replacing it at all takes
    the same explicit `--overwrite` the rest of the command-owned outputs take.
    """

    planned = _planned(bundle)
    replacing = overwrite or bundle.replaceable
    if not replacing:
        for path in bundle.destinations:
            if path.exists():
                return _exists(path)
    try:
        if bundle.staged is not None:
            rmtree(bundle.staged, ignore_errors=True)
        for directory in {path.parent for path, _ in planned} | {bundle.written}:
            directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return _internal_error(bundle.directory, error)
    for path, payload in planned:
        try:
            with path.open("wb" if replacing else "xb") as destination:
                _ = destination.write(payload)
        except FileExistsError:
            return _exists(path)
        except OSError as error:
            return _internal_error(path, error)
    return None


def publish_evidence(bundle: EvidenceBundle | None) -> None:
    """Make one staged evidence bundle visible at its final path in a single rename."""

    if bundle is None or bundle.staged is None:
        return
    bundle.directory.parent.mkdir(parents=True, exist_ok=True)
    os.replace(bundle.staged, bundle.directory)


def discard_evidence(bundle: EvidenceBundle | None) -> None:
    """Remove a staged bundle a refusal will never publish, leaving no partial evidence."""

    if bundle is not None and bundle.staged is not None:
        rmtree(bundle.staged, ignore_errors=True)


def _planned(bundle: EvidenceBundle) -> list[tuple[Path, bytes]]:
    written = bundle.written
    planned: list[tuple[Path, bytes]] = []
    if bundle.document is not None:
        planned.append((written / CANONICAL_NAME, canonical_bytes(bundle.document)))
    if bundle.baseline is not None:
        planned.append((written / BASELINE_NAME, bundle.baseline.encode("utf-8")))
    if bundle.extraction is not None:
        planned.append((written / EXTRACTION_NAME, bundle.extraction.encode("utf-8")))
    planned.extend(
        (written / PREVIEWS_NAME / name, payload)
        for name, payload in sorted(bundle.previews.items())
    )
    return planned


def _exists(path: Path) -> EvidenceRefusal:
    display = display_path(path)
    return EvidenceRefusal(
        boundary="output-exists",
        summary=f"retained evidence already exists: {display}",
        fact={"path": display},
        exit_code=ExitCode.REFUSED,
    )


def _internal_error(target: Path, error: OSError) -> EvidenceRefusal:
    error_type = type(error).__name__
    display = display_path(target)
    return EvidenceRefusal(
        boundary="internal-error",
        summary=f"internal error while writing retained evidence: {error_type}",
        fact={"error_type": error_type, "operation": "write-evidence", "path": display},
        exit_code=ExitCode.INTERNAL_ERROR,
    )

"""Write the Repair Set a localisation produced, or say why the directory could not receive it.

The three files carry the names `inspect` and `prepare` already write, because they are the same
three files — the Repair Inputs. An ordinary agent-assisted `prepare` reads this directory without
being told it came from anywhere unusual. The retrieved bytes sit beside them under `images/`, so
a reader holding the directory has the document, what it was measured against, and every picture
that went into it.

Nothing outside the named directory is ever written. Everything is built in a hidden sibling
first and made visible in one rename, so a run that fails part-way through writing leaves the
named directory exactly as it found it — "no partial Repair Set" is a property of the write, not
a promise about the weather.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from shutil import rmtree

from galley.document.canonical import canonical_bytes
from galley.localisation.refusals import LocalisationRefusal
from galley.locations import display_path
from galley.output.evidence import BASELINE_NAME, CANONICAL_NAME, REPORT_NAME
from galley.output.policy import input_collision
from galley.report.envelope import Report, report_json

IMAGES_NAME = "images"
ENCODING = "utf-8"
EVIDENCE_STAGE = "localisation-evidence"
STAGING_SUFFIX = ".localising"


def image_path(directory: Path, name: str) -> Path:
    """Name the file one retrieved image takes inside an evidence directory.

    One definition, because the record that names the file and the write that creates it must
    agree: a document pointing at a path nothing wrote is worse than no document.
    """

    return directory / IMAGES_NAME / name


@dataclass(frozen=True)
class RepairSet:
    """One directory and everything a completed localisation would put in it."""

    directory: Path
    report: Report
    document: dict[str, object]
    baseline: str
    images: dict[str, bytes] = field(default_factory=dict[str, bytes])

    @property
    def destinations(self) -> list[Path]:
        """Name every file this run would write, so each can be protected before any is."""

        return [
            self.directory / REPORT_NAME,
            self.directory / CANONICAL_NAME,
            self.directory / BASELINE_NAME,
            *(image_path(self.directory, name) for name in sorted(self.images)),
        ]

    def facts(self) -> dict[str, object]:
        """Name the directory and the three Repair Inputs an agent hands straight to `prepare`."""

        return {
            "directory": display_path(self.directory),
            "inspection_report": display_path(self.directory / REPORT_NAME),
            "canonical_document": display_path(self.directory / CANONICAL_NAME),
            "preservation_baseline": display_path(self.directory / BASELINE_NAME),
            "images_directory": display_path(self.directory / IMAGES_NAME),
        }


def reserved(directory: Path) -> list[Path]:
    """Name every path a localisation could write, before it knows what it will retrieve.

    A run that would refuse on its evidence directory must refuse before it fetches a single
    image, so the check has to be answerable while the image set is still unknown. The images
    directory is named whole for the same reason preparation names its previews directory whole.
    """

    return [
        directory / REPORT_NAME,
        directory / CANONICAL_NAME,
        directory / BASELINE_NAME,
        directory / IMAGES_NAME,
    ]


def unusable_directory(
    directory: Path, source: Path, *, overwrite: bool
) -> LocalisationRefusal | None:
    """Refuse a directory that holds an evidence set already, or that is the source itself.

    Input protection is asked first, so naming the source as a destination is refused as exactly
    that rather than as an occupied path.
    """

    planned = reserved(directory)
    collision = input_collision([source], planned)
    if collision is not None:
        return _refusal(
            "output-is-input",
            f"the evidence directory would write over the source: {display_path(collision)}",
            {"path": display_path(collision)},
        )
    if overwrite:
        return None
    taken = next((path for path in planned if path.exists()), None)
    if taken is None:
        return None
    return _occupied(taken)


def write_repair_set(repair: RepairSet, *, overwrite: bool) -> LocalisationRefusal | None:
    """Write every file the Repair Set holds, or leave the named directory as it was found.

    Destinations are checked again here rather than trusted from the earlier pass: the image
    files are only nameable once the images exist, and a run that fetched for thirty seconds may
    find a path taken that was free when it started.
    """

    if not overwrite:
        taken = next((path for path in repair.destinations if path.exists()), None)
        if taken is not None:
            return _occupied(taken)
    staging = repair.directory.parent / f".{repair.directory.name}{STAGING_SUFFIX}"
    try:
        _staged(repair, staging)
        _published(repair, staging)
    except OSError as error:
        rmtree(staging, ignore_errors=True)
        error_type = type(error).__name__
        return _refusal(
            "internal-error",
            f"internal error while writing the Repair Set: {error_type}",
            {
                "error_type": error_type,
                "operation": "write-repair-set",
                "path": display_path(repair.directory),
            },
        )
    return None


def _staged(repair: RepairSet, staging: Path) -> None:
    """Build the whole Repair Set in a hidden sibling, where a failure costs nothing visible."""

    rmtree(staging, ignore_errors=True)
    (staging / IMAGES_NAME).mkdir(parents=True)
    payloads = [
        (staging / REPORT_NAME, f"{report_json(repair.report)}\n".encode()),
        (staging / CANONICAL_NAME, canonical_bytes(repair.document)),
        (staging / BASELINE_NAME, repair.baseline.encode(ENCODING)),
        *((image_path(staging, name), payload) for name, payload in sorted(repair.images.items())),
    ]
    for path, payload in payloads:
        _ = path.write_bytes(payload)


def _published(repair: RepairSet, staging: Path) -> None:
    """Make the staged set visible: one rename where nothing is there, file by file where it is.

    A fresh directory arrives whole, which is the ordinary case. Replacing one the caller
    explicitly authorised is the only case that lands file by file, and it is the same window
    `prepare --overwrite` already has over its own evidence.
    """

    repair.directory.parent.mkdir(parents=True, exist_ok=True)
    if not repair.directory.exists():
        os.replace(staging, repair.directory)
        return
    (repair.directory / IMAGES_NAME).mkdir(parents=True, exist_ok=True)
    for staged in sorted(staging.rglob("*")):
        if staged.is_file():
            os.replace(staged, repair.directory / staged.relative_to(staging))
    rmtree(staging, ignore_errors=True)


def _occupied(path: Path) -> LocalisationRefusal:
    return _refusal(
        "output-exists",
        f"the evidence directory already holds a Repair Set: {display_path(path)}",
        {"path": display_path(path)},
    )


def _refusal(boundary: str, summary: str, fact: dict[str, object]) -> LocalisationRefusal:
    return LocalisationRefusal(boundary=boundary, stage=EVIDENCE_STAGE, summary=summary, fact=fact)

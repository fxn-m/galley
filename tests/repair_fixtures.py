"""Produce the three Repair Inputs an agent-assisted preparation supplies.

A Bespoke Repair is written by an agent at the moment it is needed, so these helpers stand in
for that agent: they run a real inspection, keep its Report and Preservation Baseline exactly as
written, and replace only the Canonical Document's AST with the repaired one. Nothing here is a
`prepare` transform, and nothing here edits the retained evidence.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.markdown_fixtures import native_ast, write_markdown
from tests.public_cli import public_cli_commands, run_command

PROFILE = ("--profile", "x4-crosspoint")

# Paul Graham's hand-rolled endnote shape as Markdown carries it: a visible bracketed digit in
# the prose, a bare "Notes" heading, and each note introduced by the same bracketed digit. The
# `[1]` sequences are unresolved shortcut references, so Pandoc keeps them as literal text and
# the document reaches `prepare` with zero notes — which is exactly `cli_expected` for it.
HAND_ROLLED_NOTES = """---
title: Great Work
author: Ada Lovelace
---

# Great Work

Curiosity drives the work [1] and persistence sustains it [2].

Notes

[1] Curiosity is the engine.

[2] Persistence keeps it running.
"""

# The same work with its apparatus rewritten into the Recovered Footnote Apparatus. The prose is
# word-for-word identical, so the only baseline token the built book cannot carry is "Notes".
REPAIRED_NOTES = """---
title: Great Work
author: Ada Lovelace
---

# Great Work

Curiosity drives the work[^1] and persistence sustains it[^2].

[^1]: Curiosity is the engine.

[^2]: Persistence keeps it running.
"""

# The one baseline token the repair consumes, hand-derived from HAND_ROLLED_NOTES: each digit
# survives as its reference number and again as its "Footnote N." label, and the bare "Notes"
# heading has nowhere to survive. Nothing else in the document says "Notes", deliberately — a
# title carrying the same word would hide the loss behind its own occurrence.
CONSUMED_TOKENS = {"Notes": 1}


@dataclass(frozen=True)
class RepairInputs:
    """The three files a repaired preparation is handed, and the evidence they came from."""

    report: Path
    canonical: Path
    baseline: Path

    @property
    def paths(self) -> tuple[Path, Path, Path]:
        """Name all three, for immutability assertions that must cover every one of them."""

        return (self.report, self.canonical, self.baseline)

    @property
    def options(self) -> tuple[str, ...]:
        """Name all three on the public command line, which is the only accepted set."""

        return (
            "--inspection-report",
            str(self.report),
            "--canonical-document",
            str(self.canonical),
            "--preservation-baseline",
            str(self.baseline),
        )


def inspected(directory: Path, source: str) -> Path:
    """Run one real inspection and retain its evidence, exactly as an agent would."""

    result = run_command(
        public_cli_commands("inspect", source)[0],
        *PROFILE,
        "--json",
        "--evidence-dir",
        str(directory),
    )
    assert result.returncode in (0, 3), result.stderr
    return directory


def repaired_document(evidence: Path, destination: Path, ast: Any) -> Path:
    """Write the repaired Canonical Document, changing the AST and nothing else."""

    document = json.loads((evidence / "canonical-document.json").read_text(encoding="utf-8"))
    _ = destination.write_text(
        f"{json.dumps({**document, 'pandoc': ast}, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return destination


def hand_rolled_repair(tmp_path: Path, name: str = "notes") -> tuple[Path, RepairInputs]:
    """Inspect the hand-rolled source and hand back the repair an agent would submit."""

    source = write_markdown(tmp_path / f"{name}.md", HAND_ROLLED_NOTES)
    evidence = inspected(tmp_path / f"{name}.galley", str(source))
    repair = write_markdown(tmp_path / f"{name}-repaired.md", REPAIRED_NOTES)
    canonical = repaired_document(evidence, tmp_path / f"{name}-repaired.json", native_ast(repair))
    return source, RepairInputs(
        evidence / "report.json", canonical, evidence / "preservation-baseline.txt"
    )


def declarations(path: Path, tokens: dict[str, int]) -> Path:
    """Write one expected-missing-token declaration file, as the public interface accepts it."""

    _ = path.write_text(json.dumps(tokens), encoding="utf-8")
    return path


def edited(source: Path, destination: Path, change: Callable[[Any], None]) -> Path:
    """Copy one JSON input and change it, so the original retained evidence stays untouched."""

    document = json.loads(source.read_text(encoding="utf-8"))
    change(document)
    _ = destination.write_text(f"{json.dumps(document, indent=2, sort_keys=True)}\n", "utf-8")
    return destination

"""Run Galley's definition-of-done gates from one entry point."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Gate:
    """One named command in an aggregate check tier."""

    name: str
    command: tuple[str, ...]


GATES = (
    Gate("formatting", (sys.executable, "-m", "ruff", "format", "--check", ".")),
    Gate("linting", (sys.executable, "-m", "ruff", "check", ".")),
    Gate("line count", (sys.executable, str(ROOT / "scripts/checkline.py"))),
    Gate("skill validation", (sys.executable, str(ROOT / "scripts/checkskill.py"))),
    Gate("regex allowlist", (sys.executable, str(ROOT / "scripts/checkregex.py"))),
    Gate("import layers", (sys.executable, str(ROOT / "scripts/checkimports.py"))),
    Gate("Modelled Set", (sys.executable, str(ROOT / "scripts/checkmodel.py"))),
    Gate("source kinds", (sys.executable, str(ROOT / "scripts/checksources.py"))),
    Gate("Repair Conventions", (sys.executable, str(ROOT / "scripts/checkconventions.py"))),
    Gate("record shapes", (sys.executable, str(ROOT / "scripts/checkrecords.py"))),
    Gate("Device Profile", (sys.executable, str(ROOT / "scripts/checkprofile.py"))),
    Gate("strict typing", (sys.executable, "-m", "basedpyright")),
    Gate("tests", (sys.executable, "-m", "pytest", "-n", "auto")),
)

Runner = Callable[[Sequence[str]], int]


def run_command(command: Sequence[str]) -> int:
    """Run one child gate from the repository root."""

    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        (str(Path(sys.executable).parent), environment.get("PATH", ""))
    )
    return subprocess.run(command, cwd=ROOT, check=False, env=environment).returncode


def run_gates(gates: Sequence[Gate], *, runner: Runner = run_command) -> int:
    """Run gates in order, stopping at and identifying the first failure."""

    for gate in gates:
        print(f"check: {gate.name}", flush=True)
        result = runner(gate.command)
        if result != 0:
            print(f"check: FAILED {gate.name} (exit {result})", file=sys.stderr)
            return result if result > 0 else 1
    return 0


def main() -> int:
    """Run the repository's definition-of-done checks."""

    result = run_gates(GATES)
    if result == 0:
        print("check: OK")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

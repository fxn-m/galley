"""Isolated installed-CLI journeys and explicit entry points for adapter parity."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

# Package-structure tests select a command name that cannot exist, so audit records a
# structured "not-found" conformance fact instead of paying for a real EPUBCheck run.
NO_EPUBCHECK = {"GALLEY_EPUBCHECK": "galley-epubcheck-not-installed"}
# Source tests select the same shape for Pandoc when they want the dependency-unavailable path.
NO_PANDOC = {"GALLEY_PANDOC": "galley-pandoc-not-installed"}
# Article tests select it for Defuddle, whose absence must never look like a page with no work.
NO_DEFUDDLE = {"GALLEY_DEFUDDLE": "galley-defuddle-not-installed"}


def public_cli_commands(*arguments: str) -> list[list[str]]:
    return [
        [installed_galley(), *arguments],
        [sys.executable, "-m", "galley", *arguments],
    ]


def cli_command(*arguments: str) -> list[str]:
    """Build the installed command for tests that deliberately control invocation details."""

    return [installed_galley(), *arguments]


def run_cli(
    *arguments: str, environment: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the installed command once with this invocation's environment overrides."""

    return run_command(cli_command(), *arguments, environment=environment)


def installed_galley() -> str:
    """The console script this interpreter was installed beside, not whatever PATH names first.

    Parity compares the same installation through both public entry points. `shutil.which` answers with the first `galley` on PATH, and a machine
    may carry several that all report the same version. Resolving through PATH compares the checkout against a stranger,
    and the disagreement it reports is about the wrong thing entirely.

    Test helpers therefore prefer the console script installed beside this interpreter and use
    `PATH` only as a fallback.
    """

    beside = Path(sys.executable).parent / "galley"
    if beside.is_file():
        return str(beside)
    found = shutil.which("galley")
    assert found is not None, "the public `galley` command is neither beside python nor on PATH"
    return found


def run_command(
    command: Sequence[str],
    *arguments: str,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one entry point with per-invocation arguments, for tests that own an output path."""

    return subprocess.run(
        [*command, *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=None if environment is None else {**os.environ, **environment},
    )


@dataclass(frozen=True)
class Preparation:
    """One invocation's captured output paths, process result, and decoded Report."""

    output: Path
    evidence: Path
    result: subprocess.CompletedProcess[str]
    report: dict[str, Any]


def prepare(
    root: Path,
    source: Path | str,
    *arguments: str,
    profile: str = "x4-crosspoint",
    environment: Mapping[str, str] | None = None,
    expected_exit: int | None = 0,
) -> Preparation:
    """Prepare once into a fresh test-local directory, retaining refusal evidence too.

    The caller owns the source and any repairs. Each call owns a separate artifact and
    evidence bundle even when two invocations share a source or environment.
    Explicit output-policy tests use run_command to name the paths whose state they test.
    """

    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="preparation-", dir=root))
    output = directory / "book.epub"
    evidence = output.with_suffix(".galley")
    if "--evidence-dir" in arguments:
        evidence = Path(arguments[arguments.index("--evidence-dir") + 1])
    result = run_command(
        [installed_galley()],
        "prepare",
        str(source),
        "--output",
        str(output),
        "--profile",
        profile,
        "--json",
        *arguments,
        environment=environment,
    )
    assert result.stderr == "", result.stderr
    if expected_exit is not None:
        assert result.returncode == expected_exit, result.stdout
    document = cast(object, json.loads(result.stdout))
    assert isinstance(document, dict), result.stdout
    return Preparation(output, evidence, result, cast(dict[str, Any], document))

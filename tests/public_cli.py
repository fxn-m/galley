"""Helpers for exercising both supported public CLI entry points."""

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

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


def installed_galley() -> str:
    """The console script this interpreter was installed beside, not whatever PATH names first.

    These tests assert that both public entry points agree, which only means anything when both
    are the same program. `shutil.which` answers with the first `galley` on PATH, and a machine
    may carry several that all report the same version — this one carries a `uv tool` install
    alongside the checkout's. Resolving through PATH compares the checkout against a stranger,
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


def run_public_cli(
    *arguments: str, environment: Mapping[str, str] | None = None
) -> list[subprocess.CompletedProcess[str]]:
    child_environment = None if environment is None else {**os.environ, **environment}
    return [
        subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=child_environment,
        )
        for command in public_cli_commands(*arguments)
    ]

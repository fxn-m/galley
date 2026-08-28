"""One preflight and execution surface for every pinned external dependency.

A single surface turns a missing or unusable dependency into a structured fact rather than a
shell traceback. This module owns command selection, timeouts and
diagnostic capture; each dependency module keeps its own arguments and its own reading of what
the tool produced.
"""

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

TIMEOUT_SECONDS = 300
DIAGNOSTIC_LIMIT = 2000
TRUNCATION_MARKER = " […truncated]"

UnavailableReason = Literal["not-found", "not-executable", "timeout"]


@dataclass(frozen=True)
class Execution:
    """One attempt to run a pinned dependency, whether or not it ran."""

    command: str
    completed: subprocess.CompletedProcess[str] | None = None
    reason: UnavailableReason | None = None
    detail: str = ""


def selected_command(variable: str, default: str) -> str:
    """Name the command to run, letting tests select one that cannot exist."""

    return os.environ.get(variable) or default


def run_dependency(
    command: str,
    arguments: Sequence[str],
    *,
    timeout: int = TIMEOUT_SECONDS,
    environment: Mapping[str, str] | None = None,
) -> Execution:
    """Run one pinned dependency, classifying every way it can fail to produce output.

    `environment` adds to the inherited environment rather than replacing it, because a tool
    still needs its own `PATH` and locale. It exists for the variables a deterministic build
    depends on, which are an argument to the tool in everything but spelling.
    """

    resolved = shutil.which(command)
    if resolved is None:
        return Execution(
            command, reason="not-found", detail=f"the command was not found: {command}"
        )
    try:
        completed = subprocess.run(
            [resolved, *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=None if environment is None else {**os.environ, **environment},
        )
    except subprocess.TimeoutExpired:
        return Execution(command, reason="timeout", detail=f"{command} exceeded {timeout}s")
    except OSError as error:
        return Execution(command, reason="not-executable", detail=str(error))
    return Execution(command, completed=completed)


def diagnostic(captured: str) -> str:
    """Retain a dependency's own output at a bounded length."""

    stripped = captured.strip()
    if len(stripped) <= DIAGNOSTIC_LIMIT:
        return stripped
    return stripped[:DIAGNOSTIC_LIMIT] + TRUNCATION_MARKER

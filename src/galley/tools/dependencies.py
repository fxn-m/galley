"""One preflight and execution surface for every pinned external dependency.

A single surface turns a missing or unusable dependency into a structured fact rather than a
shell traceback. This module owns invocation-scoped command and version identity, process
supervision and diagnostic capture. Each adapter keeps its native arguments and output parsing.
"""

import os
import shutil
import subprocess
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Literal

TIMEOUT_SECONDS = 300
DIAGNOSTIC_LIMIT = 2000
TRUNCATION_MARKER = " […truncated]"

UnavailableReason = Literal["not-found", "not-executable", "timeout"]
VersionProbe = Callable[[str], str | None]


@dataclass
class _Identity:
    """Selections and observations owned by one active invocation only."""

    commands: dict[tuple[str, str], str] = field(default_factory=dict)
    resolved: dict[str, str | None] = field(default_factory=dict)
    versions: dict[tuple[VersionProbe, str], str | None] = field(default_factory=dict)


_identity: ContextVar[_Identity | None] = ContextVar("dependency_identity", default=None)


@contextmanager
def invocation() -> Generator[None]:
    """Own fresh dependency identity until this invocation finishes, including on failure.

    The context variable locates the active scope; it holds no process-wide cache. Calls outside
    a scope retain no identity. Nested invocations restore their caller's state when they close.
    """

    token = _identity.set(_Identity())
    try:
        yield
    finally:
        _identity.reset(token)


def version_probe(probe: VersionProbe) -> VersionProbe:
    """Reuse an adapter's observed version, including an unanswered probe, within one invocation.

    The adapter still owns execution, parsing and failure interpretation. Distinct adapters may
    interpret the same command differently, so both the probe and command identify an observation.
    """

    @wraps(probe)
    def observed(command: str) -> str | None:
        identity = _identity.get()
        if identity is None:
            return probe(command)
        key = (probe, command)
        if key not in identity.versions:
            identity.versions[key] = probe(command)
        return identity.versions[key]

    return observed


@dataclass(frozen=True)
class Execution:
    """One attempt to run a pinned dependency, whether or not it ran."""

    command: str
    completed: subprocess.CompletedProcess[str] | None = None
    reason: UnavailableReason | None = None
    detail: str = ""


def selected_command(variable: str, default: str) -> str:
    """Select a command once per invocation, preserving the requested name in diagnostics."""

    identity = _identity.get()
    if identity is None:
        return os.environ.get(variable) or default
    key = (variable, default)
    if key not in identity.commands:
        identity.commands[key] = os.environ.get(variable) or default
    return identity.commands[key]


def _resolved_command(command: str) -> str | None:
    identity = _identity.get()
    if identity is None:
        return shutil.which(command)
    if command not in identity.resolved:
        identity.resolved[command] = shutil.which(command)
    return identity.resolved[command]


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

    resolved = _resolved_command(command)
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

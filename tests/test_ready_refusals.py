"""Refuse every unsafe Ready publication through the installed public CLI."""

from hashlib import sha256
from pathlib import Path

from tests.public_cli import run_cli
from tests.ready_fixtures import (
    COMPLETED,
    INVOCATION_ERROR,
    PROFILE,
    REFUSED,
    facts,
    inbox_note,
    prepare_ready,
    report,
)
from tests.workspace_fixtures import tree, workspace_environment


def test_republishing_the_same_provenance_refuses(tmp_path: Path) -> None:
    """Ready evidence is immutable, so the same source and hash never write a second time."""

    source = inbox_note(tmp_path)
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    first = prepare_ready(source, environment)
    assert first.returncode == COMPLETED
    published = tree(workspace / "ready")
    again = prepare_ready(source, environment)
    assert again.returncode == REFUSED
    assert facts(report(again.stdout), "refusal")["boundary"] == "output-exists"
    assert tree(workspace / "ready") == published


def test_a_changed_source_refuses_against_the_observed_hash(tmp_path: Path) -> None:
    """Preparation refuses before publication when the bytes are not the ones checked."""

    source = inbox_note(tmp_path)
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    stale = sha256(b"whatever the Inbox Check saw").hexdigest()
    result = prepare_ready(source, environment, "--expected-source-hash", stale)
    assert result.returncode == REFUSED
    refusal = facts(report(result.stdout), "refusal")
    assert refusal["boundary"] == "source-hash-mismatch"
    assert refusal["artifact_written"] is False
    assert not (workspace / "ready").exists()
    attempts = sorted((workspace / "work").glob("*/report.json"))
    assert len(attempts) == 1
    assert facts(report(attempts[0].read_text(encoding="utf-8")), "refusal")["boundary"] == (
        "source-hash-mismatch"
    )


def test_a_matching_hash_publishes(tmp_path: Path) -> None:
    """The hash an Inbox Check observed is exactly what a matching source presents."""

    source = inbox_note(tmp_path)
    environment = workspace_environment(tmp_path / "workspace", tmp_path / "home")
    observed = sha256(source.read_bytes()).hexdigest()
    result = prepare_ready(source, environment, "--expected-source-hash", observed)
    assert result.returncode == COMPLETED


def test_an_expected_hash_needs_local_source_bytes(tmp_path: Path) -> None:
    """A page has no bytes to compare, so the check is refused rather than quietly skipped."""

    environment = workspace_environment(tmp_path / "workspace", tmp_path / "home")
    result = run_cli(
        "prepare",
        "https://example.invalid/article",
        "--profile",
        PROFILE,
        "--ready",
        "--json",
        "--expected-source-hash",
        "0" * 64,
        environment=environment,
    )
    assert result.returncode == REFUSED
    assert facts(report(result.stdout), "refusal")["boundary"] == "expected-hash-unavailable"


def test_a_retried_attempt_replaces_its_work_evidence(tmp_path: Path) -> None:
    """Work storage holds the latest attempt, so a retry is never blocked by the last one."""

    source = inbox_note(tmp_path)
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    stale = sha256(b"stale").hexdigest()
    for _ in range(2):
        result = prepare_ready(source, environment, "--expected-source-hash", stale)
        assert result.returncode == REFUSED
    assert len(sorted((workspace / "work").glob("*/report.json"))) == 1
    published = prepare_ready(source, environment)
    assert published.returncode == COMPLETED


def test_ready_refuses_overwrite_rather_than_mutating_evidence(tmp_path: Path) -> None:
    """The explicit-output overwrite option is never a way to replace a Ready Artifact."""

    source = inbox_note(tmp_path)
    environment = workspace_environment(tmp_path / "workspace", tmp_path / "home")
    result = prepare_ready(source, environment, "--overwrite")
    assert result.returncode == INVOCATION_ERROR


def test_prepare_requires_exactly_one_destination_mode(tmp_path: Path) -> None:
    """Neither mode and both modes are invocation errors, before any workflow exists."""

    source = inbox_note(tmp_path)
    environment = workspace_environment(tmp_path / "workspace", tmp_path / "home")
    result = run_cli("prepare", str(source), "--profile", PROFILE, environment=environment)
    assert result.returncode == INVOCATION_ERROR
    result = run_cli(
        "prepare",
        str(source),
        "--profile",
        PROFILE,
        "--ready",
        "--output",
        str(tmp_path / "book.epub"),
        environment=environment,
    )
    assert result.returncode == INVOCATION_ERROR


def test_a_source_changing_while_it_is_read_refuses(tmp_path: Path) -> None:
    """A race between acquisition and packaging cannot produce a misattributed artifact.

    The parser reads the source itself, so a Pandoc stand-in that rewrites the file before
    handing it to the real Pandoc is exactly the race, made deterministic.
    """

    source = inbox_note(tmp_path)
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    meddler = tmp_path / "meddling-pandoc"
    _ = meddler.write_text(
        f'#!/bin/sh\nprintf "\\nAn edit that lands mid-read.\\n" >> "{source}"\nexec pandoc "$@"\n',
        encoding="utf-8",
    )
    meddler.chmod(0o755)
    result = prepare_ready(source, {**environment, "GALLEY_PANDOC": str(meddler)})
    assert result.returncode == REFUSED
    refusal = facts(report(result.stdout), "refusal")
    assert refusal["boundary"] == "source-changed-during-read"
    assert refusal["artifact_written"] is False
    assert not (workspace / "ready").exists()
    assert sorted((workspace / "work").glob("*/report.json"))

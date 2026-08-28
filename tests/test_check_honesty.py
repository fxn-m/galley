"""Keep Inbox Check honest across partial access, failure and recovery, through the CLI."""

from hashlib import sha256
from pathlib import Path

from tests.check_fixtures import (
    OTHER_BODY,
    candidate,
    checked,
    checked_workspace,
    derived,
    publish,
    states,
)
from tests.markdown_fixtures import blocked_links
from tests.public_cli import NO_PANDOC, run_public_cli
from tests.ready_fixtures import BODY, COMPLETED, REFUSED, facts, inbox_note, report
from tests.workspace_fixtures import entries, inbox_table, tree

STALE = sha256(b"whatever an earlier Inbox Check saw").hexdigest()


def note(path: Path, body: str = BODY) -> Path:
    """Place one Markdown source, creating whatever directory it belongs in."""

    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")
    return path


def test_an_unavailable_inbox_leaves_the_healthy_ones_usable_and_partial(tmp_path: Path) -> None:
    """A missing volume and a half-read Inbox both keep every other candidate reachable."""

    partial = tmp_path / "partial"
    healthy = tmp_path / "healthy"
    _ = note(partial / "seen.md")
    _ = note(partial / "locked" / "buried.md")
    _ = note(healthy / "kept.md")
    (partial / "locked").chmod(0o000)
    _, environment = checked_workspace(
        tmp_path,
        inbox_table("missing", str(tmp_path / "absent")),
        inbox_table("partial", str(partial), recursive=True),
        inbox_table("healthy", str(healthy)),
    )
    try:
        coverage = entries(checked(environment), "coverage")
        assert [entry["status"] for entry in coverage] == [
            "unavailable",
            "unavailable",
            "checked",
        ]
        assert [entry["supported_count"] for entry in coverage] == [0, 1, 1]
        assert str((partial / "locked").resolve()) in str(coverage[1]["error"])
        assert states(environment) == {"seen.md": "new", "kept.md": "new"}
    finally:
        (partial / "locked").chmod(0o700)


def test_overlap_symlinks_and_permission_errors_attribute_deterministically(
    tmp_path: Path,
) -> None:
    """One awkward tree resolves the same way every time, and no walk ever loops."""

    outer = tmp_path / "outer"
    inner = outer / "inner"
    target = note(outer / "real.md")
    _ = note(inner / "shared.md", OTHER_BODY)
    (outer / "link.md").symlink_to(target)
    (outer / "loop").symlink_to(outer, target_is_directory=True)
    _ = note(outer / "locked" / "buried.md")
    (outer / "locked").chmod(0o000)
    _, environment = checked_workspace(
        tmp_path,
        inbox_table("outer", str(outer), recursive=True),
        inbox_table("inner", str(inner)),
    )
    try:
        first = derived(checked(environment))
        assert first == derived(checked(environment))
        found = entries(checked(environment), "candidates")
        assert [entry["resolved_path"] for entry in found] == [
            str(inner.resolve() / "shared.md"),
            str(target.resolve()),
        ]
        assert found[0]["inboxes"] == ["outer", "inner"]
        assert entries(checked(environment), "coverage")[0]["status"] == "unavailable"
    finally:
        (outer / "locked").chmod(0o700)


def test_a_failed_attempt_is_a_fact_beside_the_state_not_a_fourth_one(tmp_path: Path) -> None:
    """An execution refusal is retained as the latest attempt; the candidate is still new."""

    source = inbox_note(tmp_path)
    _, environment = checked_workspace(tmp_path)
    refused = publish(source, {**environment, **NO_PANDOC})
    assert refused.returncode == REFUSED
    found = candidate(checked(environment), "note.md")
    assert found["state"] == "new"
    attempt = facts(found, "latest_attempt")
    assert attempt["boundary"] == "dependency-unavailable"
    assert attempt["stage"] == "source-parse"


def test_a_refused_candidate_stays_eligible_for_retry_and_recovers(tmp_path: Path) -> None:
    """Work evidence is replaceable, so no refusal class blocks the attempt that follows it."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, {**environment, **NO_PANDOC}).returncode == REFUSED
    assert publish(source, environment, "--expected-source-hash", STALE).returncode == REFUSED
    assert states(environment) == {"note.md": "new"}
    assert not (workspace / "ready").exists()
    assert publish(source, environment).returncode == COMPLETED
    recovered = candidate(checked(environment), "note.md")
    assert recovered["state"] == "already-ready"
    assert facts(recovered, "latest_attempt")["boundary"] == "source-hash-mismatch"


def test_a_compatibility_refusal_is_retryable_once_the_source_is_repaired(tmp_path: Path) -> None:
    """A candidate refused against the Device Profile is still new, and still preparable."""

    source = inbox_note(tmp_path, "note.md", blocked_links(129))
    workspace, environment = checked_workspace(tmp_path)
    refused = publish(source, environment)
    assert refused.returncode == REFUSED
    assert facts(report(refused.stdout), "refusal")["boundary"] == "compatibility"
    assert not (workspace / "ready").exists()
    found = candidate(checked(environment), "note.md")
    assert found["state"] == "new"
    assert facts(found, "latest_attempt")["boundary"] == "compatibility"
    _ = source.write_text(blocked_links(128), encoding="utf-8")
    assert publish(source, environment).returncode == COMPLETED
    assert states(environment) == {"note.md": "already-ready"}


def test_a_source_hash_race_refuses_and_the_next_check_reports_current_bytes(
    tmp_path: Path,
) -> None:
    """The hash a check observed is the hash prepare is held to; a new check states the new one."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    observed = str(candidate(checked(environment), "note.md")["sha256"])
    _ = source.write_text(OTHER_BODY, encoding="utf-8")
    refused = publish(source, environment, "--expected-source-hash", observed)
    assert refused.returncode == REFUSED
    assert facts(report(refused.stdout), "refusal")["boundary"] == "source-hash-mismatch"
    assert not (workspace / "ready").exists()
    current = candidate(checked(environment), "note.md")
    assert current["sha256"] == sha256(OTHER_BODY.encode("utf-8")).hexdigest()
    assert current["sha256"] != observed
    assert current["state"] == "new"


def test_removing_a_source_deletes_nothing_it_produced(tmp_path: Path) -> None:
    """Every artifact, Report, work bundle and Delivery Record outlives the source."""

    kept = inbox_note(tmp_path, "note.md")
    other = inbox_note(tmp_path, "other.md", OTHER_BODY)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(kept, environment).returncode == COMPLETED
    assert publish(other, environment, "--expected-source-hash", STALE).returncode == REFUSED
    record = workspace / "delivery" / "record.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    _ = record.write_text('{"schema": "galley/delivery-record/1"}', encoding="utf-8")
    retained = tree(workspace)
    kept.unlink()
    other.unlink()
    assert states(environment) == {}
    assert tree(workspace) == retained
    assert record.is_file()


def test_repeated_checks_are_deterministic_and_move_no_processed_source(tmp_path: Path) -> None:
    """Nothing is archived, cleaned up or moved once a source has been prepared."""

    source = inbox_note(tmp_path, "note.md")
    _ = inbox_note(tmp_path, "other.md", OTHER_BODY)
    _, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    before = tree(tmp_path)
    observed = [derived(checked(environment)) for _ in range(3)]
    assert observed[0] == observed[1] == observed[2]
    assert states(environment) == {"note.md": "already-ready", "other.md": "new"}
    assert tree(tmp_path) == before


def test_human_output_states_the_attempt_and_the_damage_it_found(tmp_path: Path) -> None:
    """Concise output carries the same partial, failed and damaged facts as the document."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    assert publish(source, environment, "--expected-source-hash", STALE).returncode == REFUSED
    (workspace / "ready" / "note.epub").unlink()
    for result in run_public_cli("inbox", "check", environment=environment):
        assert "    latest attempt: source-hash-mismatch (source-acquisition)" in result.stdout
        assert "Evidence problems: 1" in result.stdout
        assert f"  artifact-missing: {workspace / 'ready' / 'evidence'}" in result.stdout
        assert result.returncode == COMPLETED

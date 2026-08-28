"""Derive repeated Inbox Check state from immutable Ready evidence, through the installed CLI."""

from pathlib import Path

from tests.check_fixtures import checked_workspace, publish, states
from tests.public_cli import run_public_cli
from tests.ready_fixtures import BODY, COMPLETED, facts, inbox_note, ready_reports, report
from tests.workspace_fixtures import tree

CHANGED_BODY = BODY + "\nA second paragraph, long enough to make an entirely different book.\n"


def test_an_unpublished_candidate_is_new(tmp_path: Path) -> None:
    """With nothing published, every candidate is new and the check still completes."""

    _ = inbox_note(tmp_path)
    _, environment = checked_workspace(tmp_path)
    assert states(environment) == {"note.md": "new"}


def test_a_published_candidate_becomes_already_ready(tmp_path: Path) -> None:
    """The exact source pair and a matching artifact are what make a candidate already ready."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    assert states(environment) == {"note.md": "already-ready"}
    assert (workspace / "ready" / "note.epub").is_file()


def test_an_edited_source_is_changed_and_the_published_book_survives(tmp_path: Path) -> None:
    """A changed source stays changed while the earlier artifact and Report stay immutable."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    published = workspace / "ready" / "note.epub"
    original = published.read_bytes()
    _ = source.write_text(CHANGED_BODY, encoding="utf-8")
    assert states(environment) == {"note.md": "changed"}
    assert published.read_bytes() == original
    assert len(ready_reports(workspace)) == 1


def test_reverting_to_a_published_hash_is_recognised_without_rebuilding(tmp_path: Path) -> None:
    """Restoring a previously prepared hash finds that pair's own Report still in place."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    _ = source.write_text(CHANGED_BODY, encoding="utf-8")
    assert states(environment) == {"note.md": "changed"}
    _ = source.write_text(BODY, encoding="utf-8")
    assert states(environment) == {"note.md": "already-ready"}
    assert len(ready_reports(workspace)) == 1


def test_a_copied_or_renamed_source_is_new_even_though_its_bytes_recur(tmp_path: Path) -> None:
    """Identity is the resolved path, so recurring content under a new path has no evidence."""

    source = inbox_note(tmp_path)
    _, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    copied = source.parent / "copy.md"
    _ = copied.write_text(BODY, encoding="utf-8")
    assert states(environment) == {"note.md": "already-ready", "copy.md": "new"}
    source.rename(source.parent / "renamed.md")
    assert states(environment) == {"renamed.md": "new", "copy.md": "new"}


def test_a_missing_or_replaced_artifact_cannot_produce_already_ready(tmp_path: Path) -> None:
    """`already-ready` claims a finished book exists, so it is checked against the bytes."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    published = workspace / "ready" / "note.epub"
    original = published.read_bytes()
    _ = published.write_bytes(b"not the book this Report recorded")
    assert states(environment) == {"note.md": "new"}
    published.unlink()
    assert states(environment) == {"note.md": "new"}
    _ = published.write_bytes(original)
    assert states(environment) == {"note.md": "already-ready"}


def test_damaged_ready_evidence_cannot_produce_already_ready(tmp_path: Path) -> None:
    """A Report that will not parse answers nothing, rather than standing in for an answer."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    bundles = sorted((workspace / "ready" / "evidence").glob("*/report.json"))
    assert len(bundles) == 1
    _ = bundles[0].write_text("{ this is not a Report", encoding="utf-8")
    assert states(environment) == {"note.md": "new"}
    assert (workspace / "ready" / "note.epub").is_file()


def test_the_published_report_records_the_pair_the_state_is_derived_from(tmp_path: Path) -> None:
    """State comes from the Report's own source pair and artifact hash, not from a second store."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    published_report = report(publish(source, environment).stdout)
    retained = ready_reports(workspace)[0]
    assert facts(retained, "source")["path"] == str(source.resolve())
    assert facts(retained, "source")["sha256"] == facts(published_report, "source")["sha256"]
    assert facts(retained, "artifact")["sha256"] == facts(published_report, "artifact")["sha256"]


def test_human_output_states_each_candidate_behind_its_own_state(tmp_path: Path) -> None:
    """Concise output leads with the state, which is the fact a reader acts on."""

    source = inbox_note(tmp_path)
    _, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    for result in run_public_cli("inbox", "check", environment=environment):
        assert f"  already-ready — inbox: {source.resolve()} (markdown," in result.stdout
        assert result.returncode == COMPLETED


def test_repeated_checks_introduce_no_index_or_status_file(tmp_path: Path) -> None:
    """Deriving state reads immutable evidence and writes nothing at all, however often."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    assert states(environment) == {"note.md": "already-ready"}
    before = tree(workspace)
    assert states(environment) == {"note.md": "already-ready"}
    assert tree(workspace) == before

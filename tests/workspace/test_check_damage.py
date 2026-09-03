"""Report every damaged Ready Artifact and evidence bundle a check meets, and repair none."""

from pathlib import Path

from tests.support.ready_fixtures import COMPLETED, facts, inbox_note, report
from tests.support.workspace_fixtures import entries
from tests.workspace.check_fixtures import (
    OTHER_BODY,
    bundles,
    checked,
    checked_workspace,
    publish,
    states,
)


def test_missing_artifacts_and_damaged_evidence_are_reported_and_left_alone(
    tmp_path: Path,
) -> None:
    """A check repairs nothing and deletes nothing, so it says what it found instead."""

    kept = inbox_note(tmp_path, "note.md")
    other = inbox_note(tmp_path, "other.md", OTHER_BODY)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(kept, environment).returncode == COMPLETED
    assert publish(other, environment).returncode == COMPLETED
    published = bundles(workspace)
    missing = workspace / "ready" / "note.epub"
    missing.unlink()
    _ = (published[str(other.resolve())] / "report.json").write_text("{ not a Report", "utf-8")
    document = checked(environment)
    problems = entries(document, "evidence_problems")
    assert {(str(found["problem"]), str(found["evidence_path"])) for found in problems} == {
        ("artifact-missing", str(published[str(kept.resolve())])),
        ("unreadable-report", str(published[str(other.resolve())])),
    }
    assert [str(found["evidence_path"]) for found in problems] == sorted(
        str(found["evidence_path"]) for found in problems
    )
    assert str(missing) in {str(found["artifact_path"]) for found in problems}
    assert states(environment) == {"note.md": "new", "other.md": "new"}
    assert not missing.exists()
    assert (workspace / "ready" / "other.epub").is_file()
    assert sorted(path.name for path in (workspace / "ready" / "evidence").iterdir()) == sorted(
        path.name for path in published.values()
    )


def test_every_shape_of_damage_is_named_for_what_it_is(tmp_path: Path) -> None:
    """Replaced bytes, an unreadable book and a Report missing its facts each say so."""

    replaced = inbox_note(tmp_path, "replaced.md")
    incomplete = inbox_note(tmp_path, "incomplete.md", OTHER_BODY)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(replaced, environment).returncode == COMPLETED
    assert publish(incomplete, environment).returncode == COMPLETED
    published = bundles(workspace)
    _ = (workspace / "ready" / "replaced.epub").write_bytes(b"a different book entirely")
    _ = (published[str(incomplete.resolve())] / "report.json").write_text(
        '{"source": {"path": "/nowhere/incomplete.md"}}', encoding="utf-8"
    )
    problems = entries(checked(environment), "evidence_problems")
    assert {(str(found["problem"]), str(found["evidence_path"])) for found in problems} == {
        ("artifact-mismatched", str(published[str(replaced.resolve())])),
        ("incomplete-report", str(published[str(incomplete.resolve())])),
    }
    assert states(environment) == {"replaced.md": "new", "incomplete.md": "new"}


def test_damage_is_reported_even_when_no_candidate_still_points_at_it(tmp_path: Path) -> None:
    """A book that vanished is named whether or not the source that made it still matches."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    published = bundles(workspace)[str(source.resolve())]
    (workspace / "ready" / "note.epub").unlink()
    _ = source.write_text(OTHER_BODY, encoding="utf-8")
    document = checked(environment)
    assert states(environment) == {"note.md": "changed"}
    assert [str(found["problem"]) for found in entries(document, "evidence_problems")] == [
        "artifact-missing"
    ]
    assert str(entries(document, "evidence_problems")[0]["evidence_path"]) == str(published)
    source.unlink()
    assert states(environment) == {}
    assert entries(checked(environment), "evidence_problems") != []


def test_a_damaged_exact_pair_falls_back_to_changed_where_the_path_has_other_evidence(
    tmp_path: Path,
) -> None:
    """Damaged evidence is reported and then treated as absent, never as an answer."""

    source = inbox_note(tmp_path)
    _, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    _ = source.write_text(OTHER_BODY, encoding="utf-8")
    republished = publish(source, environment)
    assert republished.returncode == COMPLETED
    assert states(environment) == {"note.md": "already-ready"}
    Path(str(facts(report(republished.stdout), "artifact")["path"])).unlink()
    assert states(environment) == {"note.md": "changed"}
    assert [
        str(found["problem"]) for found in entries(checked(environment), "evidence_problems")
    ] == ["artifact-missing"]


def test_an_unreadable_artifact_is_not_reported_as_a_missing_one(tmp_path: Path) -> None:
    """A book that is there but cannot be opened is named for that, not for being absent."""

    source = inbox_note(tmp_path)
    workspace, environment = checked_workspace(tmp_path)
    assert publish(source, environment).returncode == COMPLETED
    published = workspace / "ready" / "note.epub"
    published.chmod(0o000)
    try:
        problems = entries(checked(environment), "evidence_problems")
        assert [str(found["problem"]) for found in problems] == ["artifact-unreadable"]
        assert str(problems[0]["artifact_path"]) == str(published)
        assert states(environment) == {"note.md": "new"}
    finally:
        published.chmod(0o600)
